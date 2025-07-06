"""Action execution framework for handling boolean action operations."""

from __future__ import annotations

import inspect
import logging
from abc import ABC, abstractmethod
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from praga_core.types import Page, PageURI

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)

# Action function type - returns awaitable boolean for success/failure
ActionFunction = Callable[..., Awaitable[bool]]


def _is_action_function(action_function: ActionFunction) -> bool:
    """
    Check if a function is a valid action function.

    Action functions should:
    1. Have a Page (or subclass) as the first parameter
    2. Return a boolean
    """
    try:
        type_hints = get_type_hints(action_function)

        # Check return type is Awaitable[bool] or async function returning bool
        return_annotation = type_hints.get("return", None)
        if return_annotation is None:
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
        if not (
            first_param_type is Page
            or (
                isinstance(first_param_type, type)
                and issubclass(first_param_type, Page)
            )
        ):
            return False

        # For async functions, the return type should be bool (wrapped in Coroutine internally)
        if inspect.iscoroutinefunction(action_function):
            if return_annotation == bool:
                return True

        # Check if it's explicitly Awaitable[bool]
        origin = get_origin(return_annotation)
        if origin is not None:
            args = get_args(return_annotation)
            # Check for Awaitable[bool], Coroutine[Any, Any, bool], etc.
            if origin is Union:
                # Skip Union types for now
                return False
            elif args and args[-1] == bool:  # Last type arg should be bool
                return True
        elif return_annotation == Awaitable[bool]:
            return True

        return False
    except Exception:
        return False


