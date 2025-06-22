from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, TypeVar

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse

from .page_cache import PageCache
from .service import Service

logger = logging.getLogger(__name__)

# Type for page handler functions
PageHandler = Callable[..., Page]
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

    def create_page_uri(self, type_name: str, id: str, version: int = 1) -> PageURI:
        """Create a PageURI with this context's root.

        Args:
            type_name: Type name for the page
            id: Unique identifier
            version: Version number (defaults to 1)

        Returns:
            PageURI object
        """
        return PageURI(root=self.root, type=type_name, id=id, version=version)

    def handler(self, page_type: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator to register a page handler function for a specific page type.

        Usage:
            @ctx.handler(EmailDocument)
            def handle_email(email_id: str) -> EmailDocument:
                # Make API calls, parse, return document
                return EmailDocument(...)

            # With aliases:
            @ctx.handler(EmailPage, aliases=["Email", "EmailMessage"])
            def handle_email(email_id: str) -> EmailPage:
                return EmailPage(...)
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            self.register_handler(page_type, func)
            return func

        return decorator

    def get_page(self, page_uri: str | PageURI) -> Page:
        """Retrieve a page by routing to the appropriate service handler.

        The page may be retrieved from cache or created fresh by the service.
        Cache management is handled by individual services.
        """
        # Parse URI if it's a string
        if isinstance(page_uri, str):
            page_uri = PageURI.parse(page_uri)

        if page_uri.type not in self._page_handlers:
            raise RuntimeError(f"No page handler registered for type: {page_uri.type}")

        handler = self._page_handlers[page_uri.type]
        # Call handler with just the id - handlers are responsible for cache management
        return handler(page_uri.id)

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
    ) -> None:
        """
        Register a page handler function for a specific type name.

        Args:
            type_name: String identifier for the page type
            handler_func: Function that takes minimal input and returns a complete Page

        Usage:
            def handle_email(email_id: str) -> EmailPage:
                # Make API calls, parse, return document
                return EmailPage(...)

            ctx.register_handler("email", handle_email)
        """
        if type_name in self._page_handlers:
            raise RuntimeError(f"Page handler already registered for type: {type_name}")

        self._page_handlers[type_name] = handler_func

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
