"""Slack service for handling API interactions and page creation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from .client import SlackAPIClient
from .ingestion import SlackIngestionService
from .page import (
    SlackChannelListPage,
    SlackChannelPage,
    SlackConversationPage,
    SlackMessagePage,
    SlackMessageSummary,
    SlackThreadPage,
    SlackUserPage,
)
from .utils import SlackParser

logger = logging.getLogger(__name__)


class SlackService(ToolkitService):
    """Service for Slack API interactions and page creation."""

    def __init__(self, api_client: Optional[SlackAPIClient] = None) -> None:
        super().__init__()
        self.api_client = api_client or SlackAPIClient()
        self.parser = SlackParser()

        # Register page types with the page cache
        self.page_cache.register_page_type(SlackConversationPage)
        self.page_cache.register_page_type(SlackThreadPage)
        self.page_cache.register_page_type(SlackChannelPage)
        self.page_cache.register_page_type(SlackUserPage)
        self.page_cache.register_page_type(SlackChannelListPage)
        self.page_cache.register_page_type(SlackMessagePage)

        # Register handlers using decorators
        self._register_handlers()

        # Initialize ingestion service
        self.ingestion = SlackIngestionService(self)

        logger.info("Slack service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        @self.context.handler("slack_conversation")
        def handle_conversation(conversation_id: str) -> SlackConversationPage:
            return self.get_conversation_page(conversation_id)

        @self.context.handler("slack_thread")
        def handle_thread(thread_id: str) -> SlackThreadPage:
            return self.get_thread_page(thread_id)

        @self.context.handler("slack_channel")
        def handle_channel(channel_id: str) -> SlackChannelPage:
            return self.get_channel_page(channel_id)

        @self.context.handler("slack_user")
        def handle_user(user_id: str) -> SlackUserPage:
            return self.get_user_page(user_id)

        @self.context.handler("slack_channel_list")
        def handle_channel_list(workspace_id: str) -> SlackChannelListPage:
            return self.get_channel_list_page(workspace_id)

        @self.context.handler("slack_message")
        def handle_message(message_id: str) -> SlackMessagePage:
            logger.info(f"Message handler called for message_id: {message_id}")
            return self.get_message_page(message_id)

    def _get_existing_user_page(self, user_id: str) -> Optional[SlackUserPage]:
        """Get existing user page from cache."""
        uri = PageURI(root=self.context.root, type="slack_user", id=user_id)
        return self.page_cache.get_page(SlackUserPage, uri)

    def _get_existing_channel_page(self, channel_id: str) -> Optional[SlackChannelPage]:
        """Get existing channel page from cache."""
        uri = PageURI(root=self.context.root, type="slack_channel", id=channel_id)
        return self.page_cache.get_page(SlackChannelPage, uri)

    def get_user_display_name(self, user_id: str) -> str:
        """Get user display name for UI, creating user page if needed."""
        if not user_id:
            return "unknown"

        user_page = self.get_user_page(user_id)
        return user_page.display_name or user_page.real_name or user_page.name

    def get_conversation_page(self, conversation_id: str) -> SlackConversationPage:
        """Get conversation page, creating if needed."""
        # Try to get from cache first
        uri = PageURI(
            root=self.context.root, type="slack_conversation", id=conversation_id
        )
        existing_page = self.page_cache.get_page(SlackConversationPage, uri)

        if existing_page:
            return existing_page

        # Create conversation from channel ID (fetch recent messages)
        return self.create_conversation_page(conversation_id)

    def create_conversation_page(self, conversation_id: str) -> SlackConversationPage:
        """Create conversation page from channel ID by fetching recent messages."""
        # Assume conversation_id is a channel_id
        channel_id = conversation_id

        # Get channel page for info
        channel_page = self.get_channel_page(channel_id)
        channel_name = channel_page.name
        channel_type = channel_page.channel_type

        # Fetch recent messages
        messages, _ = self.api_client.get_conversation_history(
            channel_id=channel_id, limit=50
        )

        if not messages:
            raise ValueError(f"No messages found in channel {channel_id}")

        # Get time range
        timestamps = [float(msg.get("ts", "0")) for msg in messages]
        start_time = datetime.fromtimestamp(min(timestamps), tz=timezone.utc)
        end_time = datetime.fromtimestamp(max(timestamps), tz=timezone.utc)

        # Get participants
        user_ids = list(set(msg.get("user", "") for msg in messages))
        participants = []
        for user_id in user_ids:
            if user_id:
                display_name = self.get_user_display_name(user_id)
                participants.append(display_name)

        # Format message content using parser
        messages_content = self.parser.format_messages_for_content(
            messages, self.get_user_display_name
        )

        # Create permalink - use first message timestamp
        first_ts = messages[0].get("ts", "")
        permalink = (
            f"https://slack.com/app_redirect?channel={channel_id}&message_ts={first_ts}"
        )

        # Create URI
        uri = PageURI(
            root=self.context.root,
            type="slack_conversation",
            id=conversation_id,
            version=1,
        )

        conversation_page = SlackConversationPage(
            uri=uri,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_name=channel_name,
            channel_type=channel_type,
            start_time=start_time,
            end_time=end_time,
            message_count=len(messages),
            participants=participants,
            messages_content=messages_content,
            permalink=permalink,
        )

        # Store in cache
        self.page_cache.store_page(conversation_page)
        return conversation_page

    def get_message_page(self, message_id: str) -> SlackMessagePage:
        """Get message page, creating if needed."""
        logger.info(f"Getting message page for message_id: {message_id}")

        # Try to get from cache first
        uri = PageURI(root=self.context.root, type="slack_message", id=message_id)
        existing_page = self.page_cache.get_page(SlackMessagePage, uri)

        if existing_page:
            logger.info(f"Found cached message page for {message_id}")
            return existing_page

        logger.info(f"No cached page found, creating new message page for {message_id}")
        # Create message page on-demand
        return self.create_message_page(message_id)

    def create_message_page(self, message_id: str) -> SlackMessagePage:
        """Create a message page from message ID (format: channel_id_message_ts)."""
        logger.info(f"Creating message page for message ID: {message_id}")

        channel_id, message_ts = self.parser.decode_message_id(message_id)

        # Get channel page for info
        channel_page = self.get_channel_page(channel_id)
        channel_name = channel_page.name
        channel_type = channel_page.channel_type

        # Fetch the target message
        messages, _ = self.api_client.get_conversation_history(
            channel_id=channel_id, oldest=message_ts, inclusive=True, limit=1
        )
        if not messages:
            raise RuntimeError(f"Unable to find message: {message_id}")

        target_message = messages[0]

        user_id = target_message.get("user", "")
        display_name = self.get_user_display_name(user_id)

        # Parse timestamp
        timestamp_str = target_message.get("ts", "")
        timestamp = datetime.fromtimestamp(float(timestamp_str), tz=timezone.utc)

        # Create permalink
        permalink = f"https://slack.com/app_redirect?channel={channel_id}&message_ts={message_ts}"

        # Check if message is part of a thread
        thread_ts = target_message.get("thread_ts")

        # Create URI
        uri = PageURI(
            root=self.context.root, type="slack_message", id=message_id, version=1
        )

        page = SlackMessagePage(
            uri=uri,
            message_ts=message_ts,
            channel_id=channel_id,
            channel_name=channel_name,
            channel_type=channel_type,
            user_id=user_id,
            display_name=display_name,
            text=target_message.get("text", ""),
            timestamp=timestamp,
            thread_ts=thread_ts,
            permalink=permalink,
        )

        # Store in cache
        self.page_cache.store_page(page)

        return page

    def get_thread_page(self, thread_id: str) -> SlackThreadPage:
        """Get thread page, creating if needed."""
        # Try to get from cache first
        uri = PageURI(root=self.context.root, type="slack_thread", id=thread_id)
        existing_page = self.page_cache.get_page(SlackThreadPage, uri)

        if existing_page:
            return existing_page

        # Create from API if not cached
        return self.create_thread_page(thread_id)

    def create_thread_page(self, thread_id: str) -> SlackThreadPage:
        """Create a SlackThreadPage from thread ID (format: channel_id_thread_ts)."""
        channel_id, thread_ts = self.parser.decode_thread_id(thread_id)

        # Get thread messages from API
        messages = self.api_client.get_thread_replies(channel_id, thread_ts)

        if not messages:
            raise ValueError(f"Thread {thread_id} contains no messages")

        # Get channel page for info
        channel_page = self.get_channel_page(channel_id)
        channel_name = channel_page.name

        # Parse messages into SlackMessageSummary objects
        message_summaries = []
        participants = set()

        for msg in messages:
            user_id = msg.get("user", "")
            user_name = self.get_user_display_name(user_id)
            participants.add(user_name)

            timestamp_str = msg.get("ts", "")
            timestamp = datetime.fromtimestamp(float(timestamp_str), tz=timezone.utc)

            summary = SlackMessageSummary(
                display_name=user_name, text=msg.get("text", ""), timestamp=timestamp
            )
            message_summaries.append(summary)

        # Get parent message (first message)
        parent_message = messages[0].get("text", "") if messages else ""

        # Get time info
        created_at = (
            message_summaries[0].timestamp
            if message_summaries
            else datetime.now(tz=timezone.utc)
        )
        last_reply_at = (
            message_summaries[-1].timestamp if len(message_summaries) > 1 else None
        )

        # Create permalink
        permalink = f"https://slack.com/app_redirect?channel={channel_id}&message_ts={thread_ts}"

        # Create URI
        uri = PageURI(
            root=self.context.root, type="slack_thread", id=thread_id, version=1
        )

        page = SlackThreadPage(
            uri=uri,
            thread_ts=thread_ts,
            channel_id=channel_id,
            channel_name=channel_name,
            parent_message=parent_message,
            messages=message_summaries,
            message_count=len(message_summaries),
            participants=list(participants),
            created_at=created_at,
            last_reply_at=last_reply_at,
            permalink=permalink,
        )

        # Store in cache
        self.page_cache.store_page(page)
        return page

    def get_channel_page(self, channel_id: str) -> SlackChannelPage:
        """Get channel page, creating if needed."""
        # Try to get from cache first
        uri = PageURI(root=self.context.root, type="slack_channel", id=channel_id)
        existing_page = self.page_cache.get_page(SlackChannelPage, uri)

        if existing_page:
            return existing_page

        # Create from API if not cached
        return self.create_channel_page(channel_id)

    def create_channel_page(self, channel_id: str) -> SlackChannelPage:
        """Create a SlackChannelPage from channel ID."""
        channel_info = self.api_client.get_channel_info(channel_id)

        # Parse channel data
        name = channel_info.get("name", channel_id)
        channel_type = self.parser.determine_channel_type(channel_info)
        topic = channel_info.get("topic", {}).get("value")
        purpose = channel_info.get("purpose", {}).get("value")

        # Get member count
        try:
            members = self.api_client.get_channel_members(channel_id)
            member_count = len(members)
        except Exception as e:
            logger.warning(f"Failed to get member count for {channel_id}: {e}")
            member_count = 0

        # Parse timestamps
        created_ts = channel_info.get("created", 0)
        created = (
            datetime.fromtimestamp(created_ts, tz=timezone.utc)
            if created_ts
            else datetime.now(tz=timezone.utc)
        )

        is_archived = channel_info.get("is_archived", False)

        # Get last activity (would need to fetch recent messages)
        last_activity = None  # TODO: Implement if needed

        # Create permalink
        permalink = f"https://slack.com/app_redirect?channel={channel_id}"

        # Create URI
        uri = PageURI(
            root=self.context.root, type="slack_channel", id=channel_id, version=1
        )

        page = SlackChannelPage(
            uri=uri,
            channel_id=channel_id,
            name=name,
            channel_type=channel_type,
            topic=topic,
            purpose=purpose,
            member_count=member_count,
            created=created,
            is_archived=is_archived,
            last_activity=last_activity,
            message_urls=[],  # Empty by default, can be populated on demand
            permalink=permalink,
        )

        # Store in cache
        self.page_cache.store_page(page)
        return page

    def get_user_page(self, user_id: str) -> SlackUserPage:
        """Get user page, creating if needed."""
        # Try to get from cache first
        uri = PageURI(root=self.context.root, type="slack_user", id=user_id)
        existing_page = self.page_cache.get_page(SlackUserPage, uri)

        if existing_page:
            return existing_page

        # Create from API if not cached
        return self.create_user_page(user_id)

    def create_user_page(self, user_id: str) -> SlackUserPage:
        """Create a SlackUserPage from user ID."""
        user_info = self.api_client.get_user_info(user_id)
        profile = user_info.get("profile", {})

        # Parse user data
        name = user_info.get("name", user_id)
        real_name = user_info.get("real_name")
        display_name = profile.get("display_name")
        email = profile.get("email")
        title = profile.get("title")

        is_bot = user_info.get("is_bot", False)
        is_admin = user_info.get("is_admin", False)

        status_text = profile.get("status_text")
        status_emoji = profile.get("status_emoji")

        last_updated = datetime.now(tz=timezone.utc)

        # Create URI
        uri = PageURI(root=self.context.root, type="slack_user", id=user_id, version=1)

        page = SlackUserPage(
            uri=uri,
            user_id=user_id,
            name=name,
            real_name=real_name,
            display_name=display_name,
            email=email,
            title=title,
            is_bot=is_bot,
            is_admin=is_admin,
            status_text=status_text,
            status_emoji=status_emoji,
            last_updated=last_updated,
        )

        # Store in cache
        self.page_cache.store_page(page)
        return page

    def get_channel_list_page(
        self, workspace_id: str, refresh: bool = False
    ) -> SlackChannelListPage:
        """Get or create channel list page using ingestion service."""
        return self.ingestion.create_channel_list_page(workspace_id, refresh)

    def search_messages(
        self, query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search conversations and return URIs with pagination."""
        try:
            # Use Slack search API
            page_num = 1
            if page_token:
                try:
                    page_num = int(page_token)
                except ValueError:
                    page_num = 1

            messages, pagination = self.api_client.search_messages(
                query=query, count=page_size, page=page_num
            )

            # Convert to PageURIs (return message pages for individual messages)
            uris = []
            processed_threads = set()

            logger.info(f"Processing {len(messages)} search result messages")

            for i, msg in enumerate(messages):
                channel_id = msg.get("channel", {}).get("id", "")
                ts = msg.get("ts", "")
                thread_ts = msg.get("thread_ts")
                text = msg.get("text", "")
                user = msg.get("user", "")

                logger.info(
                    f"Message {i+1}: channel_id={channel_id}, ts={ts}, user={user}"
                )
                logger.info(
                    f"Message {i+1} text: {text[:100]}{'...' if len(text) > 100 else ''}"
                )

                if thread_ts:
                    logger.info(f"Message {i+1} is part of thread: {thread_ts}")

                if thread_ts and f"{channel_id}_{thread_ts}" not in processed_threads:
                    # This is part of a thread - return the thread page
                    thread_id = self.parser.encode_thread_id(channel_id, thread_ts)
                    logger.info(f"Creating thread URI for {thread_id}")
                    uri = PageURI(
                        root=self.context.root, type="slack_thread", id=thread_id
                    )
                    uris.append(uri)
                    processed_threads.add(thread_id)
                else:
                    # Regular message or thread message - return message page
                    message_id = self.parser.encode_message_id(channel_id, ts)
                    logger.info(
                        f"Creating message URI for {message_id} (channel={channel_id}, ts={ts})"
                    )
                    uri = PageURI(
                        root=self.context.root,
                        type="slack_message",
                        id=message_id,
                    )
                    uris.append(uri)

            logger.info(f"Generated {len(uris)} URIs from search results")

            # Determine next page token
            next_token = None
            if pagination.get("page", 1) < pagination.get("page_count", 1):
                next_token = str(pagination["page"] + 1)

            return uris, next_token

        except Exception as e:
            logger.error(f"Error searching conversations: {e}")
            return [], None

    @property
    def toolkit(self) -> "SlackToolkit":
        """Get the toolkit for this service."""
        return SlackToolkit(slack_service=self)

    @property
    def name(self) -> str:
        return "slack"


