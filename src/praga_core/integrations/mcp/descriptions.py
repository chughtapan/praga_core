"""Description templates for MCP tools and resources."""

import inspect
from typing import List

from praga_core.action_executor import ActionFunction


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

    # Extract parameters (excluding the first Page parameter)
    params = list(sig.parameters.items())[
        1:
    ]  # Skip first parameter which should be Page

    param_descriptions = []
    for param_name, param in params:
        param_type = (
            param.annotation if param.annotation != inspect.Parameter.empty else "Any"
        )
        default_text = (
            f" (default: {param.default})"
            if param.default != inspect.Parameter.empty
            else ""
        )
        param_descriptions.append(f"- {param_name}: {param_type}{default_text}")

    param_text = (
        "\n".join(param_descriptions)
        if param_descriptions
        else "No additional parameters required."
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
