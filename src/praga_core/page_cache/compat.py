"""Backward compatibility adapter for PageCache.

This provides the old PageCache interface while using the new SimplePageCache
implementation under the hood. This allows for seamless migration.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..types import Page, PageURI
from .simple_core import SimplePageCache

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)


class PageCache:
    """Backward compatibility wrapper around SimplePageCache.

    This class provides the exact same interface as the old complex PageCache
    but uses the new simplified implementation under the hood.
    """

    def __init__(self, url: str, drop_previous: bool = False) -> None:
        """Initialize the page cache with backward compatibility."""
        self._simple_cache = SimplePageCache(url, drop_previous)

    # Backward compatibility methods - delegate to SimplePageCache
    def store_page(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page (backward compatibility method)."""
        return self._simple_cache.store(page, parent_uri)

    def get_page(self, page_type: Type[P], uri: PageURI) -> Optional[P]:
        """Get a page by type and URI (backward compatibility method)."""
        return self._simple_cache.get(page_type, uri)

    def get_latest_page(self, page_type: Type[P], uri_prefix: str) -> Optional[P]:
        """Get latest page version (backward compatibility method)."""
        return self._simple_cache.get_latest(page_type, uri_prefix)

    def find_pages_by_attribute(
        self,
        page_type: Type[P],
        query_filter: Callable[[Any], Any],
    ) -> List[P]:
        """Find pages by attribute (backward compatibility method)."""
        return self._simple_cache.find(page_type).where(query_filter).all()

    def register_page_type(self, page_type: Type[P]) -> None:
        """Register page type (backward compatibility - now automatic)."""
        # Registration is now automatic, but we still need to trigger it for compatibility
        self._simple_cache._registry.ensure_registered(page_type)
        logger.debug(f"Registered page type for compatibility: {page_type.__name__}")

    def register_invalidator(
        self, page_type: Type[P], invalidator: Callable[[P], bool]
    ) -> None:
        """Register invalidator function (backward compatibility method)."""
        self._simple_cache.register_validator(page_type, invalidator)

    def invalidate_page(self, uri: PageURI) -> bool:
        """Invalidate a specific page (backward compatibility method)."""
        return self._simple_cache.invalidate(uri)

    def invalidate_pages_by_prefix(self, uri_prefix: str) -> int:
        """Invalidate pages by prefix (backward compatibility method)."""
        return self._simple_cache.invalidate_prefix(uri_prefix)

    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get child pages (backward compatibility method)."""
        return self._simple_cache.get_children(parent_uri)

    def get_provenance_chain(self, page_uri: PageURI) -> List[Page]:
        """Get provenance chain (backward compatibility method)."""
        return self._simple_cache.get_lineage(page_uri)

    # Additional backward compatibility methods that may be used in tests or elsewhere
    def get_page_by_uri_any_type(self, uri: PageURI) -> Optional[Page]:
        """Get page by URI regardless of type (backward compatibility)."""
        # In the new system, we'd need to try all registered types
        # For now, let's delegate to the underlying implementation
        # This is a bit more complex to implement cleanly, so we'll use a simple approach
        registered_types = self._simple_cache._registry.registered_types

        for page_type in registered_types:
            try:
                page = self._simple_cache.get(page_type, uri)
                if page is not None:
                    return page
            except Exception:
                continue
        return None

    def get_latest_version(self, page_type: Type[P], uri_prefix: str) -> Optional[int]:
        """Get latest version number (backward compatibility method)."""
        page = self._simple_cache.get_latest(page_type, uri_prefix)
        return page.uri.version if page else None

    def get_table_class(self, page_type: Type[P]) -> Any:
        """Get table class for page type (backward compatibility method)."""
        return self._simple_cache._registry.get_table_class(page_type)

    # Properties for backward compatibility
    @property
    def engine(self) -> Engine:
        """Get SQLAlchemy engine (backward compatibility property)."""
        return self._simple_cache.engine

    def get_session(self) -> Session:
        """Get database session (backward compatibility method)."""
        return self._simple_cache.get_session()

    @property
    def registered_page_types(self) -> List[str]:
        """Get registered page type names (backward compatibility property)."""
        return self._simple_cache._registry.registered_type_names

    @property
    def table_mapping(self) -> Dict[str, str]:
        """Get table mapping (backward compatibility property)."""
        # Reconstruct table mapping from registry
        mapping = {}
        for type_name in self._simple_cache._registry.registered_type_names:
            try:
                page_type = self._simple_cache._registry.get_page_class(type_name)
                table_class = self._simple_cache._registry.get_table_class(page_type)
                mapping[type_name] = table_class.__tablename__
            except Exception:
                continue
        return mapping

    @property
    def table_registry(self) -> Dict[str, Any]:
        """Get table registry (backward compatibility property)."""
        from .schema import get_table_registry

        return get_table_registry()

    @property
    def page_classes(self) -> Dict[str, Type[Page]]:
        """Get page classes (backward compatibility property)."""
        classes = {}
        for type_name in self._simple_cache._registry.registered_type_names:
            try:
                classes[type_name] = self._simple_cache._registry.get_page_class(
                    type_name
                )
            except Exception:
                continue
        return classes

    @property
    def _invalidators(self) -> Dict[str, Callable[[Page], bool]]:
        """Get invalidators (backward compatibility property - deprecated)."""
        logger.warning(
            "_invalidators property is deprecated - use register_validator instead"
        )
        return self._simple_cache._validator._validators

    # Internal methods that might be called by legacy code (marked as deprecated)
    def _validate_page_and_ancestors(self, page: Page) -> bool:
        """Validate page and ancestors (backward compatibility - deprecated)."""
        logger.warning(
            "_validate_page_and_ancestors is deprecated - validation is now automatic"
        )

        # First, validate the page itself
        if not self._simple_cache._validator.is_valid(page):
            self._simple_cache.invalidate(page.uri)
            return False

        # Then validate all ancestors if page has a parent and we have validators
        if page.parent_uri is not None and self._simple_cache._validator._validators:
            try:
                provenance_chain = self.get_provenance_chain(page.uri)
                # Remove the current page from the chain (it's always the last one)
                ancestor_pages = provenance_chain[:-1] if provenance_chain else []

                for ancestor in ancestor_pages:
                    if not self._simple_cache._validator.is_valid(ancestor):
                        logger.debug(f"Ancestor page failed validation: {ancestor.uri}")
                        # Mark ancestor as invalid in cache
                        self._simple_cache.invalidate(ancestor.uri)
                        # Also mark current page as invalid since its ancestor is invalid
                        self._simple_cache.invalidate(page.uri)
                        return False
            except Exception as e:
                logger.warning(f"Error validating provenance chain for {page.uri}: {e}")
                # If we can't validate ancestors, only fail if we have validators registered
                if self._simple_cache._validator._validators:
                    return False

        return True

    def _get_page_by_uri_any_type_no_validation(self, uri: PageURI) -> Optional[Page]:
        """Get page without validation (backward compatibility - deprecated)."""
        logger.warning("_get_page_by_uri_any_type_no_validation is deprecated")
        # Return the page without validation
        registered_types = self._simple_cache._registry.registered_types
        for page_type in registered_types:
            try:
                # Use storage directly to bypass validation
                page = self._simple_cache._storage.get(page_type, uri)
                if page is not None:
                    return page
            except Exception:
                continue
        return None

    def _get_page_by_uri_any_type_ignore_validity(self, uri: PageURI) -> Optional[Page]:
        """Get page ignoring validity (backward compatibility - deprecated)."""
        logger.warning("_get_page_by_uri_any_type_ignore_validity is deprecated")
        # This would require more complex implementation to ignore validity flags
        # For compatibility, we'll use the same approach as no_validation
        return self._get_page_by_uri_any_type_no_validation(uri)

    # Provenance methods for backward compatibility
    def _validate_provenance(self, page: Page, parent_uri: PageURI) -> None:
        """Validate provenance (backward compatibility - deprecated)."""
        logger.warning("_validate_provenance is deprecated - now handled automatically")
        self._simple_cache._provenance.validate_relationship(page, parent_uri)

    def _check_for_cycles(
        self,
        child_uri: PageURI,
        parent_uri: PageURI,
        visited: Optional[Set[PageURI]] = None,
    ) -> None:
        """Check for cycles (backward compatibility - deprecated)."""
        logger.warning("_check_for_cycles is deprecated - now handled automatically")
        self._simple_cache._provenance._check_for_cycles(child_uri, parent_uri, visited)

    # New methods from SimplePageCache (can be used directly)
    def store(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page (new simplified method)."""
        return self._simple_cache.store(page, parent_uri)

    def get(self, page_type: Type[P], uri: PageURI) -> Optional[P]:
        """Get a page (new simplified method)."""
        return self._simple_cache.get(page_type, uri)

    def get_latest(self, page_type: Type[P], uri_prefix: str) -> Optional[P]:
        """Get latest page (new simplified method)."""
        return self._simple_cache.get_latest(page_type, uri_prefix)

    def find(self, page_type: Type[P]):
        """Start building a query (new simplified method)."""
        return self._simple_cache.find(page_type)

    def register_validator(
        self, page_type: Type[P], validator: Callable[[P], bool]
    ) -> None:
        """Register validator (new simplified method)."""
        return self._simple_cache.register_validator(page_type, validator)

    def invalidate(self, uri: PageURI) -> bool:
        """Invalidate page (new simplified method)."""
        return self._simple_cache.invalidate(uri)

    def invalidate_prefix(self, uri_prefix: str) -> int:
        """Invalidate by prefix (new simplified method)."""
        return self._simple_cache.invalidate_prefix(uri_prefix)

    def get_lineage(self, page_uri: PageURI) -> List[Page]:
        """Get lineage (new simplified method)."""
        return self._simple_cache.get_lineage(page_uri)
