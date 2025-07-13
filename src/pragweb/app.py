"""Multi-Provider API Integration App"""

import argparse
import asyncio
import logging
from typing import Dict

from praga_core import ServerContext, set_global_context
from praga_core.agents import ReactAgent
from pragweb.api_clients.base import BaseProviderClient

# Import provider clients
# from pragweb.api_clients.google import GoogleProviderClient
from pragweb.api_clients.microsoft import MicrosoftProviderClient
from pragweb.config import get_current_config

# Import new orchestration services
from pragweb.services import (
    CalendarService,
    DocumentService,
    EmailService,
    PeopleService,
)

logging.basicConfig(level=getattr(logging, get_current_config().log_level))

logger = logging.getLogger(__name__)


async def initialize_providers() -> Dict[str, BaseProviderClient]:
    """Initialize all available providers."""
    providers: Dict[str, BaseProviderClient] = {}

    # Try to initialize Google provider
    # try:
    #     logger.info("Initializing Google provider...")
    #     google_provider = GoogleProviderClient()
    #     if await google_provider.test_connection():
    #         providers["google"] = google_provider
    #         logger.info("✅ Google provider initialized successfully")
    #     else:
    #         logger.warning("❌ Google provider failed connection test")
    # except Exception as e:
    #     logger.warning(f"❌ Failed to initialize Google provider: {e}")

    # Try to initialize Microsoft provider
    try:
        logger.info("Initializing Microsoft provider...")
        microsoft_provider = MicrosoftProviderClient()
        if await microsoft_provider.test_connection():
            providers["microsoft"] = microsoft_provider
            logger.info("✅ Microsoft provider initialized successfully")
        else:
            logger.warning("❌ Microsoft provider failed connection test")
    except Exception as e:
        logger.warning(f"❌ Failed to initialize Microsoft provider: {e}")

    if not providers:
        logger.error("❌ No providers could be initialized!")
        raise RuntimeError("No providers available")

    logger.info(f"✅ Initialized {len(providers)} providers: {list(providers.keys())}")
    return providers


async def setup_global_context() -> None:
    """Set up global context and initialize all components."""
    logger.info("Setting up global context...")

    # Get current configuration
    config = get_current_config()

    # Create and set global context with SQL cache
    context = await ServerContext.create(
        root=config.server_root, cache_url=config.page_cache_url
    )
    set_global_context(context)

    # Initialize providers
    providers = await initialize_providers()

    # Initialize provider-specific service instances
    logger.info("Initializing provider-specific services...")
    all_toolkits = []

    # Create separate service instances for each provider
    for provider_name, provider_client in providers.items():
        logger.info(f"Creating services for provider: {provider_name}")

        # Email service for this provider
        email_service = EmailService({provider_name: provider_client})
        all_toolkits.append(email_service.toolkit)

        # Calendar service for this provider
        calendar_service = CalendarService({provider_name: provider_client})
        all_toolkits.append(calendar_service.toolkit)

        # Document service for this provider
        document_service = DocumentService({provider_name: provider_client})
        all_toolkits.append(document_service.toolkit)

    # Create shared people service with all providers
    logger.info("Creating shared people service...")
    people_service = PeopleService(providers)
    all_toolkits.append(people_service.toolkit)

    # Collect all toolkits
    logger.info(f"Collected {len(all_toolkits)} service toolkits")

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
    logger.info("🚀 Multi-provider integration ready!")

    # Show available providers
    provider_list = ", ".join(providers.keys())
    logger.info(f"📡 Available providers: {provider_list}")


async def run_interactive_cli() -> None:
    """Run interactive CLI for direct queries."""
    from praga_core import get_global_context

    context = get_global_context()

    print("🚀 Multi-Provider API Integration - Interactive Mode")
    print("=" * 50)
    print("✅ Setup complete! Ready for queries.")
    print(
        "📧 Supports: gmail/, outlook/, google_calendar/, outlook_calendar/, people/, etc."
    )
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
            result = await context.search(query)

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


async def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Provider API Integration with Global Context",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python app.py                    # Run interactive mode
  python app.py -v                 # Run with verbose logging

Supported Providers:
  - Google (Gmail, Calendar, Contacts, Docs, Drive)
  - Microsoft (Outlook, Calendar, Contacts, OneDrive)
        """,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Set up global context
    try:
        await setup_global_context()
        await run_interactive_cli()
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        print(f"\n❌ Startup failed: {e}")
        print("\nPlease check your provider configurations:")
        print("- For Google: docs/integrations/GOOGLE_OAUTH_SETUP.md")
        print("- For Microsoft: docs/integrations/OUTLOOK_OAUTH_SETUP.md")


if __name__ == "__main__":
    asyncio.run(main())
