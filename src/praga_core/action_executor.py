"""Action execution framework for handling boolean action operations."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Sequence, Type, TypeVar, Union, get_origin, get_args, get_type_hints

from praga_core.types import Page, PageURI

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