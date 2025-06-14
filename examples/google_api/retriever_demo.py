#!/usr/bin/env python3
"""
RetrieverAgent Demo with Google API Integration

This demo shows how to use the RetrieverAgent with OpenAI to intelligently search
through Gmail and Calendar data to find relevant document references.

Requirements:
- OpenAI API key (set OPENAI_API_KEY environment variable)
- Google API credentials (OAuth2 setup)
- Gmail and Calendar API access

Usage:
    python react_agent_demo.py
"""

import logging
import os
import sys

from calendar_toolkit import CalendarToolkit
from dotenv import load_dotenv
from gmail_toolkit import GmailToolkit

from praga_core import RetrieverAgent

# Configure logging with a professional format
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",  # Clean format without timestamps for demo output
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Silence other loggers
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def display_documents(results):
    """Display complete documents from DocumentReference results."""
    if not results:
        logger.info("[SYSTEM] No documents found.")
        return

    logger.info(f"[SYSTEM] Found {len(results)} document(s):")
    logger.info("")

    for i, doc_ref in enumerate(results, 1):
        logger.info(f"[REFERENCE {i}] ID: {doc_ref.id}")
        logger.info(f"[REFERENCE {i}] Type: {doc_ref.document_type}")
        logger.info(f"[REFERENCE {i}] Score: {doc_ref.score}")
        logger.info(f"[REFERENCE {i}] Explanation: {doc_ref.explanation}")
        logger.info("")

        # Display the complete document if available
        if doc_ref.document:
            logger.info(f"[DOCUMENT {i}] Document: {doc_ref.document}")
        else:
            logger.info(
                f"[DOCUMENT {i}] No document content available (document is None)"
            )
            logger.info("")


def demo_interactive_search():
    """Interactive demo where user can ask queries."""
    logger.info("=" * 80)
    logger.info("[SYSTEM] RetrieverAgent Interactive Demo")
    logger.info("=" * 80)
    logger.info("[SYSTEM] This demo uses OpenAI's GPT to intelligently search through")
    logger.info(
        "[SYSTEM] your Gmail and Calendar data based on natural language queries."
    )
    logger.info("")

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error(
            "[SYSTEM] Error: Please set your OPENAI_API_KEY environment variable or add it to a .env file"
        )
        logger.error(
            "[SYSTEM] Example .env file entry: OPENAI_API_KEY='your-api-key-here'"
        )
        return

    try:
        # Initialize the toolkits
        logger.info("[SYSTEM] Setting up Google API toolkits...")

        toolkits = []

        # Try to initialize Gmail toolkit
        try:
            gmail_toolkit = GmailToolkit()
            toolkits.append(gmail_toolkit)
            logger.info("[SYSTEM] ✅ Gmail toolkit ready")
        except Exception as e:
            logger.warning(f"[SYSTEM] ⚠️ Gmail initialization failed: {e}")

        # Try to initialize Calendar toolkit
        try:
            calendar_toolkit = CalendarToolkit()
            toolkits.append(calendar_toolkit)
            logger.info("[SYSTEM] ✅ Calendar toolkit ready")
        except Exception as e:
            logger.warning(f"[SYSTEM] ⚠️ Calendar initialization failed: {e}")

        if not toolkits:
            logger.error(
                "[SYSTEM] Error: Neither Gmail nor Calendar could be initialized"
            )
            logger.error("[SYSTEM] Please check your Google API credentials")
            return

        # Initialize the RetrieverAgent with multiple toolkits
        logger.info("[SYSTEM] Initializing RetrieverAgent with OpenAI...")
        agent = RetrieverAgent(
            toolkits=toolkits,  # Pass list of toolkits directly
            model="gpt-4o-mini",
            max_iterations=5,
            debug=True,  # Enable detailed logging
        )
        logger.info("[SYSTEM] RetrieverAgent ready!")
        logger.info("")

        # Show available capabilities
        logger.info("[SYSTEM] Available Search Capabilities:")
        for toolkit in toolkits:
            toolkit_name = toolkit.__class__.__name__.replace("Toolkit", "")
            tool_names = list(toolkit.tools.keys())
            logger.info(f"[SYSTEM] - {toolkit_name}: {', '.join(tool_names)}")
        logger.info("")

        # Example queries
        logger.info("[SYSTEM] Example Queries:")
        logger.info("[SYSTEM] - 'Find emails about the project meeting last week'")
        logger.info("[SYSTEM] - 'Show me calendar events for next Tuesday'")
        logger.info("[SYSTEM] - 'Find emails from john@company.com about the budget'")
        logger.info("[SYSTEM] - 'What meetings do I have today?'")
        logger.info("")

        # Interactive loop
        while True:
            try:
                logger.info("─" * 80)
                query = input("[USER] Enter your query (or 'quit' to exit): ")
                logger.info("─" * 80)

                if query.lower() in ("quit", "exit", "q"):
                    break

                if not query.strip():
                    continue

                try:
                    results = agent.search(query)

                    logger.info("─" * 80)
                    display_documents(results)
                    logger.info("─" * 80)
                    logger.info("")

                except Exception as e:
                    logger.error(f"[SYSTEM] Error during search: {e}")
                    logger.info("")

            except KeyboardInterrupt:
                logger.info("\n[SYSTEM] Search interrupted")
                break

            except Exception as e:
                logger.error(f"[SYSTEM] Error: {e}")
                break

        logger.info("[SYSTEM] Demo completed")

    except Exception as e:
        logger.error(f"[SYSTEM] Error: {e}")


