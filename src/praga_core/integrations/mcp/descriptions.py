"""Description templates for MCP tools and resources."""

from typing import List


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
