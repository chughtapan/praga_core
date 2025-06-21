from __future__ import annotations

from typing import Callable, Dict, List, Optional, TypeVar

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse

from .page_cache import PageCache

# Type for page handler functions
PageHandler = Callable[..., Page]
T = TypeVar("T", bound=Page)


class ServerContext:
    """Central server context that acts as single source of truth for caching and state."""

    def __init__(self, root: str = "", cache_url: Optional[str] = None) -> None:
        """Initialize server context.

        Args:
            root: Root identifier for this context, used in PageURIs
            cache_url: Optional database URL for PageCache. If None, no persistent cache is used.
        """
        self.root = root
        self._retriever: Optional[RetrieverAgentBase] = None
        self._page_handlers: Dict[str, PageHandler] = {}
        self._page_cache: Dict[str, Page] = {}

        # Initialize SQL-based PageCache if URL provided
        self._sql_cache: Optional[PageCache] = None
        if cache_url:
            self._sql_cache = PageCache(cache_url)

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

    def _create_page(self, page_uri: PageURI) -> Page:
        """Create a page using the registered handler for the given type."""
        if page_uri.type not in self._page_handlers:
            raise RuntimeError(f"No page handler registered for type: {page_uri.type}")

        handler = self._page_handlers[page_uri.type]
        # Call handler with just the id - handlers are responsible for creating proper URIs
        page: Page = handler(page_uri.id)
        return page

    def _cache_set_page(self, page: Page) -> None:
        """Store a page in the cache using its URI string."""
        uri_str = str(page.uri)
        self._page_cache[uri_str] = page

        # Also store in SQL cache if available
        if self._sql_cache is not None:
            self._sql_cache.store_page(page)

    def _cache_get_page(self, uri: str | PageURI) -> Optional[Page]:
        """Get a page from the cache using its URI."""
        uri_str = str(uri)

        # First check in-memory cache
        cached_page = self._page_cache.get(uri_str, None)
        if cached_page is not None:
            return cached_page

        # Then check SQL cache if available
        if self._sql_cache is not None:
            page_uri = PageURI.parse(uri_str)
            # Find the page type from registered handlers
            if page_uri.type in self._page_handlers:
                # We need to infer the page type from the handler
                # This is a bit tricky - we'd need to call the handler to get the type
                # For now, let's skip SQL cache lookup in _cache_get_page
                # and handle it explicitly in other methods
                pass

        return None

    def get_page(self, page_uri: str | PageURI) -> Page:
        """Retrieve a document from the cache or create it if not found."""

        # Parse URI if it's a string
        if isinstance(page_uri, str):
            page_uri = PageURI.parse(page_uri)

        page = self._cache_get_page(page_uri)
        if page is None:
            # Not in cache, create it
            page = self._create_page(page_uri)
            self._cache_set_page(page)
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
        """Resolve references to pages in the cache."""
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

        # Register page type with SQL cache if available
        if self._sql_cache is not None:
            # We need to determine the page type from the handler
            # This is tricky since we don't have the actual type yet
            # We'll defer this until the first page of this type is created
            pass

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
    def sql_cache(self) -> Optional[PageCache]:
        """Get access to the SQL-based page cache."""
        return self._sql_cache
