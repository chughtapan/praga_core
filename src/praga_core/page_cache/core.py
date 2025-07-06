"""Simplified PageCache implementation with clear separation of concerns."""

import logging
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Generic,
    List,
    Optional,
    Type,
    TypeVar,
    cast,
)

from sqlalchemy import Table
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from ..types import Page, PageURI
from .provenance import ProvenanceManager
from .query import PageQuery
from .registry import PageRegistry
from .schema import Base, PageRelationships
from .storage import PageStorage
from .validator import PageValidator

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)


class PageCache:
    """A simplified, more readable PageCache implementation.

    This design separates concerns into focused components:
    - PageStorage: Core CRUD operations
    - PageRegistry: Type registration and table management
    - PageValidator: Validation logic
    - PageQuery: Query building and execution
    - ProvenanceManager: Relationship tracking

    Use `await PageCache.create(url, drop_previous)` to instantiate.
    Direct use of the constructor is discouraged.
    """

    def __init__(
        self,
        url: str,
        drop_previous: bool = False,
        _engine: Any = None,
        _session_factory: Any = None,
    ) -> None:
        """Do not use directly. Use `await PageCache.create(...)` instead."""
        if _engine is not None and _session_factory is not None:
            self._engine = _engine
            self._session_factory = _session_factory
        else:
            # Only allow direct construction for internal use
            raise RuntimeError(
                "Use `await PageCache.create(url, drop_previous)` to instantiate PageCache."
            )

        # Initialize components
        self._registry = PageRegistry(self._engine)
        self._storage = PageStorage(self._session_factory, self._registry)
        self._validator = PageValidator()
        self._query = PageQuery(self._session_factory, self._registry)
        self._provenance = ProvenanceManager(
            self._session_factory, self._storage, self._registry
        )

    @classmethod
    async def create(cls, url: str, drop_previous: bool = False) -> "PageCache":
        engine_args: dict[str, Any] = {}
        if url.startswith("postgresql"):
            engine_args["poolclass"] = NullPool
        elif url.startswith("sqlite+aiosqlite://"):
            engine_args["poolclass"] = StaticPool
            engine_args["connect_args"] = {"check_same_thread": False}
        engine = create_async_engine(url, **engine_args)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        # Create tables
        if drop_previous:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
                await conn.run_sync(Base.metadata.create_all)
                # Explicitly ensure PageRelationships table is created
                await conn.run_sync(
                    lambda sync_conn: cast(Table, PageRelationships.__table__).create(
                        sync_conn, checkfirst=True
                    )
                )
        else:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                # Explicitly ensure PageRelationships table is created
                await conn.run_sync(
                    lambda sync_conn: cast(Table, PageRelationships.__table__).create(
                        sync_conn, checkfirst=True
                    )
                )
        return cls(url, drop_previous, _engine=engine, _session_factory=session_factory)

    async def _reset_async(self) -> None:
        """Reset database and clear all state (async)."""
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        self._registry.clear()
        logger.debug("Reset database and cleared all state")

    # Core operations - simple and clear
    async def store(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page, optionally with parent relationship (async).

        Returns True if newly created, False if already existed.
        """
        # Validate provenance if needed
        if parent_uri or page.parent_uri:
            effective_parent = parent_uri or page.parent_uri
            if effective_parent is not None:
                await self._provenance.validate_relationship(page, effective_parent)
            if parent_uri:
                page.parent_uri = parent_uri

        # Register type if needed
        await self._registry.ensure_registered(page.__class__)

        # Store page
        return await self._storage.store(page, parent_uri)

    async def get(self, page_type: Type[P], uri: PageURI) -> Optional[P]:
        """Get a page by type and URI, with validation (async)."""
        page = await self._storage.get(page_type, uri)
        if page and not await self._validate_page_and_ancestors(page):
            return None
        return page

    async def get_latest(self, page_type: Type[P], uri_prefix: str) -> Optional[P]:
        """Get the latest version of a page (async)."""
        page = await self._storage.get_latest(page_type, uri_prefix)
        if page and not await self._validator.is_valid(page):
            await self._storage.mark_invalid(page.uri)
            return None
        return page

    def find(self, page_type: Type[P]) -> "QueryBuilder[P]":
        """Start building a query for pages of the given type."""
        return QueryBuilder(page_type, self._query, self._validator, self._storage)

    # Validation management
    def register_validator(
        self, page_type: Type[P], validator: Callable[[P], Awaitable[bool]]
    ) -> None:
        """Register an validator function for a page type."""
        self._validator.register(page_type, validator)

    # Cache management
    async def invalidate(self, uri: PageURI) -> bool:
        """Mark a specific page as invalid."""
        return await self._storage.mark_invalid(uri)

    # Versioning methods
    async def get_latest_version(
        self, page_type: Type[P], uri_prefix: str
    ) -> Optional[int]:
        """Get the latest version number for a URI prefix (used by ServerContext for auto-increment)."""
        page = await self._storage.get_latest(page_type, uri_prefix)
        return page.uri.version if page else None

    # Provenance operations
    async def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all child pages of the given parent."""
        return await self._provenance.get_children(parent_uri)

    async def get_lineage(self, page_uri: PageURI) -> List[Page]:
        """Get the full lineage from root to this page."""
        return await self._provenance.get_lineage(page_uri)

    async def _validate_page_and_ancestors(self, page: Page) -> bool:
        """Validate a page and its ancestors using registered validators."""
        # First, validate the page itself
        if not await self._validator.is_valid(page):
            await self.invalidate(page.uri)
            return False

        # Then validate all ancestors if page has a parent and we have validators
        if page.parent_uri is not None and self._validator._validators:
            try:
                provenance_chain = await self.get_lineage(page.uri)
                # Remove the current page from the chain (it's always the last one)
                ancestor_pages = provenance_chain[:-1] if provenance_chain else []

                for ancestor in ancestor_pages:
                    if not await self._validator.is_valid(ancestor):
                        logger.debug(f"Ancestor page failed validation: {ancestor.uri}")
                        # Mark ancestor as invalid in cache
                        await self.invalidate(ancestor.uri)
                        # Also mark current page as invalid since its ancestor is invalid
                        await self.invalidate(page.uri)
                        return False
            except Exception as e:
                logger.warning(f"Error validating provenance chain for {page.uri}: {e}")
                # If we can't validate ancestors, only fail if we have validators registered
                if self._validator._validators:
                    return False

        return True

    # Utilities
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as session:
            yield session


class QueryBuilder(Generic[P]):
    """Fluent interface for building page queries."""

    def __init__(
        self,
        page_type: Type[P],
        query_engine: PageQuery,
        validator: PageValidator,
        storage: PageStorage,
    ) -> None:
        self._page_type = page_type
        self._query_engine = query_engine
        self._validator = validator
        self._storage = storage
        self._filters: List[Callable[[Any], Any]] = []

    def where(self, condition: Callable[[Any], Any]) -> "QueryBuilder[P]":
        """Add a WHERE condition to the query."""
        self._filters.append(condition)
        return self

    async def all(self) -> List[P]:
        """Execute query and return all matching valid pages."""
        pages = await self._query_engine.find(self._page_type, self._filters)
        valid_pages: List[P] = []
        for page in pages:
            if await self._validator.is_valid(page):
                valid_pages.append(page)
            else:
                await self._storage.mark_invalid(page.uri)
        return valid_pages

    async def first(self) -> Optional[P]:
        """Execute query and return first matching valid page."""
        results = await self.all()
        return results[0] if results else None

    async def count(self) -> int:
        """Count matching valid pages"""
        return len(await self.all())
