"""Description templates for MCP tools and resources."""

import inspect
from typing import Any, Dict, List, Union, get_args, get_origin, get_type_hints

from praga_core.action_executor import ActionFunction
from praga_core.types import PageURI


def get_search_tool_description(type_names: List[str]) -> str:
    """Generate description for the search_pages tool."""
    return f"""Search for pages using natural language instructions.

Returns JSON with search results and optionally resolved page content.

Available page types: {', '.join(type_names)}

Parameters:
- instruction: Natural language search instruction (required)
- resolve_references: Whether to resolve page content in results (default: true)

Examples:
- "Find emails from Alice about project X"
- "Get calendar events for next week"
- "Show me all documents mentioning quarterly report"
- "Search for person named John Smith"

Response format:
- results: Array of search results with page references
- If resolve_references=true: Each result includes full page content
- If resolve_references=false: Each result includes only page URI and metadata
"""


def get_pages_tool_description(type_names: List[str]) -> str:
    """Generate description for the get_pages tool. Optionally accepts allow_stale to return invalid pages."""
    return f"""Get specific pages/documents by their URIs.

Returns JSON with complete page content and metadata. Supports both single page and bulk operations.

Available page types: {', '.join(type_names)}

Parameters:
- page_uris: List of page URIs in format "PageType:id"
- allow_stale: Optional boolean to allow stale data (default: false)

Examples:
- Single page: page_uris=["EmailPage:msg_12345"]
- Multiple pages: page_uris=["EmailPage:msg_1", "CalendarEventPage:event_2"]
- Full URI format: page_uris=["root/EmailPage:msg@1", "root/CalendarEventPage:event@2"]

Response format:
- requested_count: Number of pages requested
- successful_count: Number of pages successfully retrieved
- error_count: Number of pages that failed
- pages: Array of successfully retrieved pages with uri, content, and status
- errors: Array of failed pages with uri, status, and error message (if any failures)
"""


def get_invoke_action_tool_description(actions: Dict[str, ActionFunction]) -> str:
    """Generate comprehensive description for the single invoke_action tool."""
    if not actions:
        return """Execute any registered action on pages.

This tool provides a unified interface for invoking actions on pages. Actions are operations that can modify page state or perform operations on pages.

Available actions: No actions available

Parameters:
- action_name: str - Name of the action to execute (required)
- action_input: Dict[str, Any] - Dictionary containing action parameters (required)

Returns JSON with success status and error information:
- Success: {"success": true}
- Failure: {"success": false, "error": "<error_message>"}
"""

    action_names = list(actions.keys())
    actions_text = ", ".join(action_names)

    # Generate detailed descriptions for each action
    action_details = []
    for action_name, action_func in actions.items():
        action_detail = _generate_action_detail(action_name, action_func)
        action_details.append(action_detail)

    action_details_text = "\n\n".join(action_details)

    return f"""Execute any registered action on pages.

This tool provides a unified interface for invoking actions on pages. Actions are operations that can modify page state or perform operations on pages.

Available actions: {actions_text}

Parameters:
- action_name: str - Name of the action to execute (required)
- action_input: Dict[str, Any] - Dictionary containing action parameters (required)

Action input format:
- Page parameters should be provided as string URIs
- Simple format: {{"email": "EmailPage:msg_12345"}}
- Full format: {{"email": "root/EmailPage:msg_12345@1"}}
- For actions with multiple parameters: {{"email": "EmailPage:msg_1", "mark_read": true}}

Returns JSON with success status and error information:
- Success: {{"success": true}}
- Failure: {{"success": false, "error": "<error_message>"}}

## Available Actions

{action_details_text}

## Example Usage

{_generate_example_usage(actions)}

Note: This tool can execute any registered action. The specific parameters required depend on the action being invoked.
"""


def _generate_action_detail(action_name: str, action_func: ActionFunction) -> str:
    """Generate detailed description for a single action."""
    # Get docstring
    doc = inspect.getdoc(action_func) or "No description available."

    # Get function signature and type hints
    sig = inspect.signature(action_func)
    try:
        type_hints = get_type_hints(action_func)
    except Exception:
        type_hints = {}

    # Generate parameter descriptions
    param_descriptions = []
    for param_name, param in sig.parameters.items():
        param_type = type_hints.get(param_name, param.annotation)
        if param_type == inspect.Parameter.empty:
            param_type = "Any"

        # Transform Page types to URI types for description
        transformed_type = _convert_page_type_to_uri_type_for_description(param_type)

        # Check if parameter has default value
        has_default = param.default != inspect.Parameter.empty
        default_text = (
            f" (optional, default: {param.default})" if has_default else " (required)"
        )

        param_descriptions.append(f"  - {param_name}: {transformed_type}{default_text}")

    param_text = (
        "\n".join(param_descriptions) if param_descriptions else "  No parameters"
    )

    return f"""### {action_name}

{doc}

Parameters:
{param_text}"""


