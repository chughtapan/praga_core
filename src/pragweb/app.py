"""
Google API Integration App - CLI with Global Context

Clean architecture with global context pattern:
- Global context accessible via ContextMixin
- Services register themselves automatically
- CLI with options for MCP server or direct queries
"""

import argparse
import asyncio
import logging

from dotenv import load_dotenv

from praga_core import ServerContext, set_global_context
from praga_core.agents import ReactAgent
from praga_core.integrations.mcp import create_mcp_server
from pragweb.google_api.services import CalendarService, GmailService, PeopleService
from pragweb.google_api.toolkits import CalendarToolkit, GmailToolkit, PeopleToolkit

load_dotenv()
logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def setup_global_context() -> None:
    """Set up global context and initialize all components."""
    logger.info("Setting up global context...")

    # Create and set global context
    context = ServerContext(root="google")
    set_global_context(context)

    # Initialize services (they auto-register with global context)
    logger.info("Initializing services...")
    gmail_service = GmailService()
    calendar_service = CalendarService()
    people_service = PeopleService()

    # Initialize toolkits (they use global context automatically)
    logger.info("Initializing toolkits...")
    gmail_toolkit = GmailToolkit(gmail_service)
    calendar_toolkit = CalendarToolkit(calendar_service)
    people_toolkit = PeopleToolkit(people_service)

    toolkits = [gmail_toolkit, calendar_toolkit, people_toolkit]

    # Set up agent with toolkits
    logger.info("Setting up React agent...")
    agent = ReactAgent(
        model="gpt-4o-mini",
        toolkits=toolkits,
        max_iterations=10,
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


async def run_mcp_server() -> None:
    """Run MCP server."""
    from praga_core import get_global_context

    context = get_global_context()

    print("🚀 Starting MCP Server...")
    print("=" * 50)

    mcp = create_mcp_server(
        context,
        name="Google APIs - Gmail & Calendar Server",
    )

    print("✅ MCP Server ready!")
    await mcp.run_async()


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Google API Integration with Global Context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s query          # Interactive query mode
  %(prog)s mcp            # Start MCP server
        """,
    )

    parser.add_argument(
        "mode",
        choices=["query", "mcp"],
        help="Mode to run: 'query' for interactive CLI, 'mcp' for MCP server",
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

    # Run the selected mode
    if args.mode == "query":
        run_interactive_cli()
    elif args.mode == "mcp":
        asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
