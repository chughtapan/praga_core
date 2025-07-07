"""Description templates for MCP tools and resources."""

import inspect
from typing import Any, List, Union, get_args, get_origin, get_type_hints

from praga_core.action_executor import ActionFunction
from praga_core.types import Page


def get_search_tool_description(type_names: List[str]) -> str:
    """Generate description for the search_pages tool."""
    return f"""Search for pages using natural language instructions.

Returns JSON with search results and resolved page content.

Available page types: {', '.join(type_names)}

Examples:
- "Find emails from Alice about project X"
- "Get calendar events for next week"
- "Show me all documents mentioning quarterly report"
"""


def get_pages_tool_description(type_names: List[str]) -> str:
    """Generate description for the get_pages tool. Optionally accepts allow_stale to return invalid pages."""
    return f"""Get specific pages/documents by their type and ID(s).

Returns JSON with complete page content and metadata. Supports both single page and bulk operations.

Available page types: {', '.join(type_names)}

Single page examples:
- Get email: page_type="EmailPage", page_ids=["msg_12345"]
- Get calendar event: page_type="CalendarEventPage", page_ids=["event_67890"]
- Use aliases: page_type="Email", page_ids=["msg_12345"]

Bulk examples:
- Get multiple emails: page_type="EmailPage", page_ids=["msg_1", "msg_2", "msg_3"]
- Get multiple events: page_type="CalendarEvent", page_ids=["event_1", "event_2"]
"""


def get_action_tool_description(action_name: str, action_func: ActionFunction) -> str:
    """Generate description for an action tool."""
    # Get function signature and docstring
    sig = inspect.signature(action_func)
    doc = inspect.getdoc(action_func) or "Perform an action on a page."

    # Get type hints for proper parameter descriptions
    try:
        type_hints = get_type_hints(action_func)
    except Exception:
        type_hints = {}

    param_descriptions = []
    for param_name, param in sig.parameters.items():
        # Get the type annotation - transform Page types to PageURI
        param_type = type_hints.get(param_name, param.annotation)
        if param_type == inspect.Parameter.empty:
            param_type = "Any"

        # Transform Page types to PageURI types for description
        transformed_type = _convert_page_type_to_uri_type_for_description(param_type)

        default_text = (
            f" (default: {param.default})"
            if param.default != inspect.Parameter.empty
            else ""
        )
        param_descriptions.append(f"- {param_name}: {transformed_type}{default_text}")

    param_text = (
        "\n".join(param_descriptions)
        if param_descriptions
        else "No parameters required."
    )

    return f"""Action: {action_name}

{doc}

Parameters:
{param_text}

Returns JSON with success status (true/false) and any error message if the action fails.

Example usage:
- Provide the page URI and any additional parameters required by the action
- The action will be executed on the specified page
- Returns {{"success": true}} on success or {{"success": false, "error": "..."}} on failure
"""


def _convert_page_type_to_uri_type_for_description(param_type: Any) -> str:
    """Convert Page-related type annotations to PageURI equivalents for descriptions."""
    # Handle direct Page type
    if _is_page_type(param_type):
        return "PageURI"

    # Handle generic types like List[Page], Optional[Page], etc.
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin in (list, List):
        if args and _is_page_type(args[0]):
            return "List[PageURI]"
        elif args:
            # Handle List[SomePageType]
            inner_type = _convert_page_type_to_uri_type_for_description(args[0])
            return f"List[{inner_type}]"
        else:
            return "List"

    if _is_optional_page_type(param_type):
        return "Optional[PageURI]"

    # Handle Optional[List[Page]] and similar complex types
    if origin is Union:
        non_none_types = [arg for arg in args if arg is not type(None)]
        if len(non_none_types) == 1:
            inner_desc = _convert_page_type_to_uri_type_for_description(
                non_none_types[0]
            )
            return f"Optional[{inner_desc}]"

    # For non-Page types, return string representation
    if hasattr(param_type, "__name__"):
        return str(param_type.__name__)
    else:
        return str(param_type)


def _is_page_type(param_type: Any) -> bool:
    """Check if a type is Page or a subclass of Page."""
    return param_type is Page or (
        isinstance(param_type, type) and issubclass(param_type, Page)
    )


def _is_optional_page_type(param_type: Any) -> bool:
    """Check if a type is Optional[Page] or similar union with None."""
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin is Union and len(args) == 2 and type(None) in args:
        non_none_type = args[0] if args[1] is type(None) else args[1]
        return _is_page_type(non_none_type)

    return False
