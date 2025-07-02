from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Type, TypeVar

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse

from .page_cache import PageCache
from .service import Service

logger = logging.getLogger(__name__)

# Type for page handler functions
PageHandler = Callable[..., Page]
# Type for page invalidator functions - takes a Page and returns bool (True = valid, False = invalid)
PageInvalidator = Callable[[Page], bool]
T = TypeVar("T", bound=Page)


class ServerContext:
    """Central server context that acts as single source of truth for caching and state."""

    def __init__(self, root: str = "", cache_url: Optional[str] = None) -> None:
        """Initialize server context.

        Args:
            root: Root identifier for this context, used in PageURIs
            cache_url: Optional database URL for PageCache. If None, uses sqlite in-memory database.
        """
        self.root = root
        self._retriever: Optional[RetrieverAgentBase] = None
        self._page_handlers: Dict[str, PageHandler] = {}
        self._page_invalidators: Dict[str, PageInvalidator] = {}
        self._page_cache_enabled: Dict[str, bool] = {}
        self._services: Dict[str, Service] = {}

        # Initialize SQL-based PageCache (always available)
        if cache_url is None:
            cache_url = "sqlite:///:memory:"
        self._page_cache = PageCache(cache_url)

    def register_service(self, name: str, service: Service) -> None:
        """Register a service with the context."""
        if name in self._services:
            raise RuntimeError(f"Service already registered: {name}")
        self._services[name] = service
        logger.info(f"Registered service: {name}")

    def get_service(self, name: str) -> Service:
        """Get a service by name."""
        if name not in self._services:
            raise RuntimeError(f"No service registered with name: {name}")
        return self._services[name]

    @property
    def services(self) -> Dict[str, Service]:
        """Get all registered services."""
        return self._services.copy()

    def create_page_uri(
        self,
        page_type: Type[Page],
        type_path: str,
        id: str,
        version: Optional[int] = None,
    ) -> PageURI:
        """Create a PageURI with this context's root.

        When version is None, determines the next version number by checking
        the cache for the latest existing version and incrementing it.

        Args:
            page_type: The Page class type
            type_path: String path for the page type (e.g., "email", "calendar_event")
            id: Unique identifier
            version: Version number (defaults to None for auto-increment)

        Returns:
            PageURI object with resolved version number
        """
        if version is None:
            # Create prefix to check for existing versions
            prefix = f"{self.root}/{type_path}:{id}"

            # Get the latest version for this page type and prefix
            latest_version = self._page_cache.get_latest_version(page_type, prefix)

            # If no existing versions found, start with 1. Otherwise increment the latest.
            version = 1 if latest_version is None else (latest_version + 1)

        return PageURI(root=self.root, type=type_path, id=id, version=version)

    def handler(
        self, page_type: str, invalidator: Optional[PageInvalidator] = None, cache: bool = True
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator to register a page handler function for a specific page type.

        Args:
            page_type: String identifier for the page type
            invalidator: Optional function that validates cached pages
            cache: Whether to enable caching for this page type (default: True)

        Usage:
            @ctx.handler("email")
            def handle_email(email_uri: PageURI) -> EmailDocument:
                # Make API calls, parse, return document
                return EmailDocument(...)

            # With invalidator and caching disabled:
            def validate_email(page: EmailPage) -> bool:
                return check_email_still_exists(page)

            @ctx.handler("email", invalidator=validate_email, cache=False)
            def handle_email(email_uri: PageURI) -> EmailPage:
                return EmailPage(...)
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            self.register_handler(page_type, func, invalidator, cache)
            return func

        return decorator

    def _try_get_from_cache(self, page_uri: PageURI) -> Optional[Page]:
        """Try to get a page from cache if caching is enabled for this page type.
        
        Returns the cached page if found, None otherwise.
        """
        # Check if caching is enabled for this page type
        cache_enabled = self._page_cache_enabled.get(page_uri.type, True)
        
        if not cache_enabled:
            return None
            
        # Try to get from cache (determine page type from handler return type)
        handler = self._page_handlers[page_uri.type]
        # We need to inspect the handler's return type annotation to get the Page class
        import typing
        try:
            # Try to get the return type annotation
            if hasattr(handler, '__annotations__') and 'return' in handler.__annotations__:
                page_type = handler.__annotations__['return']
                cached_page = self._page_cache.get(page_type, page_uri)
                if cached_page:
                    logger.debug(f"Found cached page for {page_uri}")
                    # Register invalidator with cache if we have one for this page type
                    if page_uri.type in self._page_invalidators:
                        invalidator = self._page_invalidators[page_uri.type]
                        self._register_invalidator_with_cache(page_type, invalidator)
                    return cached_page
            else:
                logger.debug(f"No return type annotation found for handler {page_uri.type}, skipping cache lookup")
        except Exception as e:
            logger.debug(f"Error checking cache for {page_uri}: {e}, falling back to handler")
        
        return None

    def get_page(self, page_uri: str | PageURI) -> Page:
        """Retrieve a page by routing to the appropriate service handler.

        First checks cache if caching is enabled for the page type.
        If not cached or caching disabled, calls the handler to generate the page.
        """
        # Parse URI if it's a string
        if isinstance(page_uri, str):
            page_uri = PageURI.parse(page_uri)

        if page_uri.type not in self._page_handlers:
            raise RuntimeError(f"No page handler registered for type: {page_uri.type}")

        # Try to get from cache first if caching is enabled
        cached_page = self._try_get_from_cache(page_uri)
        if cached_page:
            return cached_page

        # Not in cache or caching disabled - call handler with full URI
        # Before calling the handler, ensure we have a full URI with version number
        if page_uri.version is None:
            # Need to create a full URI with version number
            # We need to determine the page type from the handler to call create_page_uri
            handler = self._page_handlers[page_uri.type]
            if hasattr(handler, '__annotations__') and 'return' in handler.__annotations__:
                page_type = handler.__annotations__['return']
                page_uri = self.create_page_uri(page_type, page_uri.type, page_uri.id)
        
        handler = self._page_handlers[page_uri.type]
        page = handler(page_uri)

        # Register invalidator with cache if we have one for this page type
        if page_uri.type in self._page_invalidators:
            invalidator = self._page_invalidators[page_uri.type]
            self._register_invalidator_with_cache(page.__class__, invalidator)

        return page

    def search(
        self,
        instruction: str,
        retriever: Optional[RetrieverAgentBase] = None,
        resolve_references: bool = True,
    ) -> SearchResponse:
        """Execute search using the provided retriever."""

        active_retriever = retriever or self.retriever
        if not active_retriever:
            raise RuntimeError(
                "No RetrieverAgent available. Either set context.retriever or pass retriever parameter."
            )

        results = self._search(instruction, active_retriever)
        if resolve_references:
            results = self._resolve_references(results)
        return SearchResponse(results=results)

    def _search(
        self, instruction: str, retriever: RetrieverAgentBase
    ) -> List[PageReference]:
        """Search for pages using the provided retriever."""
        return retriever.search(instruction)

    def _resolve_references(self, results: List[PageReference]) -> List[PageReference]:
        """Resolve references to pages by calling get_page."""
        for ref in results:
            ref.page = self.get_page(ref.uri)
            assert ref.page is not None
        return results

    def register_handler(
        self,
        type_name: str,
        handler_func: Callable[..., Page],
        invalidator_func: Optional[PageInvalidator] = None,
        cache: bool = True,
    ) -> None:
        """
        Register a page handler function for a specific type name.

        Args:
            type_name: String identifier for the page type
            handler_func: Function that takes a PageURI and returns a complete Page
            invalidator_func: Optional function that takes a Page and returns True if valid, False if invalid
            cache: Whether to enable caching for this page type (default: True)

        Usage:
            def handle_email(email_uri: PageURI) -> EmailPage:
                # Make API calls, parse, return document
                return EmailPage(...)

            def validate_email(page: EmailPage) -> bool:
                # Check if email still exists, compare revision, etc.
                return True  # or False if invalid

            ctx.register_handler("email", handle_email, validate_email, cache=True)
        """
        if type_name in self._page_handlers:
            raise RuntimeError(f"Page handler already registered for type: {type_name}")

        self._page_handlers[type_name] = handler_func
        self._page_cache_enabled[type_name] = cache

        if invalidator_func is not None:
            self._page_invalidators[type_name] = invalidator_func

            # Register invalidator with page cache if we have a sample page type
            # We'll need to get the page type from the handler function's return annotation
            # For now, we'll store it and register it when we first encounter a page of this type

    def _register_invalidator_with_cache(
        self, page_type: type, invalidator: PageInvalidator
    ) -> None:
        """Register an invalidator with the page cache for a specific page type."""
        self._page_cache.register_validator(page_type, invalidator)

    @property
    def retriever(self) -> Optional[RetrieverAgentBase]:
        """Get the current retriever agent."""
        return self._retriever

    @retriever.setter
    def retriever(self, retriever: RetrieverAgentBase) -> None:
        """Set the retriever agent."""
        if self._retriever is not None:
            raise RuntimeError("Retriever for this context is already set")
        self._retriever = retriever

    @property
    def page_cache(self) -> PageCache:
        """Get access to the SQL-based page cache."""
        return self._page_cache
