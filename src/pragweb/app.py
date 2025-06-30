"""Google API Integration App"""

import argparse
import logging

from praga_core import ServerContext, set_global_context
from praga_core.agents import ReactAgent
from pragweb.config import get_current_config
from pragweb.google_api.calendar import CalendarService
from pragweb.google_api.client import GoogleAPIClient
from pragweb.google_api.docs import GoogleDocsService
from pragweb.google_api.gmail import GmailService
from pragweb.google_api.people import PeopleService

logging.basicConfig(level=getattr(logging, get_current_config().log_level))

logger = logging.getLogger(__name__)


def setup_global_context() -> None:
    """Set up global context and initialize all components."""
    logger.info("Setting up global context...")

    # Get current configuration
    config = get_current_config()

    # Create and set global context with SQL cache
    context = ServerContext(root=config.server_root, cache_url=config.page_cache_url)
    set_global_context(context)

    # Create single Google API client
    google_client = GoogleAPIClient()

    # Initialize services (they auto-register with global context)
    logger.info("Initializing services...")
    gmail_service = GmailService(google_client)
    calendar_service = CalendarService(google_client)
    people_service = PeopleService(google_client)
    google_docs_service = GoogleDocsService(google_client)

    # Collect all toolkits from registered services
    logger.info("Collecting toolkits...")
    all_toolkits = [
        gmail_service.toolkit,
        calendar_service.toolkit,
        people_service.toolkit,
        google_docs_service.toolkit,
    ]

    # Set up agent with collected toolkits
    logger.info("Setting up React agent...")
    agent = ReactAgent(
        model=config.retriever_agent_model,
        toolkits=all_toolkits,
        max_iterations=config.retriever_max_iterations,
    )

    # Set retriever on global context
    context.retriever = agent

    logger.info("✅ Global context setup complete!")


def run_interactive_cli() -> None:
    """Run interactive CLI for direct queries."""
    from praga_core import get_global_context

    context = get_global_context()

    print("🚀 Google API Integration - Interactive Mode")
    print("=" * 50)
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


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Google API Integration with Global Context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Set up global context
    setup_global_context()
    run_interactive_cli()


if __name__ == "__main__":
    main()