def _convert_page_type_to_uri_type_for_description(param_type: Any) -> str:
    """Convert Page-related type annotations to string equivalents for descriptions."""
    # Handle direct PageURI type
    if param_type is PageURI:
        return "str (page URI)"

    # Handle generic types like List[PageURI], Optional[PageURI], etc.
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin in (list, List) and args and args[0] is PageURI:
        return "List[str] (page URIs)"

    if origin is Union and len(args) == 2 and type(None) in args:
        non_none_type = args[0] if args[1] is type(None) else args[1]
        if non_none_type is PageURI:
            return "Optional[str] (page URI)"
        # Handle Optional[List[PageURI]]
        elif (
            get_origin(non_none_type) is list
            and get_args(non_none_type)
            and get_args(non_none_type)[0] is PageURI
        ):
            return "Optional[List[str]] (page URIs)"

    # For non-PageURI types, return string representation
    if hasattr(param_type, "__name__"):
        return str(param_type.__name__)
    else:
        return str(param_type)


def _generate_example_usage(actions: Dict[str, ActionFunction]) -> str:
    """Generate example usage for actions."""
    if not actions:
        return "No actions available for examples."

    examples = []
    for action_name, action_func in actions.items():
        example = _generate_action_example(action_name, action_func)
        if example:
            examples.append(example)

    return "\n".join(examples[:3])  # Show up to 3 examples to keep it manageable


def _generate_action_example(action_name: str, action_func: ActionFunction) -> str:
    """Generate a usage example for a specific action."""
    sig = inspect.signature(action_func)
    try:
        type_hints = get_type_hints(action_func)
    except Exception:
        type_hints = {}

    # Build example action_input
    example_params: Dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        param_type = type_hints.get(param_name, param.annotation)

        # Generate example values based on parameter type
        if param_type is PageURI or _is_page_type(param_type):
            # Use the parameter name to infer page type
            if "email" in param_name.lower():
                example_params[param_name] = "EmailPage:msg_12345"
            elif "person" in param_name.lower():
                example_params[param_name] = "PersonPage:person_123"
            elif "thread" in param_name.lower():
                example_params[param_name] = "EmailThreadPage:thread_456"
            else:
                # Generic page URI
                example_params[param_name] = "SomePage:page_123"
        elif _is_list_page_type(param_type):
            # List of pages
            if "email" in param_name.lower():
                example_params[param_name] = ["EmailPage:msg_1", "EmailPage:msg_2"]
            elif "person" in param_name.lower() or "recipient" in param_name.lower():
                example_params[param_name] = [
                    "PersonPage:person_1",
                    "PersonPage:person_2",
                ]
            else:
                example_params[param_name] = ["SomePage:page_1", "SomePage:page_2"]
        elif param_type == str or param_type is str:
            # String parameters
            if "message" in param_name.lower():
                example_params[param_name] = "Your message here"
            elif "subject" in param_name.lower():
                example_params[param_name] = "Email subject"
            else:
                example_params[param_name] = f"example_{param_name}"
        elif param_type == bool or param_type is bool:
            example_params[param_name] = True
        elif param.default != inspect.Parameter.empty:
            # Skip optional parameters with defaults
            continue
        else:
            # For other types, use a generic example
            example_params[param_name] = f"<{param_name}_value>"

    if not example_params:
        return f'- action_name="{action_name}", action_input={{}}'

    return f'- action_name="{action_name}", action_input={example_params}'


def _is_page_type(param_type: Any) -> bool:
    """Check if a type is Page or a subclass of Page."""
    from praga_core.types import Page

    return param_type is Page or (
        isinstance(param_type, type) and issubclass(param_type, Page)
    )


def _is_list_page_type(param_type: Any) -> bool:
    """Check if a type is List[Page] or similar."""
    origin = get_origin(param_type)
    args = get_args(param_type)

    if origin in (list, List) and args:
        return _is_page_type(args[0])

    return False
