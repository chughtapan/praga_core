from __future__ import annotations

import logging
from typing import (
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    get_type_hints,
)

from praga_core.action_executor import ActionExecutorMixin
from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse

from .page_cache import PageCache
from .page_router import HandlerFn, PageRouter
from .service import Service

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)


class ServerContext(ActionExecutorMixin):
    """Central server context that acts as single source of truth for caching and state."""

    def __init__(
        self,
        root: str = "",
        cache_url: Optional[str] = None,
        _page_cache: Optional[PageCache] = None,
    ) -> None:
        """Do not use directly. Use `await ServerContext.create(...)` instead."""
        super().__init__()
        self.root = root
        self._retriever: Optional[RetrieverAgentBase] = None
        self._services: Dict[str, Service] = {}
        if _page_cache is not None:
            self._page_cache = _page_cache
        else:
            raise RuntimeError(
                "Use `await ServerContext.create(...)` to instantiate ServerContext."
            )
        self._router = PageRouter(self._page_cache)

    @classmethod
    async def create(
        cls, root: str = "", cache_url: Optional[str] = None
    ) -> "ServerContext":
        if cache_url is None:
            cache_url = "sqlite+aiosqlite:///:memory:"
        page_cache = await PageCache.create(cache_url)
        return cls(root, cache_url, _page_cache=page_cache)

    def route(self, path: str, cache: bool = True) -> Callable[[HandlerFn], HandlerFn]:
        """Decorator to register an async page handler.

        Args:
            path: The route path for this handler
            cache: Whether to enable caching for this handler (default: True)

        Example:
            @context.route("emails")
            async def handle_emails(uri: PageURI) -> EmailPage:
                ...
        """
        return self._router.route(path, cache)

    def validator(
        self, func: Callable[[P], Awaitable[bool]]
    ) -> Callable[[P], Awaitable[bool]]:
        """Decorator to register an async page validator.

        All validators must be async:

        Example:
            @context.validator
            async def validate_email(page: EmailPage) -> bool:
                # Could make API calls, DB queries, etc.
                return await some_async_validation(page.email)
        """
        hints = {
            name: typ for name, typ in get_type_hints(func).items() if name != "return"
        }
        if len(hints) != 1:
            raise RuntimeError("Validator function must have exactly one argument.")
        page_type = next(iter(hints.values()))
        if not isinstance(page_type, type) or not issubclass(page_type, Page):
            raise RuntimeError("Validator function's argument must be a Page subclass.")

        # Create a wrapper that handles the type cast safely
        async def validator_wrapper(page: Page) -> bool:
            if not isinstance(page, page_type):
                return False
            return await func(page)  # type: ignore

        self._page_cache.register_validator(page_type, validator_wrapper)
        return func

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

    async def create_page_uri(
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
            return await self._router._create_page_uri(
                page_type, self.root, type_path, id
            )
        return PageURI(root=self.root, type=type_path, id=id, version=version)

    async def get_page(
        self, page_uri: str | PageURI, allow_stale: bool = False
    ) -> Page:
        """Retrieve a page by routing to the appropriate service handler.

        First checks cache if caching is enabled for the page type.
        If not cached or caching disabled, calls the handler to generate the page.
        """
        if isinstance(page_uri, str):
            page_uri = PageURI.parse(page_uri)
        return await self._router.get_page(page_uri, allow_stale=allow_stale)

    async def get_pages(
        self, page_uris: Sequence[str | PageURI], allow_stale: bool = False
    ) -> List[Page]:
        """Bulk asynchronous page retrieval with parallel execution."""
        parsed_uris = [
            PageURI.parse(uri) if isinstance(uri, str) else uri for uri in page_uris
        ]
        return await self._router.get_pages(parsed_uris, allow_stale=allow_stale)

    async def search(
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

        results = await self._search(instruction, active_retriever)
        if resolve_references:
            results = await self._resolve_references(results)
        return SearchResponse(results=results)

    async def _search(
        self, instruction: str, retriever: RetrieverAgentBase
    ) -> List[PageReference]:
        """Search for pages using the provided retriever.

        Args:
            instruction: The search instruction/query
            retriever: The retriever agent to use for search

        Returns:
            List[PageReference]: List of page references matching the search
        """
        results = await retriever.search(instruction)
        return results

    async def _resolve_references(
        self, results: List[PageReference]
    ) -> List[PageReference]:
        """Resolve references to pages by calling get_page."""
        uris = [ref.uri for ref in results]
        pages = await self.get_pages(uris)
        for ref, page in zip(results, pages):
            ref.page = page
        return results

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
