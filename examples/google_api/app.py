"""
Google API Integration App

Clean architecture with:
- Pages: Page definitions
- Services: Business logic for Google API interactions
- Toolkits: Search tools that use services and context
- App: Orchestration layer
"""

import logging
import os
import sys

from dotenv import load_dotenv

from praga_core.agents import ReactAgent
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services import (  # noqa: E402
    CalendarService,
    GmailService,
    GoogleDocsService,
    PeopleService,
)
from services.slack_service import SlackService  # noqa: E402
from toolkits.calendar_toolkit import CalendarToolkit  # noqa: E402
from toolkits.gmail_toolkit import GmailToolkit  # noqa: E402
from toolkits.google_docs_toolkit import GoogleDocsToolkit  # noqa: E402
from toolkits.people_toolkit import PeopleToolkit  # noqa: E402
from toolkits.slack_toolkit import SlackToolkit  # noqa: E402

load_dotenv()
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def setup_services(context: ServerContext) -> dict:
    """Set up services and register handlers with context."""
    logger.info("Setting up services...")

    # Services automatically register their handlers with context
    gmail_service = GmailService(context)
    calendar_service = CalendarService(context)
    people_service = PeopleService(context)
    gdocs_service = GoogleDocsService(context)
    slack_service = SlackService(context)

    return {
        "gmail": gmail_service,
        "calendar": calendar_service,
        "people": people_service,
        "gdocs": gdocs_service,
        "slack": slack_service,
    }


def setup_toolkits(context: ServerContext, services: dict) -> list:
    """Set up toolkits that use services for search and context for resolution."""
    logger.info("Setting up toolkits...")

    gmail_toolkit = GmailToolkit(context, services["gmail"])
    calendar_toolkit = CalendarToolkit(context, services["calendar"])
    people_toolkit = PeopleToolkit(context, services["people"])
    gdocs_toolkit = GoogleDocsToolkit(context, services["gdocs"])
    slack_toolkit = SlackToolkit(context, services["slack"])

    return [
        gmail_toolkit,
        calendar_toolkit,
        people_toolkit,
        gdocs_toolkit,
        slack_toolkit,
    ]


def setup_agent(toolkits: list) -> ReactAgent:
    """Set up the React agent with toolkits."""
    logger.info("Setting up React agent...")

    return ReactAgent(
        model="gpt-4o-mini",
        toolkits=toolkits,
        max_iterations=10,
    )


def setup_context() -> ServerContext:
    """Set up the context."""
    logger.info("Setting up context...")

    ctx = ServerContext(root="google")
    services = setup_services(ctx)
    toolkits = setup_toolkits(ctx, services)
    agent = setup_agent(toolkits)
    ctx.retriever = agent

    return ctx


def main():
    """Run the Google API integration app."""
    print("🚀 Google API Integration App")
    print("=" * 50)

    context = setup_context()
    print("✅ Setup complete! Ready for queries.")
    print("-" * 50)

    # Interactive loop
    while True:
        try:
            query = input("\nEnter a query (or 'exit' to quit): ").strip()
            if query.lower() in ["exit", "quit", "q"]:
                break

            if not query:
                continue

            print(f"\n🔍 Searching: {query}")
            print("-" * 40)

            # Search and display results
            result = context.search(query)

            if not result.results:
                print("No results found.")
                continue

            print(f"Found {len(result.results)} results:")
            print()

            for i, ref in enumerate(result.results, 1):
                print(f"{i}. {ref.uri}")
                if ref.score > 0:
                    print(f"   Score: {ref.score:.3f}")
                if ref.explanation:
                    print(f"   {ref.explanation}")
                print()

        except KeyboardInterrupt:
            print("\n\nGoodbye! 👋")
            break
        except Exception as e:
            logger.error(f"Error during query processing: {e}")
            print(f"Error: {e}")
            print("Please try again.")


if __name__ == "__main__":
    main()
