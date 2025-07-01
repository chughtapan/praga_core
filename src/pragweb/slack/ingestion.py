"""Slack ingestion service for bulk data operations and channel initialization."""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List

from praga_core.types import PageURI

from .page import SlackChannelListPage, SlackConversationPage
from .utils import SlackParser

if TYPE_CHECKING:
    from .service import SlackService

logger = logging.getLogger(__name__)


class SlackIngestionService:
    """Sidecar service for Slack bulk data ingestion and channel operations."""

    def __init__(self, slack_service: "SlackService"):
        """Initialize with reference to main slack service."""
        self.slack_service = slack_service
        self.api_client = slack_service.api_client
        self.context = slack_service.context
        self.page_cache = slack_service.page_cache
        self.parser = SlackParser()

    def initialize_channel_data(self) -> None:
        """Initialize channel data by ingesting all channels."""
        try:
            logger.info("Initializing Slack channel data...")

            # Get workspace ID from auth test
            auth_info = self.api_client.test_auth()
            workspace_id = auth_info.get("team_id", "unknown")

            # Check if channel list page already exists
            uri = PageURI(
                root=self.context.root,
                type="slack_channel_list",
                id=workspace_id,
                version=1,
            )
            existing_page = self.page_cache.get_page(SlackChannelListPage, uri)

            if existing_page:
                logger.info("Channel data already exists in cache")
                return

            # Create new channel list page
            self.ingest_all_channels()
            logger.info("Channel data initialization complete")
        except Exception as e:
            logger.warning(f"Failed to initialize channel data: {e}")
            raise

    def ingest_all_channels(self) -> int:
        """Ingest all workspace channels for reference."""
        # Get workspace info from auth test (no team scope required)
        auth_info = self.api_client.test_auth()
        workspace_id = auth_info.get("team_id", "unknown")

        # Check if channel list page already exists
        uri = PageURI(
            root=self.context.root,
            type="slack_channel_list",
            id=workspace_id,
            version=1,
        )
        existing_page = self.page_cache.get_page(SlackChannelListPage, uri)

        if existing_page:
            logger.info(
                f"Channel list already cached with {existing_page.total_channels} channels"
            )
            return existing_page.total_channels

        # Create the channel list page (this will fetch all channels with pagination)
        channel_list_page = self.create_channel_list_page(workspace_id)

        logger.info(f"Ingested {channel_list_page.total_channels} channels")
        return channel_list_page.total_channels

    def create_channel_list_page(
        self, workspace_id: str, refresh: bool = False
    ) -> SlackChannelListPage:
        """Create a new channel list page with all workspace channels.

        Args:
            workspace_id: Slack workspace/team ID
            refresh: If True, force refresh even if cached page exists

        Returns:
            SlackChannelListPage with all workspace channels

        Note:
            This method automatically handles pagination through the API client's list_channels() method,
            which follows cursor pagination to retrieve all channels in the workspace.
        """
        # Check for existing page unless refresh is requested
        if not refresh:
            uri = PageURI(
                root=self.context.root,
                type="slack_channel_list",
                id=workspace_id,
                version=1,
            )
            existing_page = self.page_cache.get_page(SlackChannelListPage, uri)
            if existing_page:
                # Check if data is stale (older than 1 hour)
                if (
                    datetime.now(timezone.utc) - existing_page.last_updated
                ).total_seconds() < 3600:
                    logger.info("Using cached channel list page (fresh)")
                    return existing_page
                else:
                    logger.info("Cached channel list page is stale, refreshing...")

        # Get workspace info from auth test (no team scope required)
        auth_info = self.api_client.test_auth()
        workspace_name = auth_info.get("team", "Unknown Workspace")
        workspace_id = auth_info.get("team_id", workspace_id)

        # Get all channels with automatic pagination handling
        logger.info("Fetching all workspace channels...")
        all_channels = self.api_client.list_channels()

        # Count channel types and extract data
        public_count = 0
        private_count = 0
        channel_data = []

        for channel in all_channels:
            channel_type = self.parser.determine_channel_type(channel)
            if channel_type == "public_channel":
                public_count += 1
            elif channel_type == "private_channel":
                private_count += 1

            # Extract relevant channel info
            channel_info = {
                "id": channel.get("id"),
                "name": channel.get("name"),
                "type": channel_type,
                "topic": channel.get("topic", {}).get("value"),
                "purpose": channel.get("purpose", {}).get("value"),
                "member_count": channel.get("num_members", 0),
                "is_archived": channel.get("is_archived", False),
            }
            channel_data.append(channel_info)

        # Create URI
        uri = PageURI(
            root=self.context.root,
            type="slack_channel_list",
            id=workspace_id,
            version=1,
        )

        # Create page
        channel_list_page = SlackChannelListPage(
            uri=uri,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            total_channels=len(all_channels),
            public_channels=public_count,
            private_channels=private_count,
            channels=channel_data,
            last_updated=datetime.now(timezone.utc),
        )

        # Cache the page
        self.page_cache.store_page(channel_list_page)

        logger.info(
            f"Created channel list page with {len(all_channels)} channels "
            f"({public_count} public, {private_count} private)"
        )
        return channel_list_page

    def refresh_channel_list(self) -> SlackChannelListPage:
        """Force refresh the channel list from Slack API."""
        # Get workspace info
        auth_info = self.api_client.test_auth()
        workspace_id = auth_info.get("team_id", "unknown")

        # Create fresh channel list page
        return self.create_channel_list_page(workspace_id, refresh=True)

    def ingest_channel(self, channel_id: str) -> int:
        """Ingest all messages from a channel and create conversation pages."""
        logger.info(f"Starting ingestion of channel {channel_id}")

        # Get channel info using the main service method
        channel_page = self.slack_service.get_channel_page(channel_id)
        channel_name = channel_page.name
        channel_type = channel_page.channel_type

        # Fetch all messages
        all_messages = []
        cursor = None

        while True:
            messages, next_cursor = self.api_client.get_conversation_history(
                channel_id=channel_id, limit=1000, cursor=cursor
            )

            all_messages.extend(messages)

            if not next_cursor:
                break
            cursor = next_cursor

        logger.info(f"Fetched {len(all_messages)} messages from channel {channel_id}")

        # Chunk messages into conversations
        conversation_pages = self._chunk_messages_by_time(
            all_messages, channel_id, channel_name, channel_type
        )

        # Store conversation pages in cache
        stored_count = 0
        for page in conversation_pages:
            if self.page_cache.store_page(page):
                stored_count += 1

        logger.info(
            f"Created and stored {stored_count} conversation pages for channel {channel_id}"
        )
        return stored_count

    def _chunk_messages_by_time(
        self,
        messages: List[Dict[str, Any]],
        channel_id: str,
        channel_name: str,
        channel_type: str,
        max_chunk_size: int = 4000,
    ) -> List[SlackConversationPage]:
        """Chunk messages into conversation pages by time and content size."""
        if not messages:
            return []

        # Sort messages by timestamp
        sorted_messages = sorted(messages, key=lambda m: float(m.get("ts", "0")))

        conversation_pages: List[SlackConversationPage] = []
        current_chunk: List[Dict[str, Any]] = []
        current_size = 0

        for message in sorted_messages:
            message_text = message.get("text", "")
            message_size = len(message_text)

            # If adding this message would exceed chunk size, create a new chunk
            if current_chunk and (current_size + message_size > max_chunk_size):
                # Create conversation page for current chunk
                if current_chunk:
                    page = self._create_conversation_page(
                        current_chunk,
                        channel_id,
                        channel_name,
                        channel_type,
                        len(conversation_pages),
                    )
                    conversation_pages.append(page)

                # Start new chunk
                current_chunk = [message]
                current_size = message_size
            else:
                current_chunk.append(message)
                current_size += message_size

        # Handle remaining messages
        if current_chunk:
            page = self._create_conversation_page(
                current_chunk,
                channel_id,
                channel_name,
                channel_type,
                len(conversation_pages),
            )
            conversation_pages.append(page)

        return conversation_pages

    def _create_conversation_page(
        self,
        messages: List[Dict[str, Any]],
        channel_id: str,
        channel_name: str,
        channel_type: str,
        chunk_index: int,
    ) -> SlackConversationPage:
        """Create a SlackConversationPage from a chunk of messages."""
        if not messages:
            raise ValueError("Cannot create conversation page from empty messages")

        # Get time range
        timestamps = [float(msg.get("ts", "0")) for msg in messages]
        start_time = datetime.fromtimestamp(min(timestamps), tz=timezone.utc)
        end_time = datetime.fromtimestamp(max(timestamps), tz=timezone.utc)

        # Get participants - need to get display names
        user_ids = list(set(msg.get("user", "") for msg in messages))
        participants = []
        for user_id in user_ids:
            if user_id:
                user_page = self.slack_service.get_user_page(user_id)
                display_name = (
                    user_page.display_name or user_page.real_name or user_page.name
                )
                participants.append(display_name)

        # Format message content using parser
        messages_content = self.parser.format_messages_for_content(
            messages,
            lambda user_id: self.slack_service.get_user_page(user_id).display_name
            or self.slack_service.get_user_page(user_id).real_name
            or self.slack_service.get_user_page(user_id).name,
        )

        # Create conversation ID
        conversation_id = f"{channel_id}_{int(min(timestamps))}_{chunk_index}"

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

        return SlackConversationPage(
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