class ActionExecutorMixin(ABC):
    """Mixin class that provides action execution functionality."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._actions: Dict[str, ActionFunction] = {}

    @abstractmethod
    async def get_pages(self, page_uris: List[PageURI]) -> List[Page]:
        """Abstract method for retrieving pages by URIs.

        Must be implemented by classes that use this mixin.
        """
        ...

    def register_action(self, name: str, func: ActionFunction) -> None:
        """Register an action function.

        Args:
            name: Name of the action
            func: Action function that takes Page (or subclass) as first param and returns Awaitable[bool]
        """
        if not _is_action_function(func):
            raise TypeError(
                f"Action '{name}' must have a Page (or subclass) as the first parameter "
                f"and return an awaitable boolean. Got: {getattr(func, '__annotations__', {})}"
            )

        # Create a wrapper function that takes PageURIs instead of Pages
        wrapper_func = self._create_action_wrapper(func)
        self._actions[name] = wrapper_func
        logger.info(f"Registered action: {name}")

    def _create_action_wrapper(self, original_func: ActionFunction) -> ActionFunction:
        """Create a wrapper function that takes PageURIs instead of Pages."""
        import functools

        @functools.wraps(original_func)
        async def wrapper(**kwargs: Any) -> bool:
            resolved_args = await self._convert_uris_to_pages(kwargs, original_func)
            return await original_func(**resolved_args)

        self._update_wrapper_annotations(wrapper, original_func)
        return wrapper

    def _update_wrapper_annotations(
        self, wrapper: ActionFunction, original_func: ActionFunction
    ) -> None:
        """Update wrapper function's type annotations to use PageURI instead of Page types."""
        try:
            type_hints = get_type_hints(original_func)
        except Exception as e:
            raise ValueError(
                f"Action function {original_func.__name__} has invalid type annotations: {e}"
            )

        # Check that we have a return type annotation
        if "return" not in type_hints:
            raise ValueError(
                f"Action function {original_func.__name__} must have a return type annotation"
            )

        # Check that we have annotations for all parameters
        sig = inspect.signature(original_func)
        for param_name in sig.parameters.keys():
            if param_name not in type_hints:
                raise ValueError(
                    f"Action function {original_func.__name__} parameter '{param_name}' must have a type annotation"
                )

        new_annotations = {}
        for param_name, param_type in type_hints.items():
            if param_name == "return":
                new_annotations[param_name] = param_type
            else:
                new_annotations[param_name] = self._convert_page_type_to_uri_type(
                    param_type
                )

        wrapper.__annotations__ = new_annotations

    def _convert_page_type_to_uri_type(self, param_type: Any) -> Any:
        """Convert Page-related type annotations to PageURI equivalents."""
        # Direct Page type -> PageURI
        if self._is_page_type(param_type):
            return PageURI

        # Handle generic types like List[Page], Optional[Page], etc.
        origin = get_origin(param_type)
        args = get_args(param_type)

        if origin in (list, List) and args and self._is_page_type(args[0]):
            return List[PageURI]

        if self._is_optional_page_type(param_type):
            return Union[PageURI, None]

        # For non-Page types, return unchanged
        return param_type

    def _is_page_type(self, param_type: Any) -> bool:
        """Check if a type is Page or a subclass of Page."""
        return param_type is Page or (
            isinstance(param_type, type) and issubclass(param_type, Page)
        )

    def _is_optional_page_type(self, param_type: Any) -> bool:
        """Check if a type is Optional[Page] or similar union with None."""
        origin = get_origin(param_type)
        args = get_args(param_type)

        if origin is Union and len(args) == 2 and type(None) in args:
            non_none_type = args[0] if args[1] is type(None) else args[1]
            return self._is_page_type(non_none_type)

        return False

    def get_action(self, name: str) -> ActionFunction:
        """Get an action function by name."""
        if name not in self._actions:
            raise ValueError(f"Action '{name}' not found")
        return self._actions[name]

    async def invoke_action(
        self, name: str, raw_input: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Invoke an action by name.

        Args:
            name: Name of the action to invoke
            raw_input: Input arguments (PageURIs) - if string, used as first parameter

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
            # The action_func is now a wrapper that handles PageURI -> Page conversion
            result = await action_func(**args)
            return {"success": result}

        except Exception as e:
            logger.error(f"Action '{name}' failed: {e}")
            return {"success": False, "error": str(e)}

    async def _convert_uris_to_pages(
        self, args: Dict[str, Any], func: ActionFunction
    ) -> Dict[str, Any]:
        """Convert PageURIs back to Pages using self.get_pages method."""
        type_hints = get_type_hints(func)
        converted_args: Dict[str, Any] = {}

        # Collect all URIs that need to be converted to pages
        uris_to_fetch: List[PageURI] = []
        uri_param_mapping: List[Tuple[str, str, Union[int, List[int]]]] = (
            []
        )  # Track which parameter each URI belongs to

        for param_name, value in args.items():
            param_type = type_hints.get(param_name, type(value))

            # Handle single PageURI -> Page
            if isinstance(value, (PageURI, str)):
                # Check if this parameter should be a Page
                if param_type is Page or (
                    isinstance(param_type, type) and issubclass(param_type, Page)
                ):
                    page_uri = (
                        value if isinstance(value, PageURI) else PageURI.parse(value)
                    )
                    uris_to_fetch.append(page_uri)
                    uri_param_mapping.append(
                        (param_name, "single", len(uris_to_fetch) - 1)
                    )
                else:
                    converted_args[param_name] = value
            # Handle List[PageURI] -> List[Page]
            elif isinstance(value, (list, tuple)) and value:
                origin = get_origin(param_type)
                args_types = get_args(param_type)

                if (
                    origin in (list, tuple, Sequence)
                    and args_types
                    and issubclass(args_types[0], Page)
                ):
                    page_uri_indices: List[int] = []
                    for item in value:
                        if isinstance(item, (PageURI, str)):
                            page_uri = (
                                item
                                if isinstance(item, PageURI)
                                else PageURI.parse(item)
                            )
                            uris_to_fetch.append(page_uri)
                            page_uri_indices.append(
                                len(uris_to_fetch) - 1
                            )  # Store index
                        # Note: Non-URI items in mixed lists aren't supported in this simplified version
                    uri_param_mapping.append((param_name, "list", page_uri_indices))
                else:
                    converted_args[param_name] = value
            # Handle Optional[PageURI] -> Optional[Page]
            elif value is None:
                converted_args[param_name] = None
            else:
                # Check if this is a Page object that should be a PageURI
                if isinstance(value, Page):
                    raise ValueError(
                        f"Parameter '{param_name}' received a Page object, but action wrapper expects PageURI. "
                        f"Pass the page's URI instead: {value.uri}"
                    )
                # For non-Page parameters, pass through unchanged
                converted_args[param_name] = value

        # Bulk fetch all pages if we have URIs to fetch
        if uris_to_fetch:
            try:
                pages = await self.get_pages(uris_to_fetch)
            except Exception as e:
                raise ValueError(f"Failed to retrieve pages: {e}")

            # Map pages back to their parameters
            for param_name, param_type, indices in uri_param_mapping:
                if param_type == "single":
                    if isinstance(indices, int):
                        converted_args[param_name] = pages[indices]
                elif param_type == "list":
                    if isinstance(indices, list):
                        converted_list = []
                        for idx in indices:
                            converted_list.append(pages[idx])
                        converted_args[param_name] = converted_list

        return converted_args

    def action(
        self, name: str | None = None
    ) -> Callable[[ActionFunction], ActionFunction]:
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
            self.register_action(action_name, func)
            return func

        return decorator

    @property
    def actions(self) -> Dict[str, ActionFunction]:
        """Get all registered actions."""
        return self._actions.copy()