class SlackToolkit(RetrieverToolkit):
    """Toolkit for retrieving Slack conversations and threads."""

    def __init__(self, slack_service: SlackService):
        super().__init__()
        self.slack_service = slack_service
        logger.info("Slack toolkit initialized")

    def _search_messages(
        self,
        query: str,
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> PaginatedResponse[SlackMessagePage]:
        """Helper method to handle pagination for message searches."""
        # Pass cursor as positional argument, like Gmail service
        uris, next_page_token = self.slack_service.search_messages(
            query, page_token=cursor, page_size=page_size
        )

        pages = []

        for uri in uris:
            page = self.context.get_page(uri)
            if isinstance(page, SlackMessagePage):
                pages.append(page)
            else:
                logger.error(f"Resolved page is not SlackMessagePage: {type(page)}")
                raise ValueError(f"Resolved page is not SlackMessagePage: {type(page)}")

        return PaginatedResponse(
            results=pages,
            next_cursor=next_page_token,
        )

    @tool()
    def search_messages_by_content(
        self, query: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search Slack conversations by content/keywords.

        Args:
            query: Search query/keywords to find in conversation content
            cursor: Pagination cursor for next page
            page_size: Number of results per page
        """
        return self._search_messages(query, cursor)

    @tool()
    def search_messages_by_channel(
        self, channel_name: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search conversations in a specific channel.

        Args:
            channel_name: Name of the channel (without # prefix)
            cursor: Pagination cursor for next page
            page_size: Number of results per page
        """
        # Clean channel name and build search query
        clean_channel_name = channel_name.lstrip("#")
        query = f"in:#{clean_channel_name}"

        return self._search_messages(query, cursor)

    @tool()
    def search_messages_by_person(
        self, person: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search conversations where a specific person participated.

        Args:
            person: Person identifier (@username or user ID)
            cursor: Pagination cursor for next page
        """
        # Validate and format person identifier
        validated_person = self.slack_service.parser.validate_person_identifier(person)

        # Build search query
        query = f"from:{validated_person}"

        return self._search_messages(query, cursor)

    @tool()
    def search_messages_by_date_range(
        self,
        start_date: str,
        num_days: int,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search conversations within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            cursor: Pagination cursor for next page
            page_size: Number of results per page
        """
        end_date = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=num_days)
        query = f"after:{start_date} before:{end_date.strftime('%Y-%m-%d')}"

        return self._search_messages(query, cursor)

    @tool()
    def search_recent_messages(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search recent conversations from the last N days.

        Args:
            days: Number of days to look back
            cursor: Pagination cursor for next page
        """
        date = datetime.now() - timedelta(days=days)
        date_str = date.strftime("%Y-%m-%d")
        query = f"after:{date_str}"

        return self._search_messages(query, cursor)

    @tool()
    def search_direct_messages(
        self,
        person: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search direct messages, optionally with a specific person.

        Args:
            person: Optional person identifier (@username or user ID) for DMs (if None, returns all DMs)
            cursor: Pagination cursor for next page
        """
        if person:
            validated_person = self.slack_service.parser.validate_person_identifier(
                person
            )
            query = f"in:{validated_person}"
        else:
            query = "in:@"  # All DMs

        response = self._search_messages(query, cursor)
        logger.info(f"Direct messages response: {response}")
        print(response)
        return response

    @tool()
    def get_conversation_with_person(
        self, person: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Get conversations involving a specific person.

        Args:
            person: Person identifier (@username or user ID)
            cursor: Pagination cursor for next page
        """
        # Validate and format person identifier
        validated_person = self.slack_service.parser.validate_person_identifier(person)
        query = validated_person  # Already formatted for search

        return self._search_messages(query, cursor)

    @property
    def name(self) -> str:
        return "slack"
