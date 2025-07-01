"""Slack service for handling API interactions and page creation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from chonkie import RecursiveChunker

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from .client import SlackAPIClient
from .page import (
    SlackChannelListPage,
    SlackChannelPage,
    SlackConversationPage,
    SlackMessagePage,
    SlackMessageSummary,
    SlackThreadPage,
    SlackUserPage,
)

logger = logging.getLogger(__name__)


class SlackService(ToolkitService):
    """Service for Slack API interactions and page creation."""

    def __init__(self, api_client: Optional[SlackAPIClient] = None) -> None:
        super().__init__()
        self.api_client = api_client or SlackAPIClient()
        self.chunker = RecursiveChunker(chunk_size=4000)

        # Cache for user info to avoid repeated API calls
        self._user_cache: Dict[str, Dict[str, Any]] = {}
        self._channel_cache: Dict[str, Dict[str, Any]] = {}

        # Register page types with the page cache
        self.page_cache.register_page_type(SlackConversationPage)
        self.page_cache.register_page_type(SlackThreadPage)
        self.page_cache.register_page_type(SlackChannelPage)
        self.page_cache.register_page_type(SlackUserPage)
        self.page_cache.register_page_type(SlackChannelListPage)
        self.page_cache.register_page_type(SlackMessagePage)

        # Register handlers using decorators
        self._register_handlers()

        # Ingest channel list on initialization for reference
        self._initialize_channel_data()

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

    def _get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user info with caching."""
        if user_id not in self._user_cache:
            try:
                user_info = self.api_client.get_user_info(user_id)
                self._user_cache[user_id] = user_info
            except Exception as e:
                logger.warning(f"Failed to get user info for {user_id}: {e}")
                # Return minimal user info
                self._user_cache[user_id] = {
                    "id": user_id,
                    "name": user_id,
                    "real_name": None,
                    "profile": {"display_name": None},
                }
        return self._user_cache[user_id]

    def _get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get channel info with caching."""
        if channel_id not in self._channel_cache:
            try:
                channel_info = self.api_client.get_channel_info(channel_id)
                self._channel_cache[channel_id] = channel_info
            except Exception as e:
                logger.warning(f"Failed to get channel info for {channel_id}: {e}")
                # Return minimal channel info
                self._channel_cache[channel_id] = {
                    "id": channel_id,
                    "name": channel_id,
                    "is_channel": True,
                    "is_group": False,
                    "is_im": False,
                    "is_mpim": False,
                }
        return self._channel_cache[channel_id]

    def _get_user_display_name(self, user_id: str) -> str:
        """Get user display name for UI."""
        user_info = self._get_user_info(user_id)

        # Prefer display name, then real name, then username
        display_name = user_info.get("profile", {}).get("display_name")
        if display_name:
            return str(display_name)

        real_name = user_info.get("real_name")
        if real_name:
            return str(real_name)

        name = user_info.get("name", user_id)
        return str(name)

    def _validate_person_identifier(self, person: str) -> str:
        """Validate and format person identifier for Slack search.

        Args:
            person: Person identifier (should start with @ or be a user ID)

        Returns:
            Formatted person identifier for search

        Raises:
            ValueError: If person identifier format is invalid
        """
        if not person:
            raise ValueError("Person identifier cannot be empty")

        # If it starts with @, it's a username/handle - use as is
        if person.startswith("@"):
            return person

        # If it looks like a user ID (starts with U), use as is
        if person.startswith("U") and len(person) > 5:
            return f"<@{person}>"  # Format for search

        # Otherwise, it's likely a display name or email - we don't support this yet
        raise ValueError(
            f"Person identifier '{person}' is not supported. "
            f"Please use either @username (e.g., '@john.doe') or user ID (e.g., 'U1234567890'). "
            f"Display names and email addresses are not yet supported."
        )

    def _encode_message_id(self, channel_id: str, message_ts: str) -> str:
        """Encode channel ID and message timestamp into a URI-safe message ID.

        Args:
            channel_id: Slack channel ID
            message_ts: Message timestamp

        Returns:
            Encoded message ID safe for PageURI
        """
        # Use underscore as separator since colons aren't allowed in PageURI IDs
        return f"{channel_id}_{message_ts}"

    def _decode_message_id(self, message_id: str) -> tuple[str, str]:
        """Decode message ID back to channel ID and message timestamp.

        Args:
            message_id: Encoded message ID

        Returns:
            Tuple of (channel_id, message_ts)

        Raises:
            ValueError: If message ID format is invalid
        """
        try:
            # Split on last underscore to handle cases where channel_id might have underscores
            parts = message_id.rsplit("_", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            return parts[0], parts[1]
        except ValueError:
            raise ValueError(
                f"Invalid message ID format: {message_id}. Expected 'channel_id_message_ts'"
            )

    def _encode_thread_id(self, channel_id: str, thread_ts: str) -> str:
        """Encode channel ID and thread timestamp into a URI-safe thread ID.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp

        Returns:
            Encoded thread ID safe for PageURI
        """
        # Use underscore as separator since colons aren't allowed in PageURI IDs
        return f"{channel_id}_{thread_ts}"

    def _decode_thread_id(self, thread_id: str) -> tuple[str, str]:
        """Decode thread ID back to channel ID and thread timestamp.

        Args:
            thread_id: Encoded thread ID

        Returns:
            Tuple of (channel_id, thread_ts)

        Raises:
            ValueError: If thread ID format is invalid
        """
        try:
            # Split on last underscore to handle cases where channel_id might have underscores
            parts = thread_id.rsplit("_", 1)
            if len(parts) != 2:
                raise ValueError("Invalid format")
            return parts[0], parts[1]
        except ValueError:
            raise ValueError(
                f"Invalid thread ID format: {thread_id}. Expected 'channel_id_thread_ts'"
            )

    def _determine_channel_type(self, channel_info: Dict[str, Any]) -> str:
        """Determine channel type string."""
        if channel_info.get("is_channel"):
            return "public_channel"
        elif channel_info.get("is_group"):
            return "private_channel"
        elif channel_info.get("is_im"):
            return "im"
        elif channel_info.get("is_mpim"):
            return "mpim"
        else:
            return "unknown"

    def _format_messages_for_content(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages into readable content."""
        formatted_messages = []

        for msg in messages:
            user_id = msg.get("user", "unknown")
            user_name = self._get_user_display_name(user_id)
            text = msg.get("text", "")

            # Format timestamp
            timestamp = msg.get("ts", "")
            if timestamp:
                try:
                    dt = datetime.fromtimestamp(float(timestamp))
                    time_str = dt.strftime("%Y-%m-%d %H:%M")
                except (ValueError, TypeError):
                    time_str = timestamp
            else:
                time_str = "unknown"

            formatted_messages.append(f"[{time_str}] {user_name}: {text}")

        return "\n".join(formatted_messages)

    def _chunk_messages_by_time(
        self,
        messages: List[Dict[str, Any]],
        channel_id: str,
        channel_name: Optional[str],
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
        channel_name: Optional[str],
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

        # Get participants
        participants = list(
            set(self._get_user_display_name(msg.get("user", "")) for msg in messages)
        )

        # Format message content
        messages_content = self._format_messages_for_content(messages)

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

        # Get channel info
        channel_info = self._get_channel_info(channel_id)
        channel_name = channel_info.get("name")
        channel_type = self._determine_channel_type(channel_info)

        # Fetch recent messages
        messages, _ = self.api_client.get_conversation_history(
            channel_id=channel_id, limit=50
        )

        if not messages:
            raise ValueError(f"No messages found in channel {channel_id}")

        # Create conversation pages
        pages = self._chunk_messages_by_time(
            messages, channel_id, channel_name, channel_type, max_chunk_size=4000
        )

        if not pages:
            raise ValueError(
                f"Failed to create conversation page for {conversation_id}"
            )

        # Return the most recent page
        target_page = pages[0]  # Most recent

        # Update conversation_id and URI to match request
        uri = PageURI(
            root=self.context.root,
            type="slack_conversation",
            id=conversation_id,
            version=1,
        )

        conversation_page = SlackConversationPage(
            uri=uri,
            conversation_id=conversation_id,
            channel_id=target_page.channel_id,
            channel_name=target_page.channel_name,
            channel_type=target_page.channel_type,
            start_time=target_page.start_time,
            end_time=target_page.end_time,
            message_count=target_page.message_count,
            participants=target_page.participants,
            messages_content=target_page.messages_content,
            permalink=target_page.permalink,
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

        channel_id, message_ts = self._decode_message_id(message_id)

        # Get channel info
        channel_info = self._get_channel_info(channel_id)
        channel_name = channel_info.get("name")
        channel_type = self._determine_channel_type(channel_info)

        # Fetch the target message
        messages, _ = self.api_client.get_conversation_history(
            channel_id=channel_id, oldest=message_ts, inclusive=True, limit=1
        )
        if not messages:
            raise RuntimeError(f"Unable to find message: {message_id}")

        target_message = messages[0]

        user_id = target_message.get("user", "")
        display_name = self._get_user_display_name(user_id)

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
        channel_id, thread_ts = self._decode_thread_id(thread_id)

        # Get thread messages from API
        messages = self.api_client.get_thread_replies(channel_id, thread_ts)

        if not messages:
            raise ValueError(f"Thread {thread_id} contains no messages")

        # Get channel info
        channel_info = self._get_channel_info(channel_id)
        channel_name = channel_info.get("name")

        # Parse messages into SlackMessageSummary objects
        message_summaries = []
        participants = set()

        for msg in messages:
            user_id = msg.get("user", "")
            user_name = self._get_user_display_name(user_id)
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
        self.context.page_cache.store_page(page)
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
        channel_info = self._get_channel_info(channel_id)

        # Parse channel data
        name = channel_info.get("name", channel_id)
        channel_type = self._determine_channel_type(channel_info)
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
            permalink=permalink,
        )

        # Store in cache
        self.context.page_cache.store_page(page)
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
        user_info = self._get_user_info(user_id)
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

    def _initialize_channel_data(self) -> None:
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
                # Still populate the channel cache for fast lookups
                for channel_info in existing_page.channels:
                    channel_id = channel_info.get("id")
                    if channel_id and channel_id not in self._channel_cache:
                        # Convert back to API format for cache
                        self._channel_cache[channel_id] = {
                            "id": channel_id,
                            "name": channel_info.get("name"),
                            "is_channel": channel_info.get("type") == "public_channel",
                            "is_group": channel_info.get("type") == "private_channel",
                            "is_im": channel_info.get("type") == "im",
                            "is_mpim": channel_info.get("type") == "mpim",
                            "topic": {"value": channel_info.get("topic")},
                            "purpose": {"value": channel_info.get("purpose")},
                            "num_members": channel_info.get("member_count", 0),
                            "is_archived": channel_info.get("is_archived", False),
                        }
                return

            # Create new channel list page
            self.ingest_all_channels()
            logger.info("Channel data initialization complete")
        except Exception as e:
            logger.warning(f"Failed to initialize channel data: {e}")

    def get_channel_list_page(
        self, workspace_id: str, refresh: bool = False
    ) -> SlackChannelListPage:
        """Get or create channel list page.

        Args:
            workspace_id: Slack workspace/team ID
            refresh: If True, force refresh from API even if cached

        Returns:
            SlackChannelListPage with workspace channels
        """
        if refresh:
            return self.create_channel_list_page(workspace_id, refresh=True)

        uri = PageURI(
            root=self.context.root,
            type="slack_channel_list",
            id=workspace_id,
            version=1,
        )

        existing_page = self.page_cache.get_page(SlackChannelListPage, uri)
        if existing_page:
            return existing_page

        return self.create_channel_list_page(workspace_id)

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
        try:
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
                channel_type = self._determine_channel_type(channel)
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

        except Exception as e:
            logger.error(f"Failed to create channel list page: {e}")
            raise

    def refresh_channel_list(self) -> SlackChannelListPage:
        """Force refresh the channel list from Slack API."""
        try:
            # Get workspace info
            auth_info = self.api_client.test_auth()
            workspace_id = auth_info.get("team_id", "unknown")

            # Clear the channel cache to force fresh data
            self._channel_cache.clear()

            # Create fresh channel list page
            return self.create_channel_list_page(workspace_id, refresh=True)

        except Exception as e:
            logger.error(f"Failed to refresh channel list: {e}")
            raise

    def ingest_all_channels(self) -> int:
        """Ingest all workspace channels for reference."""
        try:
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
                # Still populate the channel cache if not already done
                if not self._channel_cache:
                    for channel_info in existing_page.channels:
                        channel_id = channel_info.get("id")
                        if channel_id:
                            # Convert back to API format for cache
                            self._channel_cache[channel_id] = {
                                "id": channel_id,
                                "name": channel_info.get("name"),
                                "is_channel": channel_info.get("type")
                                == "public_channel",
                                "is_group": channel_info.get("type")
                                == "private_channel",
                                "is_im": channel_info.get("type") == "im",
                                "is_mpim": channel_info.get("type") == "mpim",
                                "topic": {"value": channel_info.get("topic")},
                                "purpose": {"value": channel_info.get("purpose")},
                                "num_members": channel_info.get("member_count", 0),
                                "is_archived": channel_info.get("is_archived", False),
                            }
                return existing_page.total_channels

            # Create the channel list page (this will fetch all channels with pagination)
            channel_list_page = self.create_channel_list_page(workspace_id)

            # Populate the channel cache from the fetched data
            for channel_info in channel_list_page.channels:
                channel_id = channel_info.get("id")
                if channel_id:
                    # Convert back to API format for cache
                    self._channel_cache[channel_id] = {
                        "id": channel_id,
                        "name": channel_info.get("name"),
                        "is_channel": channel_info.get("type") == "public_channel",
                        "is_group": channel_info.get("type") == "private_channel",
                        "is_im": channel_info.get("type") == "im",
                        "is_mpim": channel_info.get("type") == "mpim",
                        "topic": {"value": channel_info.get("topic")},
                        "purpose": {"value": channel_info.get("purpose")},
                        "num_members": channel_info.get("member_count", 0),
                        "is_archived": channel_info.get("is_archived", False),
                    }

            logger.info(f"Ingested {channel_list_page.total_channels} channels")
            return channel_list_page.total_channels

        except Exception as e:
            logger.error(f"Failed to ingest all channels: {e}")
            return 0

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
                    thread_id = self._encode_thread_id(channel_id, thread_ts)
                    logger.info(f"Creating thread URI for {thread_id}")
                    uri = PageURI(
                        root=self.context.root, type="slack_thread", id=thread_id
                    )
                    uris.append(uri)
                    processed_threads.add(thread_id)
                else:
                    # Regular message or thread message - return message page
                    message_id = self._encode_message_id(channel_id, ts)
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

    def ingest_channel(self, channel_id: str) -> int:
        """Ingest all messages from a channel and create conversation pages."""
        logger.info(f"Starting ingestion of channel {channel_id}")

        # Get channel info
        channel_info = self._get_channel_info(channel_id)
        channel_name = channel_info.get("name")
        channel_type = self._determine_channel_type(channel_info)

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
        validated_person = self.slack_service._validate_person_identifier(person)

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
            validated_person = self.slack_service._validate_person_identifier(person)
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
        validated_person = self.slack_service._validate_person_identifier(person)
        query = validated_person  # Already formatted for search

        return self._search_messages(query, cursor)

    @property
    def name(self) -> str:
        return "slack"
