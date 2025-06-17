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
    """Generate description for the get_pages tool."""
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


def get_page_list_resource_description(type_names: List[str]) -> str:
    """Generate description for the page list resource."""
    return f"""List of all available pages in the system.

Available page types: {', '.join(type_names)}

This resource provides information about page types and their structure, but does not enumerate individual pages.
Use the search_pages tool to find specific pages or the get_pages tool to retrieve known pages.
"""


PAGE_SCHEMA_RESOURCE_DESCRIPTION = """JSON schema definitions for all page types.

This resource provides the complete JSON schema for each page type, including:
- Field definitions and types
- Required vs optional fields  
- Validation constraints
- Field descriptions

Use this to understand the structure of page data returned by other tools and resources.
"""


PAGE_TYPE_RESOURCE_DESCRIPTION = """Available page type information.

This resource lists all registered page types in the system, including:
- Class names (e.g., "EmailPage", "CalendarEventPage")
- Type aliases (e.g., "Email", "CalendarEvent")
- Handler information

Use this to discover what page types are available for search and retrieval operations.
"""
