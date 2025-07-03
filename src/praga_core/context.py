from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union, get_type_hints

from praga_core.action_executor import ActionExecutor, ActionFunction
from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse

from .page_cache import PageCache
from .page_router import HandlerFn, PageRouter
from .service import Service

logger = logging.getLogger(__name__)


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
        self._services: Dict[str, Service] = {}
        if cache_url is None:
            cache_url = "sqlite:///:memory:"
        self._page_cache = PageCache(cache_url)
        self._router = PageRouter(self._page_cache)
        self._action_executor = ActionExecutor(self)

    def route(self, path: str, cache: bool = True) -> Callable[[HandlerFn], HandlerFn]:
        """Decorator to register a page handler.

        Args:
            path: The route path for this handler
            cache: Whether to enable caching for this handler (default: True)

        Example:
            @context.route("emails")
            def handle_emails(uri: PageURI) -> EmailPage:
                ...
        """
        return self._router.route(path, cache)

    def action(self, name: str | None = None) -> Callable[[ActionFunction], ActionFunction]:
        """Decorator to register an action function.

        Args:
            name: Optional name for the action. If not provided, uses function name.

        Example:
            @context.action()
            def mark_email_read(email: EmailPage) -> bool:
                email.read = True
                return True
        """
        def decorator(func: ActionFunction) -> ActionFunction:
            action_name = name if name is not None else func.__name__
            self._action_executor.register_action(action_name, func)
            return func
        return decorator

    def register_action(self, name: str, func: ActionFunction) -> None:
        """Register an action function directly.
        
        Args:
            name: Name of the action
            func: Action function that takes Page (or subclass) as first param and returns bool
        """
        self._action_executor.register_action(name, func)

    def invoke_action(self, name: str, raw_input: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Invoke an action by name.
        
        Args:
            name: Name of the action to invoke
            raw_input: Input arguments
            
        Returns:
            Dict with 'success' key and boolean value
        """
        return self._action_executor.invoke_action(name, raw_input)

    @property
    def actions(self) -> Dict[str, ActionFunction]:
        """Get all registered actions."""
        return self._action_executor.actions

    @property  
    def _page_handlers(self) -> Dict[str, HandlerFn]:
        """Get all registered page handlers (for MCP compatibility)."""
        return self._router._handlers

    def validator(self, func: Callable[[Page], bool]) -> Callable[[Page], bool]:
        """Register a validator function for a specific page type.

        Example:
            @context.validator
            def validate_email(page: EmailPage) -> bool:
                ...
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
        def validator_wrapper(page: Page) -> bool:
            if not isinstance(page, page_type):
                return False
            return func(page)  # type: ignore

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
            return self._router._create_page_uri(page_type, self.root, type_path, id)
        return PageURI(root=self.root, type=type_path, id=id, version=version)

    def get_page(self, page_uri: str | PageURI) -> Page:
        """Retrieve a page by routing to the appropriate service handler.

        First checks cache if caching is enabled for the page type.
        If not cached or caching disabled, calls the handler to generate the page.
        """
        if isinstance(page_uri, str):
            page_uri = PageURI.parse(page_uri)
        return self._router.get_page(page_uri)

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
        """Search for pages using the provided retriever.

        Args:
            instruction: The search instruction/query
            retriever: The retriever agent to use for search

        Returns:
            List[PageReference]: List of page references matching the search
        """
        return retriever.search(instruction)

    def _resolve_references(self, results: List[PageReference]) -> List[PageReference]:
        """Resolve references to pages by calling get_page."""
        for ref in results:
            ref.page = self.get_page(ref.uri)
            assert ref.page is not None
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


def action(
    name: str | None = None
) -> Callable[[ActionFunction], ActionFunction]:
    """
    Standalone @action decorator for functions that will be registered later.
    
    This decorator marks a function as an action but doesn't register it immediately.
    The function can be registered later with a ServerContext.
    
    Args:
        name: Optional name for the action. If not provided, uses function name.

    Example:
        @action()
        def mark_email_read(email: EmailPage) -> bool:
            email.read = True
            return True
            
        # Later, register with context:
        context.register_action("mark_email_read", mark_email_read)
    """
    def decorator(func: ActionFunction) -> ActionFunction:
        # Mark the function as an action for later registration
        func._praga_action_name = name or func.__name__  # type: ignore[attr-defined]
        func._praga_is_action = True  # type: ignore[attr-defined]
        return func
    return decorator
