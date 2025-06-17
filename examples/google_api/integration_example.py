#!/usr/bin/env python3
"""
Integration Example - Complete handler-based architecture with Google APIs.

This example shows:
1. Setting up ServerContext with handlers
2. Creating simplified toolkits that delegate to context
3. Using both registration patterns (@ctx.handler and ctx.register_handler)
4. Real Gmail and Calendar API integration
"""

import logging
import os
import sys

from dotenv import load_dotenv

from praga_core.agents import ReactAgent
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.calendar import CalendarEventPage  # noqa: E402
from pages.calendar import create_calendar_document  # noqa: E402
from pages.gmail import EmailPage, create_email_document  # noqa: E402
from toolkits.calendar_toolkit import CalendarToolkit  # noqa: E402
from toolkits.gmail_toolkit import GmailToolkit  # noqa: E402

load_dotenv()

logging.basicConfig(level=logging.DEBUG)


def setup_context() -> ServerContext:
    """Set up ServerContext with all handlers registered."""
    print("🔧 Setting up ServerContext with handlers...")

    ctx = ServerContext()

    # Method 1: Decorator pattern registration
    @ctx.handler(EmailPage)
    def handle_email_complete(email_id: str) -> EmailPage:
        """Complete email handler using decorator pattern."""
        return create_email_document(email_id)

    @ctx.handler(CalendarEventPage)
    def handle_calendar_complete(
        event_id: str, calendar_id: str = "primary"
    ) -> CalendarEventPage:
        return create_calendar_document(event_id, calendar_id)

    gmail_toolkit = GmailToolkit(ctx)
    calendar_toolkit = CalendarToolkit(ctx)
    ctx.retriever = ReactAgent(
        model="gpt-4o-mini",
        toolkits=[gmail_toolkit, calendar_toolkit],
        max_iterations=10,
    )
    return ctx


def main():
    """Run the complete integration example."""
    print("🚀 Google API Integration Test")
    # Set up context with handlers
    ctx = setup_context()

    while True:
        query = input("Enter a query: ")
        result = ctx.search(query)
        print(result)
        print("-" * 100)


if __name__ == "__main__":
    main()
