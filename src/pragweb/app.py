"""
Google API Integration App

Clean architecture with:
- Pages: Page definitions
- Services: Business logic for Google API interactions
- Toolkits: Search tools that use services and context
- App: Orchestration layer
"""

import logging
from typing import Any, Dict, List

from dotenv import load_dotenv

from praga_core.agents import ReactAgent, RetrieverToolkit
from praga_core.context import ServerContext
from pragweb.google_api.services import CalendarService, GmailService, PeopleService
from pragweb.google_api.toolkits import CalendarToolkit, GmailToolkit, PeopleToolkit

load_dotenv()
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def setup_services(context: ServerContext) -> Dict[str, Any]:
    """Set up services and register handlers with context."""
    logger.info("Setting up services...")

    # Services automatically register their handlers with context
    gmail_service = GmailService(context)
    calendar_service = CalendarService(context)
    people_service = PeopleService(context)

    return {
        "gmail": gmail_service,
        "calendar": calendar_service,
        "people": people_service,
    }


def setup_toolkits(
    context: ServerContext, services: Dict[str, Any]
) -> List[RetrieverToolkit]:
    """Set up toolkits that use services for search and context for resolution."""
    logger.info("Setting up toolkits...")

    gmail_toolkit = GmailToolkit(context, services["gmail"])
    calendar_toolkit = CalendarToolkit(context, services["calendar"])
    people_toolkit = PeopleToolkit(context, services["people"])

    return [gmail_toolkit, calendar_toolkit, people_toolkit]


def setup_agent(toolkits: List[RetrieverToolkit]) -> ReactAgent:
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


def main() -> None:
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
