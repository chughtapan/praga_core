from __future__ import annotations

from typing import Callable, Dict, List, Optional, Type, TypeVar, Union, overload

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference

# Type for page handler functions
PageHandler = Callable[..., Page]
T = TypeVar("T", bound=Page)


class ServerContext:
    """Central server context that acts as single source of truth for caching and state."""

    def __init__(self) -> None:
        """Initialize server context without requiring a retriever."""
        self._retriever: Optional[RetrieverAgentBase] = None
        self._page_handlers: Dict[Type[Page], PageHandler] = {}
        self._page_cache: Dict[str, Page] = {}

    def _resolve_page_type(self, page_type: Union[Type[Page], str]) -> Type[Page]:
        """Resolve a page type from either a Type or string to the actual Type."""
        if isinstance(page_type, str):
            # Find the actual type from registered handlers
            for registered_type in self._page_handlers:
                if registered_type.__name__ == page_type:
                    return registered_type
            raise RuntimeError(f"No page handler registered for type: {page_type}")
        return page_type

    @overload
    def get_page_uri(self, page_ref_or_id: PageReference) -> str: ...

    @overload
    def get_page_uri(
        self, page_ref_or_id: str, page_type: Union[Type[Page], str]
    ) -> str: ...

    def get_page_uri(
        self,
        page_ref_or_id: Union[PageReference, str],
        page_type: Optional[Union[Type[Page], str]] = None,
    ) -> str:
        """Get the URI for a page."""
        if isinstance(page_ref_or_id, PageReference):
            return f"{page_ref_or_id.type}:{page_ref_or_id.id}"
        else:
            # page_ref_or_id is a string (page_id)
            if page_type is None:
                raise ValueError(
                    "page_type must be provided when first argument is a page_id"
                )
            resolved_type = self._resolve_page_type(page_type)
            return f"{resolved_type.__name__}:{page_ref_or_id}"

    def handler(
        self, page_type: Type[T]
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        """Decorator to register a page handler function for a specific page type.

        Usage:
            @ctx.handler(EmailDocument)
            def handle_email(email_id: str) -> EmailDocument:
                # Make API calls, parse, return document
                return EmailDocument(...)
        """

        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            self.register_handler(func, page_type)
            return func

        return decorator

    def _create_page(self, page_id: str, page_type: Type[T]) -> T:
        """
        Create a page using the registered handler for the given type."""
        if page_type not in self._page_handlers:
            raise RuntimeError(
                f"No page handler registered for type: {page_type.__name__}"
            )

        handler = self._page_handlers[page_type]
        page: T = handler(page_id)  # type: ignore[assignment]
        return page

    def _cache_set_page(self, page: Page) -> None:
        """Store a page in the cache using its URI."""
        uri = self.get_page_uri(page.id, type(page))
        self._page_cache[uri] = page

    def _cache_get_page(self, uri: str) -> Optional[Page]:
        """Get a page from the cache using its URI."""
        return self._page_cache.get(uri, None)

    def get_page(self, page_uri: str) -> Page:
        """Retrieve a document from the cache or create it if not found."""

        page = self._cache_get_page(page_uri)
        if page is None:
            # Not in cache, create it
            type_name, page_id = page_uri.split(":", 1)
            resolved_type = self._resolve_page_type(type_name)
            page = self._create_page(page_id, resolved_type)
            self._cache_set_page(page)
        return page

    def search(
        self,
        instruction: str,
        retriever: Optional[RetrieverAgentBase] = None,
        resolve_references: bool = True,
    ) -> List[PageReference]:
        """Execute search using the provided retriever."""

        active_retriever = retriever or self.retriever
        if not active_retriever:
            raise RuntimeError(
                "No RetrieverAgent available. Either set context.retriever or pass retriever parameter."
            )

        results = self._search(instruction, active_retriever)
        if resolve_references:
            results = self._resolve_references(results)
        return results

    def _search(
        self, instruction: str, retriever: RetrieverAgentBase
    ) -> List[PageReference]:
        """Search for pages using the provided retriever."""
        return retriever.search(instruction)

    def _resolve_references(self, results: List[PageReference]) -> List[PageReference]:
        """Resolve references to pages in the cache."""
        for ref in results:
            uri = self.get_page_uri(ref)
            ref.page = self.get_page(uri)
        return results

    def register_handler(
        self, handler_func: Callable[..., T], page_type: Type[T]
    ) -> None:
        """
        Programmatically register a page handler function.

        Args:
            handler_func: Function that takes minimal input and returns a complete Page
            page_type: The page type this handler creates

        Usage:
            def handle_email(email_id: str) -> EmailDocument:
                # Make API calls, parse, return document
                return EmailDocument(...)

            ctx.register_handler(handle_email, EmailDocument)
        """
        if not issubclass(page_type, Page):
            raise RuntimeError(
                f"Page type {page_type.__name__} is not a subclass of Page"
            )
        if page_type in self._page_handlers:
            raise RuntimeError(
                f"Page handler already registered for type: {page_type.__name__}"
            )
        self._page_handlers[page_type] = handler_func

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
