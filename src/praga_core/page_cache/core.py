"""Simplified PageCache implementation with clear separation of concerns."""

import logging
from typing import Any, Awaitable, Callable, Generic, List, Optional, Type, TypeVar, Union, cast

from sqlalchemy import Table, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

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

    Example:
        cache = SimplePageCache("sqlite:///cache.db")

        # Simple operations
        cache.store(user_page)
        user = cache.get(UserPage, uri)
        users = cache.find(UserPage).where(lambda t: t.email.like("%@company.com")).all()

        # With validation
        cache.register_validator(GoogleDocPage, lambda doc: doc.revision == "current")

        # With provenance
        cache.store(chunk_page, parent_uri=header.uri)
    """

    def __init__(self, url: str, drop_previous: bool = False) -> None:
        """Initialize the cache with database URL."""
        # Setup database
        engine_args = {}
        if url.startswith("postgresql"):
            from sqlalchemy.pool import NullPool

            engine_args["poolclass"] = NullPool

        self._engine = create_engine(url, **engine_args)
        self._session_factory = sessionmaker(bind=self._engine)

        # Initialize components
        self._registry = PageRegistry(self._engine)
        self._storage = PageStorage(self._session_factory, self._registry)
        self._validator = PageValidator()
        self._query = PageQuery(self._session_factory, self._registry)
        self._provenance = ProvenanceManager(
            self._session_factory, self._storage, self._registry
        )

        Base.metadata.create_all(
            self._engine,
            tables=[cast(Table, PageRelationships.__table__)],
            checkfirst=True,
        )

        if drop_previous:
            self._reset()

    def _reset(self) -> None:
        """Reset database and clear all state."""
        from .schema import Base

        Base.metadata.drop_all(self._engine)
        self._registry.clear()
        logger.debug("Reset database and cleared all state")

    # Core operations - simple and clear
    def store(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page, optionally with parent relationship.

        Returns True if newly created, False if updated.
        """
        # Validate provenance if needed
        if parent_uri or page.parent_uri:
            effective_parent = parent_uri or page.parent_uri
            if effective_parent is not None:
                self._provenance.validate_relationship(page, effective_parent)
            if parent_uri:
                page.parent_uri = parent_uri

        # Register type if needed
        self._registry.ensure_registered(page.__class__)

        # Store page
        return self._storage.store(page, parent_uri)

    def get(self, page_type: Type[P], uri: PageURI) -> Optional[P]:
        """Get a page by type and URI, with validation."""
        page = self._storage.get(page_type, uri)
        if page and not self._validate_page_and_ancestors(page):
            return None
        return page

    def get_latest(self, page_type: Type[P], uri_prefix: str) -> Optional[P]:
        """Get the latest version of a page."""
        page = self._storage.get_latest(page_type, uri_prefix)
        if page and not self._validator.is_valid(page):
            self._storage.mark_invalid(page.uri)
            return None
        return page

    def find(self, page_type: Type[P]) -> "QueryBuilder[P]":
        """Start building a query for pages of the given type."""
        return QueryBuilder(page_type, self._query, self._validator, self._storage)

    # Validation management
    def register_validator(
        self, page_type: Type[P], validator: Union[Callable[[P], bool], Callable[[P], Awaitable[bool]]]
    ) -> None:
        """Register a validator function for a page type."""
        self._validator.register(page_type, validator)

    # Cache management
    def invalidate(self, uri: PageURI) -> bool:
        """Mark a specific page as invalid."""
        return self._storage.mark_invalid(uri)

    # Versioning methods
    def get_latest_version(self, page_type: Type[P], uri_prefix: str) -> Optional[int]:
        """Get the latest version number for a URI prefix (used by ServerContext for auto-increment)."""
        page = self._storage.get_latest(page_type, uri_prefix)
        return page.uri.version if page else None

    # Provenance operations
    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all child pages of the given parent."""
        return self._provenance.get_children(parent_uri)

    def get_lineage(self, page_uri: PageURI) -> List[Page]:
        """Get the full lineage from root to this page."""
        return self._provenance.get_lineage(page_uri)

    def _validate_page_and_ancestors(self, page: Page) -> bool:
        """Validate a page and its ancestors using registered validators."""
        # First, validate the page itself
        if not self._validator.is_valid(page):
            self.invalidate(page.uri)
            return False

        # Then validate all ancestors if page has a parent and we have validators
        if page.parent_uri is not None and self._validator._validators:
            try:
                provenance_chain = self.get_lineage(page.uri)
                # Remove the current page from the chain (it's always the last one)
                ancestor_pages = provenance_chain[:-1] if provenance_chain else []

                for ancestor in ancestor_pages:
                    if not self._validator.is_valid(ancestor):
                        logger.debug(f"Ancestor page failed validation: {ancestor.uri}")
                        # Mark ancestor as invalid in cache
                        self.invalidate(ancestor.uri)
                        # Also mark current page as invalid since its ancestor is invalid
                        self.invalidate(page.uri)
                        return False
            except Exception as e:
                logger.warning(f"Error validating provenance chain for {page.uri}: {e}")
                # If we can't validate ancestors, only fail if we have validators registered
                if self._validator._validators:
                    return False

        return True

    # Utilities
    @property
    def engine(self) -> Engine:
        return self._engine

    def get_session(self) -> Session:
        return self._session_factory()


class QueryBuilder(Generic[P]):
    """Fluent interface for building page queries."""

    def __init__(
        self,
        page_type: Type[P],
        query_engine: PageQuery,
        validator: PageValidator,
        storage: PageStorage,
    ):
        self._page_type = page_type
        self._query_engine = query_engine
        self._validator = validator
        self._storage = storage
        self._filters: List[Callable[[Any], Any]] = []

    def where(self, condition: Callable[[Any], Any]) -> "QueryBuilder[P]":
        """Add a WHERE condition to the query."""
        self._filters.append(condition)
        return self

    def all(self) -> List[P]:
        """Execute query and return all matching valid pages."""
        pages = self._query_engine.find(self._page_type, self._filters)
        valid_pages: List[P] = []

        for page in pages:
            if self._validator.is_valid(page):
                valid_pages.append(page)
            else:
                # Automatically invalidate pages that fail validation
                self._storage.mark_invalid(page.uri)

        return valid_pages

    def first(self) -> Optional[P]:
        """Execute query and return first matching valid page."""
        results = self.all()
        return results[0] if results else None

    def count(self) -> int:
        """Count matching valid pages."""
        return len(self.all())