def demo_predefined_queries():
    """Demo with predefined queries to show capabilities."""
    logger.info("=" * 80)
    logger.info("[SYSTEM] RetrieverAgent Predefined Queries Demo")
    logger.info("=" * 80)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        logger.error(
            "[SYSTEM] Error: Please set your OPENAI_API_KEY environment variable or add it to a .env file"
        )
        return

    try:
        # Initialize toolkits
        toolkits = []

        try:
            gmail_toolkit = GmailToolkit()
            toolkits.append(gmail_toolkit)
        except Exception as e:
            logger.warning(f"[SYSTEM] Gmail initialization failed: {e}")

        try:
            calendar_toolkit = CalendarToolkit()
            toolkits.append(calendar_toolkit)
        except Exception as e:
            logger.warning(f"[SYSTEM] Calendar initialization failed: {e}")

        if not toolkits:
            logger.error("[SYSTEM] No toolkits could be initialized")
            return

        # Initialize agent with multiple toolkits
        agent = RetrieverAgent(
            toolkits=toolkits,
            model="gpt-4o-mini",
            max_iterations=10,
            debug=True,  # Enable message logging
        )

        # Predefined queries to demonstrate different capabilities
        demo_queries = [
            "Find recent emails from the last 3 days",
            "Show me today's calendar events",
            "Find emails containing 'meeting' in the last week",
            "Search for calendar events about 'standup' or 'daily'",
            "Find emails from managers or team leads",
        ]

        logger.info(
            "[SYSTEM] Running predefined queries to demonstrate capabilities..."
        )
        logger.info("")

        for i, query in enumerate(demo_queries, 1):
            logger.info("─" * 80)
            logger.info(f"[SYSTEM] Query {i}: {query}")
            logger.info("─" * 80)

            try:
                results = agent.search(query)

                logger.info("─" * 80)
                # Limit to first 2 results for predefined demo to avoid too much output
                limited_results = results[:2] if results else []
                display_documents(limited_results)

                if results and len(results) > 2:
                    logger.info(f"[SYSTEM] ... and {len(results) - 2} more results")
                logger.info("─" * 80)
                logger.info("")

            except Exception as e:
                logger.error(f"[SYSTEM] Error: {e}")
                logger.info("")

    except Exception as e:
        logger.error(f"[SYSTEM] Error: {e}")


def main():
    """Main function to run the demo."""
    # Load environment variables from .env file
    load_dotenv()
    print("🚀 Welcome to the ReAct Agent Google API Demo!")
    print()
    print("Choose a demo mode:")
    print("1. Interactive search (enter your own queries)")
    print("2. Predefined queries demo")
    print("3. Exit")
    print()

    while True:
        try:
            choice = input("Enter your choice (1-3): ").strip()

            if choice == "1":
                demo_interactive_search()
                break
            elif choice == "2":
                demo_predefined_queries()
                break
            elif choice == "3":
                print("👋 Goodbye!")
                break
            else:
                print("❌ Invalid choice. Please enter 1, 2, or 3.")
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break


if __name__ == "__main__":
    main()
