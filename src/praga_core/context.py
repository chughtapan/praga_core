from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, TypeVar, Union, get_origin, get_args, get_type_hints

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse

from .page_cache import PageCache
from .page_router import HandlerFn, PageRouter
from .service import Service

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)

# Action function type - returns boolean for success/failure
ActionFunction = Callable[..., bool]



def _is_action_function(action_function: ActionFunction) -> bool:
    """
    Check if a function is a valid action function.
    
    Action functions should:
    1. Have a Page (or subclass) as the first parameter
    2. Return a boolean
    """
    try:
        type_hints = get_type_hints(action_function)
        
        # Check return type is bool
        return_annotation = type_hints.get("return", None)
        if return_annotation is not bool:
            return False
            
        # Check first parameter is Page or subclass
        sig = inspect.signature(action_function)
        param_names = list(sig.parameters.keys())
        if not param_names:
            return False
            
        first_param = param_names[0]
        first_param_type = type_hints.get(first_param, None)
        
        if first_param_type is None:
            return False
            
        # Check if it's Page or a subclass of Page
        if first_param_type is Page:
            return True
        if isinstance(first_param_type, type) and issubclass(first_param_type, Page):
            return True
            
        return False
    except Exception:
        return False


def _convert_pages_to_uris(args: Dict[str, Any], func: ActionFunction) -> Dict[str, Any]:
    """Convert Page arguments to PageURIs in function arguments."""
    type_hints = get_type_hints(func)
    converted_args = {}
    
    for param_name, value in args.items():
        param_type = type_hints.get(param_name, type(value))
        
        # Handle single Page
        if isinstance(value, Page):
            if hasattr(value, 'uri'):
                converted_args[param_name] = value.uri
            else:
                # If Page doesn't have URI, we can't convert it
                raise ValueError(f"Page parameter '{param_name}' does not have a URI")
        # Handle Sequence[Page] or List[Page]
        elif isinstance(value, (list, tuple)) and value:
            origin = get_origin(param_type)
            args_types = get_args(param_type)
            
            if origin in (list, tuple, Sequence) and args_types and issubclass(args_types[0], Page):
                converted_list = []
                for item in value:
                    if isinstance(item, Page):
                        if hasattr(item, 'uri'):
                            converted_list.append(item.uri)
                        else:
                            raise ValueError(f"Page in parameter '{param_name}' does not have a URI")
                    else:
                        converted_list.append(item)
                converted_args[param_name] = converted_list
            else:
                converted_args[param_name] = value
        # Handle Optional[Page]
        elif value is None:
            origin = get_origin(param_type)
            args_types = get_args(param_type)
            if origin is Union and type(None) in args_types:
                # This is Optional[SomeType]
                non_none_types = [t for t in args_types if t is not type(None)]
                if non_none_types and issubclass(non_none_types[0], Page):
                    converted_args[param_name] = None
                else:
                    converted_args[param_name] = value
            else:
                converted_args[param_name] = value
        else:
            converted_args[param_name] = value
    
    return converted_args


def _convert_uris_to_pages(args: Dict[str, Any], func: ActionFunction, context: 'ServerContext') -> Dict[str, Any]:
    """Convert PageURIs back to Pages using the server context."""
    type_hints = get_type_hints(func)
    converted_args = {}
    
    for param_name, value in args.items():
        param_type = type_hints.get(param_name, type(value))
        
        # Handle single PageURI -> Page
        if isinstance(value, (PageURI, str)):
            # Check if this parameter should be a Page
            if param_type is Page or (isinstance(param_type, type) and issubclass(param_type, Page)):
                page_uri = value if isinstance(value, PageURI) else PageURI.parse(value)
                # Use the context's get_page method which handles routing
                try:
                    page = context.get_page(page_uri)
                    converted_args[param_name] = page
                except Exception as e:
                    raise ValueError(f"Failed to retrieve page for URI '{page_uri}': {e}")
            else:
                converted_args[param_name] = value
        # Handle List[PageURI] -> List[Page]
        elif isinstance(value, (list, tuple)) and value:
            origin = get_origin(param_type)
            args_types = get_args(param_type)
            
            if origin in (list, tuple, Sequence) and args_types and issubclass(args_types[0], Page):
                converted_list = []
                for item in value:
                    if isinstance(item, (PageURI, str)):
                        page_uri = item if isinstance(item, PageURI) else PageURI.parse(item)
                        try:
                            page = context.get_page(page_uri)
                            converted_list.append(page)
                        except Exception as e:
                            raise ValueError(f"Failed to retrieve page for URI '{page_uri}': {e}")
                    else:
                        converted_list.append(item)
                converted_args[param_name] = converted_list
            else:
                converted_args[param_name] = value
        # Handle Optional[PageURI] -> Optional[Page]
        elif value is None:
            converted_args[param_name] = None
        else:
            converted_args[param_name] = value
    
    return converted_args


class ActionExecutor:
    """Manages action functions that can be invoked on pages."""
    
    def __init__(self, context: 'ServerContext'):
        """Initialize the ActionExecutor with a reference to the server context."""
        self._context = context
        self._actions: Dict[str, ActionFunction] = {}
        
    def register_action(self, name: str, func: ActionFunction) -> None:
        """Register an action function.
        
        Args:
            name: Name of the action
            func: Action function that takes Page (or subclass) as first param and returns bool
        """
        if not _is_action_function(func):
            raise TypeError(
                f"Action '{name}' must have a Page (or subclass) as the first parameter "
                f"and return a boolean. Got: {getattr(func, '__annotations__', {})}"
            )
            
        self._actions[name] = func
        logger.info(f"Registered action: {name}")
        
    def get_action(self, name: str) -> ActionFunction:
        """Get an action function by name."""
        if name not in self._actions:
            raise ValueError(f"Action '{name}' not found")
        return self._actions[name]
        
    def invoke_action(self, name: str, raw_input: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Invoke an action by name.
        
        Args:
            name: Name of the action to invoke
            raw_input: Input arguments - if string, used as first parameter
            
        Returns:
            Dict with 'success' key and boolean value
        """
        action_func = self.get_action(name)
        
        # Prepare arguments
        if isinstance(raw_input, str):
            # Use first parameter name for string input
            sig = inspect.signature(action_func)
            param_names = list(sig.parameters.keys())
            if param_names:
                args = {param_names[0]: raw_input}
            else:
                args = {}
        else:
            args = raw_input or {}
            
        try:
            # Convert PageURIs back to Pages using the context
            resolved_args = _convert_uris_to_pages(args, action_func, self._context)
            
            # Invoke the action
            result = action_func(**resolved_args)
            return {"success": result}
            
        except Exception as e:
            logger.error(f"Action '{name}' failed: {e}")
            return {"success": False, "error": str(e)}
            
    @property
    def actions(self) -> Dict[str, ActionFunction]:
        """Get all registered actions."""
        return self._actions.copy()


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
        """Decorator to register a page validator.

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
