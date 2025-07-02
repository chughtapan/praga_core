"""Core PageCache implementation."""

import logging
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, cast

from sqlalchemy import create_engine, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.schema import Table

from ..types import Page, PageURI
from .provenance import ProvenanceTracker
from .schema import (
    Base,
    PageRelationships,
    clear_table_registry,
    create_page_table,
    get_table_registry,
)
from .serialization import (
    deserialize_from_storage,
    serialize_for_storage,
)

logger = logging.getLogger(__name__)

# TypeVar for generic Page type support
P = TypeVar("P", bound=Page)


class PageCache:
    """SQL-based cache for storing and retrieving Page instances.

    This class provides automatic SQL table generation from Pydantic Page models,
    with support for storing, retrieving, and querying pages using type-safe
    SQLAlchemy expressions.

    Features:
    - Automatic schema synthesis from Page models
    - URI-based primary keys
    - Type-safe querying with SQLAlchemy expressions
    - Table reuse across cache instances
    - Support for complex field types via JSON columns
    - Provenance tracking for page relationships
    - Cache invalidation with ancestor validation

    Example:
        cache = PageCache("sqlite:///pages.db")

        # Pages are automatically registered when first stored
        user = UserPage(uri=PageURI(...), name="John", email="john@example.com")
        cache.store_page(user)

        # Query with type-safe expressions
        users = cache.find_pages_by_attribute(
            UserPage,
            lambda t: t.email.like("%@company.com")
        )

        # Store with provenance tracking
        chunk = ChunkPage(uri=PageURI(...), content="...")
        cache.store_page(chunk, parent_uri=header.uri)
    """

    def __init__(self, url: str, drop_previous: bool = False) -> None:
        """Initialize the page cache.

        Args:
            url: Database URL (e.g., "sqlite:///cache.db", "postgresql://...")
            drop_previous: Whether to drop existing tables on initialization
        """
        # Configure engine based on database type
        engine_args = {}
        if url.startswith("postgresql"):
            from sqlalchemy.pool import NullPool

            engine_args["poolclass"] = NullPool

        self._engine = create_engine(url, **engine_args)
        self._session = sessionmaker(bind=self.engine)

        # Instance-specific tracking of registered page types
        self._registered_types: set[str] = set()
        self._table_mapping: Dict[str, str] = {}
        self._page_classes: Dict[str, Type[Page]] = {}
        
        # Store invalidator functions for cache validation
        self._invalidators: Dict[str, Callable[[Page], bool]] = {}

        # Initialize provenance tracker
        self._provenance = ProvenanceTracker(self)

        # Ensure relationships table exists
        Base.metadata.create_all(
            self.engine,
            tables=[cast(Table, PageRelationships.__table__)],
            checkfirst=True,
        )

        # Reset database if requested
        if drop_previous:
            self._reset()

    def _reset(self) -> None:
        """Reset the database by dropping all tables and clearing registries."""
        Base.metadata.drop_all(self.engine)

        # Clear registries for clean state
        clear_table_registry()
        self._registered_types.clear()
        self._table_mapping.clear()
        self._page_classes.clear()

        logger.debug("Reset database and cleared all registries")

    def _convert_entity_to_page(self, entity: Any, page_class: Type[P]) -> P:
        """Convert a database entity back to a Page instance.

        Args:
            entity: The SQLAlchemy entity from the database
            page_class: The Page class to convert to

        Returns:
            Page instance of the specified type
        """
        # Reconstruct full URI from uri_prefix and version
        full_uri_string = f"{entity.uri_prefix}@{entity.version}"
        page_data = {"uri": PageURI.parse(full_uri_string)}

        for field_name, field_info in page_class.model_fields.items():
            if field_name not in ("uri",):
                value = getattr(entity, field_name)
                # Deserialize stored values back to original types
                converted_value = deserialize_from_storage(value, field_info.annotation)
                page_data[field_name] = converted_value

        return page_class(**page_data)

    def register_page_type(self, page_type: Type[P]) -> None:
        """Register a page type for caching.

        This creates the necessary SQL table structure for the page type
        if it doesn't already exist.

        Args:
            page_type: Page class to register for caching
        """
        type_name = page_type.__name__
        if type_name in self._registered_types:
            return  # Already registered in this instance

        # Create or reuse the table class
        table_class = create_page_table(page_type)
        self._table_mapping[type_name] = table_class.__tablename__

        # Create the table in the database if it doesn't exist
        table_class.metadata.create_all(self.engine, checkfirst=True)

        # Mark as registered in this instance
        self._registered_types.add(type_name)
        # Store the page class for easier reconstruction
        self._page_classes[type_name] = page_type

        logger.debug(f"Registered page type {type_name}")

    def register_invalidator(self, page_type: Type[P], invalidator: Callable[[P], bool]) -> None:
        """Register an invalidator function for a page type.

        Args:
            page_type: Page class to register invalidator for
            invalidator: Function that takes a page and returns True if valid, False if invalid
        """
        type_name = page_type.__name__
        self._invalidators[type_name] = invalidator
        logger.debug(f"Registered invalidator for page type {type_name}")

    def store_page(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page in the cache with optional provenance tracking.

        If the page already exists (same URI), it will be updated.
        Otherwise, a new record will be created.

        Args:
            page: Page instance to store
            parent_uri: Optional parent URI for provenance tracking. If provided,
                        this overrides any parent_uri set on the page instance.

        Returns:
            True if page was newly created, False if updated

        Raises:
            ProvenanceError: If provenance tracking pre-checks fail
        """
        # Use provided parent_uri or fall back to page's parent_uri
        effective_parent_uri = parent_uri or page.parent_uri

        # If we have a parent URI, perform provenance pre-checks
        if effective_parent_uri is not None:
            self._provenance.validate_provenance(page, effective_parent_uri)

            # Update the page's parent_uri to the effective value
            if parent_uri is not None:
                page.parent_uri = parent_uri

        page_type_name = page.__class__.__name__
        if page_type_name not in self._registered_types:
            self.register_page_type(page.__class__)

        table_registry = get_table_registry()
        table_class = table_registry[page_type_name]

        with self.get_session() as session:
            # Check if page already exists using composite key
            existing = (
                session.query(table_class)
                .filter_by(uri_prefix=page.uri.prefix, version=page.uri.version)
                .first()
            )

            if existing:
                # Pages are immutable - do not allow updates
                from .exceptions import PageCacheError

                raise PageCacheError(
                    f"Page with URI {page.uri} already exists and cannot be updated"
                )
            else:
                # Create new page record with split URI
                page_data = {"uri_prefix": page.uri.prefix, "version": page.uri.version}
                for field_name in page.__class__.model_fields:
                    if field_name not in ("uri",):
                        value = getattr(page, field_name)
                        # Serialize complex objects for storage
                        page_data[field_name] = serialize_for_storage(value)

                page_entity = table_class(**page_data)
                session.add(page_entity)

                # Store relationship if parent_uri exists
                if effective_parent_uri is not None:
                    relationship = PageRelationships(
                        source_uri=str(page.uri),
                        relationship_type="parent",
                        target_uri=str(effective_parent_uri),
                    )
                    session.add(relationship)

                try:
                    session.commit()
                    return True
                except IntegrityError:
                    session.rollback()
                    return False

    def get_page_by_uri_any_type(self, uri: PageURI) -> Optional[Page]:
        """Get a page by URI regardless of its type.

        Args:
            uri: The URI to look up

        Returns:
            Page instance if found and valid, None otherwise
        """
        table_registry = get_table_registry()

        # Check all registered page types
        for page_type_name in self._registered_types:
            if (
                page_type_name in table_registry
                and page_type_name in self._page_classes
            ):
                table_class = table_registry[page_type_name]
                page_class = self._page_classes[page_type_name]

                with self.get_session() as session:
                    entity = (
                        session.query(table_class)
                        .filter_by(uri_prefix=uri.prefix, version=uri.version)
                        .first()
                    )

                    if entity:
                        # Check if page is marked as valid in cache
                        if not entity.valid:
                            logger.debug(f"Page marked as invalid in cache: {uri}")
                            return None
                            
                        page = self._convert_entity_to_page(entity, page_class)
                        
                        # Validate page and ancestors using invalidators
                        if not self._validate_page_and_ancestors(page):
                            return None
                            
                        return page
        return None

    def get_page(self, page_type: Type[P], uri: PageURI) -> Optional[P]:
        """Retrieve a page by its type and URI.

        Args:
            page_type: The Page class type to retrieve
            uri: The PageURI to look up

        Returns:
            Page instance of the requested type if found and valid, None otherwise
        """
        page_type_name = page_type.__name__
        table_registry = get_table_registry()

        if page_type_name not in table_registry:
            return None

        table_class = table_registry[page_type_name]

        with self.get_session() as session:
            entity = (
                session.query(table_class)
                .filter_by(uri_prefix=uri.prefix, version=uri.version)
                .first()
            )

            if entity:
                # Check if page is marked as valid in cache
                if not entity.valid:
                    logger.debug(f"Page marked as invalid in cache: {uri}")
                    return None
                    
                page = self._convert_entity_to_page(entity, page_type)
                
                # Validate page and ancestors using invalidators
                if not self._validate_page_and_ancestors(page):
                    return None
                    
                return page
            return None

    def get_latest_version(self, page_type: Type[P], uri_prefix: str) -> Optional[int]:
        """Get the latest version number for a URI prefix.

        Args:
            page_type: The Page class type to query
            uri_prefix: The URI prefix (without version) to look up

        Returns:
            Latest version number if found, None otherwise
        """
        page_type_name = page_type.__name__
        table_registry = get_table_registry()

        if page_type_name not in table_registry:
            return None

        table_class = table_registry[page_type_name]

        with self.get_session() as session:
            # Query for the maximum version for this prefix
            result = (
                session.query(table_class.version)
                .filter_by(uri_prefix=uri_prefix)
                .order_by(table_class.version.desc())
                .first()
            )

            return result[0] if result else None

    def get_latest_page(self, page_type: Type[P], uri_prefix: str) -> Optional[P]:
        """Get the latest version of a page for a URI prefix.

        Args:
            page_type: The Page class type to retrieve
            uri_prefix: The URI prefix (without version) to look up

        Returns:
            Latest valid version of the page if found, None otherwise
        """
        latest_version = self.get_latest_version(page_type, uri_prefix)
        if latest_version is None:
            return None

        # Reconstruct the full URI with the latest version
        full_uri = PageURI.parse(f"{uri_prefix}@{latest_version}")
        return self.get_page(page_type, full_uri)

    def find_pages_by_attribute(
        self,
        page_type: Type[P],
        query_filter: Callable[[Any], Any],
    ) -> List[P]:
        """Find pages of a given type that match a SQLAlchemy query filter.

        This method provides type-safe querying using SQLAlchemy expressions.
        You can use lambda functions for simple queries or direct SQLAlchemy
        expressions for more complex cases.

        Args:
            page_type: Page class type to query
            query_filter: Either a callable that takes the table class and returns
                         a filter expression, or a SQLAlchemy filter expression

        Returns:
            List of matching Page instances of the requested type

        Examples:
            # Simple equality check
            users = cache.find_pages_by_attribute(
                UserPage,
                lambda t: t.email == "test@example.com"
            )

            # Pattern matching
            users = cache.find_pages_by_attribute(
                UserPage,
                lambda t: t.name.ilike("%john%")
            )

            # Complex conditions
            users = cache.find_pages_by_attribute(
                UserPage,
                lambda t: (t.age > 18) & (t.email.like("%@company.com"))
            )
        """
        page_type_name = page_type.__name__
        table_registry = get_table_registry()

        if page_type_name not in table_registry:
            return []

        table_class = table_registry[page_type_name]

        with self.get_session() as session:
            query = session.query(table_class)

            # Apply the filter based on its type
            if callable(query_filter):
                # Lambda function that takes table class and returns filter
                filter_expr = query_filter(table_class)
                query = query.filter(filter_expr)
            else:
                # Direct SQLAlchemy filter expression
                query = query.filter(query_filter)

            # Only return valid pages
            query = query.filter(table_class.valid == True)

            entities = query.all()
            results = []

            # Convert database entities back to Page instances and validate
            for entity in entities:
                page = self._convert_entity_to_page(entity, page_type)
                
                # Validate page and ancestors using invalidators
                if self._validate_page_and_ancestors(page):
                    results.append(page)

            return results

    def get_table_class(self, page_type: Type[P]) -> Any:
        """Get the SQLAlchemy table class for a page type.

        This is useful for creating direct filter expressions when you need
        more control over the query construction.

        Args:
            page_type: Page class type

        Returns:
            SQLAlchemy table class (declarative model)

        Raises:
            ValueError: If page type is not registered

        Example:
            table = cache.get_table_class(UserPage)
            users = cache.find_pages_by_attribute(
                UserPage,
                table.email.in_(["user1@example.com", "user2@example.com"])
            )
        """
        page_type_name = page_type.__name__
        table_registry = get_table_registry()

        if page_type_name not in table_registry:
            raise ValueError(f"Page type {page_type_name} not registered")
        return table_registry[page_type_name]

    # Provenance tracking methods (delegated to ProvenanceTracker)
    def _validate_provenance(self, page: Page, parent_uri: PageURI) -> None:
        """Validate provenance tracking pre-checks."""
        self._provenance.validate_provenance(page, parent_uri)

    def _check_for_cycles(
        self,
        child_uri: PageURI,
        parent_uri: PageURI,
        visited: Optional[set[PageURI]] = None,
    ) -> None:
        """Check if adding a parent-child relationship would create a cycle."""
        self._provenance.check_for_cycles(child_uri, parent_uri, visited)

    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all pages that have the specified page as their parent."""
        return self._provenance.get_children(parent_uri)

    def get_provenance_chain(self, page_uri: PageURI) -> List[Page]:
        """Get the full provenance chain for a page (from root to the specified page)."""
        return self._provenance.get_provenance_chain(page_uri)

    # Properties and utility methods
    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine instance."""
        return self._engine

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy session instance

        Note:
            Remember to close the session when done, or use it in a context manager.
        """
        return self._session()

    @property
    def registered_page_types(self) -> List[str]:
        """Get list of page type names registered in this cache instance."""
        return list(self._registered_types)

    @property
    def table_mapping(self) -> Dict[str, str]:
        """Get mapping from page type names to database table names."""
        return self._table_mapping.copy()

    @property
    def table_registry(self) -> Dict[str, Any]:
        """Get the current table registry."""
        return get_table_registry()

    @property
    def page_classes(self) -> Dict[str, Type[Page]]:
        """Get the registered page classes."""
        return self._page_classes.copy()

    def invalidate_page(self, uri: PageURI) -> bool:
        """Mark a specific page as invalid in the cache.

        Args:
            uri: URI of the page to invalidate

        Returns:
            True if page was found and invalidated, False if not found
        """
        table_registry = get_table_registry()

        # Find which table contains this page
        for page_type_name in self._registered_types:
            if page_type_name in table_registry:
                table_class = table_registry[page_type_name]

                with self.get_session() as session:
                    result = session.execute(
                        update(table_class)
                        .where(
                            table_class.uri_prefix == uri.prefix,
                            table_class.version == uri.version,
                        )
                        .values(valid=False)
                    )
                    session.commit()

                    if result.rowcount > 0:
                        logger.debug(f"Invalidated page: {uri}")
                        return True

        logger.debug(f"Page not found for invalidation: {uri}")
        return False

    def invalidate_pages_by_prefix(self, uri_prefix: str) -> int:
        """Mark all versions of pages with the given prefix as invalid.

        Args:
            uri_prefix: URI prefix (without version) to invalidate

        Returns:
            Number of pages invalidated
        """
        table_registry = get_table_registry()
        total_invalidated = 0

        # Invalidate across all registered page types
        for page_type_name in self._registered_types:
            if page_type_name in table_registry:
                table_class = table_registry[page_type_name]

                with self.get_session() as session:
                    result = session.execute(
                        update(table_class)
                        .where(table_class.uri_prefix == uri_prefix)
                        .values(valid=False)
                    )
                    session.commit()
                    total_invalidated += result.rowcount

        logger.debug(f"Invalidated {total_invalidated} pages with prefix: {uri_prefix}")
        return total_invalidated

    def _validate_page_and_ancestors(self, page: Page) -> bool:
        """Validate a page and its ancestors using registered invalidators.

        This method checks:
        1. If the page itself is valid according to its invalidator
        2. If all ancestors in the provenance chain are valid

        Args:
            page: Page to validate

        Returns:
            True if page and all ancestors are valid, False otherwise
        """
        # First, validate the page itself
        page_type_name = page.__class__.__name__
        if page_type_name in self._invalidators:
            invalidator = self._invalidators[page_type_name]
            if not invalidator(page):
                logger.debug(f"Page failed validation: {page.uri}")
                # Mark as invalid in cache
                self.invalidate_page(page.uri)
                return False

        # Then validate all ancestors
        if page.parent_uri is not None:
            try:
                provenance_chain = self.get_provenance_chain(page.uri)
                # Remove the current page from the chain (it's always the last one)
                ancestor_pages = provenance_chain[:-1] if provenance_chain else []
                
                for ancestor in ancestor_pages:
                    ancestor_type_name = ancestor.__class__.__name__
                    if ancestor_type_name in self._invalidators:
                        ancestor_invalidator = self._invalidators[ancestor_type_name]
                        if not ancestor_invalidator(ancestor):
                            logger.debug(f"Ancestor page failed validation: {ancestor.uri}")
                            # Mark ancestor as invalid in cache
                            self.invalidate_page(ancestor.uri)
                            # Also mark current page as invalid since its ancestor is invalid
                            self.invalidate_page(page.uri)
                            return False
            except Exception as e:
                logger.warning(f"Error validating provenance chain for {page.uri}: {e}")
                # If we can't validate ancestors, consider the page invalid to be safe
                return False

        return True
