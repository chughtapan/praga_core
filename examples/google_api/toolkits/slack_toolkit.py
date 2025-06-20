"""Slack toolkit for searching conversations, threads, and messages."""

import logging
import os
import sys
from typing import Optional

from praga_core.agents import PaginatedResponse, RetrieverToolkit
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.slack import SlackConversation, SlackThread  # noqa: E402
from services.slack_service import SlackService  # noqa: E402
from toolkits.person_resolver import resolve_person_to_email  # noqa: E402

logger = logging.getLogger(__name__)


class SlackToolkit(RetrieverToolkit):
    """Toolkit for searching Slack conversations and threads."""

    def __init__(self, context: ServerContext, slack_service: SlackService):
        super().__init__(context)
        self.slack_service = slack_service

        # Register all Slack search tools
        self.register_tool(self.search_conversations_by_content)
        self.register_tool(self.search_conversations_by_person)
        self.register_tool(self.search_conversations_by_channel)
        self.register_tool(self.search_conversations_by_date_range)
        self.register_tool(self.search_recent_conversations)
        self.register_tool(self.search_direct_messages)
        self.register_tool(self.search_threads_by_content)
        self.register_tool(self.get_conversation_with_person)

        logger.info("Slack toolkit initialized")

    @property
    def name(self) -> str:
        return "SlackToolkit"

    def _search_conversations_paginated_response(
        self, search_method, *args, page: int = 0, page_size: int = 10, **kwargs
    ) -> PaginatedResponse[SlackConversation]:
        """Helper method to handle pagination for conversation searches."""
        # Calculate page token by iterating through pages
        page_token = None
        if page > 0:
            current_token = None
            for _ in range(page):
                _, current_token = search_method(
                    *args, page_token=current_token, page_size=page_size, **kwargs
                )
                if not current_token:
                    # No more pages available
                    logger.debug(f"No more pages available at page {page}")
                    return PaginatedResponse(
                        results=[],
                        page_number=page,
                        has_next_page=False,
                    )
            page_token = current_token

        # Get the actual page data
        uris, next_page_token = search_method(
            *args, page_token=page_token, page_size=page_size, **kwargs
        )

        # Resolve URIs to pages using context (this will trigger on-demand ingestion if needed)
        pages = [self.context.get_page(uri) for uri in uris]
        logger.debug(f"Successfully resolved {len(pages)} conversation pages")

        return PaginatedResponse(
            results=pages,
            page_number=page,
            has_next_page=bool(next_page_token),
        )

    def search_conversations_by_content(
        self, query: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Search Slack conversations by content/keywords.

        Args:
            query: Search query/keywords to find in conversation content
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        return self._search_conversations_paginated_response(
            self.slack_service.search_conversations_by_content,
            query,
            page=page,
            page_size=page_size,
        )

    def search_conversations_by_person(
        self, person: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Search conversations where a specific person participated.

        Args:
            person: Name or email of the person to search for
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        # Try to resolve person to email first, but also support Slack usernames/display names
        search_term = person

        return self._search_conversations_paginated_response(
            self.slack_service.search_conversations_with_person,
            search_term,
            page=page,
            page_size=page_size,
        )

    def search_conversations_by_channel(
        self, channel_name: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Search conversations in a specific channel.

        Args:
            channel_name: Name of the channel (without # prefix)
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        # Remove # prefix if present
        clean_channel_name = channel_name.lstrip("#")

        return self._search_conversations_paginated_response(
            self.slack_service.search_conversations_by_channel,
            clean_channel_name,
            page=page,
            page_size=page_size,
        )

    def search_conversations_by_date_range(
        self, start_date: str, end_date: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Search conversations within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        # For now, use content search (date filtering will be added later)
        # This will trigger ingestion and return all conversations
        query = f"conversations from {start_date} to {end_date}"
        return self._search_conversations_paginated_response(
            self.slack_service.search_conversations_by_content,
            query,
            page=page,
            page_size=page_size,
        )

    def search_recent_conversations(
        self, days: int = 7, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Search recent conversations from the last N days.

        Args:
            days: Number of days to look back
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        # For now, use content search to trigger ingestion
        query = f"recent conversations last {days} days"
        return self._search_conversations_paginated_response(
            self.slack_service.search_conversations_by_content,
            query,
            page=page,
            page_size=page_size,
        )

    def search_direct_messages(
        self, person: Optional[str] = None, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Search direct messages, optionally with a specific person.

        Args:
            person: Optional name/email of person for DMs (if None, returns all DMs)
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        if person:
            # Search DMs with specific person
            email = resolve_person_to_email(person, self.context)
            search_term = email if email else person
            return self._search_conversations_paginated_response(
                self.slack_service.search_conversations_with_person,
                search_term,
                page=page,
                page_size=page_size,
            )
        else:
            # Search all DMs - use content search to trigger ingestion
            query = "direct messages"
            return self._search_conversations_paginated_response(
                self.slack_service.search_conversations_by_content,
                query,
                page=page,
                page_size=page_size,
            )

    def search_threads_by_content(
        self, query: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackThread]:
        """Search Slack threads by content/keywords.

        Args:
            query: Search query/keywords to find in thread content
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        # For now, return empty results since thread search is not implemented yet
        # This would need a separate service method for thread-specific search
        logger.info(
            f"Searching Slack threads for content: '{query}' (not implemented yet)"
        )
        return PaginatedResponse(
            results=[],
            page_number=page,
            has_next_page=False,
        )

    def get_conversation_with_person(
        self, person: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[SlackConversation]:
        """Get the most recent conversation/DM with a specific person.

        Args:
            person: Name or email of the person
            page: Page number for pagination (0-based)
            page_size: Number of results per page
        """
        # Try to resolve person to email first
        email = resolve_person_to_email(person, self.context)
        search_term = email if email else person

        return self._search_conversations_paginated_response(
            self.slack_service.search_conversations_with_person,
            search_term,
            page=page,
            page_size=page_size,
        )
