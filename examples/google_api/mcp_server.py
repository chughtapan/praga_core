#!/usr/bin/env python3
"""
Production MCP Server for Google APIs - Gmail & Calendar integration.
"""

import os
import sys

from dotenv import load_dotenv

from praga_core.agents import ReactAgent
from praga_core.context import ServerContext
from praga_core.integrations.mcp import create_praga_mcp_server

# Import Google API components
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.calendar import CalendarEventPage, create_calendar_document  # noqa: E402
from pages.gmail import EmailPage, create_email_document  # noqa: E402
from toolkits.calendar_toolkit import CalendarToolkit  # noqa: E402
from toolkits.gmail_toolkit import GmailToolkit  # noqa: E402

load_dotenv()


def setup_context() -> ServerContext:
    """Set up ServerContext with Google API handlers."""
    ctx = ServerContext()

    # Register page handlers
    @ctx.handler(EmailPage, aliases=["Email", "EmailMessage", "GmailMessage"])
    def handle_email(email_id: str) -> EmailPage:
        """Retrieve Gmail message with full content and metadata."""
        return create_email_document(email_id)

    @ctx.handler(
        CalendarEventPage, aliases=["CalendarEvent", "Event", "GoogleCalendarEvent"]
    )
    def handle_calendar(
        event_id: str, calendar_id: str = "primary"
    ) -> CalendarEventPage:
        """Retrieve Google Calendar event with full details."""
        return create_calendar_document(event_id, calendar_id)

    # Set up toolkits and retriever
    gmail_toolkit = GmailToolkit(ctx)
    calendar_toolkit = CalendarToolkit(ctx)
    ctx.retriever = ReactAgent(
        model="gpt-4o-mini",
        toolkits=[gmail_toolkit, calendar_toolkit],
        max_iterations=10,
    )

    return ctx


# Create the MCP server instance for fastmcp
ctx = setup_context()
mcp = create_praga_mcp_server(
    ctx,
    name="Google APIs - Gmail & Calendar Server",
)


if __name__ == "__main__":
    # Run directly if executed as script
    import asyncio

    asyncio.run(mcp.run_async())
