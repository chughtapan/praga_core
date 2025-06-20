"""Slack service for fetching and caching Slack conversations."""

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from chonkie import RecursiveChunker
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from sqlmodel import Field, Session, SQLModel, create_engine, select

from praga_core.context import ServerContext
from praga_core.types import PageURI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth.slack_auth import SlackAuthenticator  # noqa: E402
from pages.slack import SlackConversation, SlackThread  # noqa: E402

logger = logging.getLogger(__name__)


class ChannelSummaryRecord(SQLModel, table=True):
    """Cache record for channel summaries and ingestion status."""

    __tablename__ = "channel_summaries"

    id: str = Field(primary_key=True)  # Channel ID (primary key)
    name: str
    type: str  # "public_channel", "private_channel", "im", "mpim"
    participants: str  # JSON string of participant IDs
    last_ingested: Optional[datetime] = None
    message_count: int = 0


class ConversationRecord(SQLModel, table=True):
    """SQLModel for storing conversation chunks in database."""

    __tablename__ = "conversations"

    conversation_id: str = Field(primary_key=True)
    channel_id: str
    channel_name: Optional[str] = None
    channel_type: str
    start_time: datetime
    end_time: datetime
    message_count: int
    participants: str  # JSON string of participant IDs
    messages_content: str


class ThreadRecord(SQLModel, table=True):
    """SQLModel for storing thread data in database."""

    __tablename__ = "threads"

    thread_id: str = Field(primary_key=True)  # Combination of channel_id and thread_ts
    thread_ts: str
    channel_id: str
    channel_name: Optional[str] = None
    parent_message: str
    thread_messages: str
    message_count: int
    participants: str  # JSON string of participant IDs
    created_at: datetime
    last_reply_at: Optional[datetime] = None


class UserRecord(SQLModel, table=True):
    """SQLModel for caching user information."""

    __tablename__ = "users"

    user_id: str = Field(primary_key=True)
    real_name: Optional[str] = None
    display_name: Optional[str] = None
    name: str  # Username
    is_bot: bool = False
    last_updated: datetime


class SlackService:
    """Service for fetching Slack conversations with caching and chunking."""

    def __init__(self, context: ServerContext):
        self.context = context
        self.root = context.root
        self.auth = SlackAuthenticator()
        self.client = self.auth.get_client()

        # Test authentication immediately
        self._test_authentication()

        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)

        # Initialize chunker for conversation splitting
        self.chunker = RecursiveChunker(chunk_size=4000)

        # Warm up channel cache
        self._warmup_channel_cache()

        # Register page handlers
        self._register_handlers()
        logger.info("Slack service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register page handlers with the context."""
        self.context.register_handler("slack_conversation", self._get_conversation)
        self.context.register_handler("slack_thread", self._get_thread)

    def _get_conversation(self, conversation_id: str) -> Optional[SlackConversation]:
        """Get a specific conversation chunk by ID."""
        try:
            with Session(self.engine) as session:
                record = session.get(ConversationRecord, conversation_id)
                if record:
                    return self._convert_conversation_record_to_page(record)
        except Exception as e:
            logger.error(f"Error fetching conversation {conversation_id}: {e}")
        return None

    def _get_thread(self, thread_id: str) -> Optional[SlackThread]:
        """Get a specific thread by ID."""
        try:
            with Session(self.engine) as session:
                record = session.get(ThreadRecord, thread_id)
                if record:
                    return self._convert_thread_record_to_page(record)
        except Exception as e:
            logger.error(f"Error fetching thread {thread_id}: {e}")
        return None

    def _get_channel_type_and_name(self, channel_id: str) -> Tuple[Optional[str], str]:
        """Get channel type and name from channel ID."""
        try:
            response = self.client.conversations_info(channel=channel_id)
            if response["ok"]:
                channel = response["channel"]
                if channel.get("is_channel"):
                    return "public_channel", f"#{channel['name']}"
                elif channel.get("is_group"):
                    return "private_channel", f"#{channel['name']}"
                elif channel.get("is_im"):
                    # Get user info for DM
                    user_response = self.client.users_info(user=channel["user"])
                    if user_response["ok"]:
                        user_name = (
                            user_response["user"].get("display_name")
                            or user_response["user"]["name"]
                        )
                        return "im", f"DM with {user_name}"
                elif channel.get("is_mpim"):
                    return "mpim", channel.get("name", "Group DM")
        except SlackApiError as e:
            logger.warning(f"Failed to get channel info for {channel_id}: {e}")

        return None, "unknown"

    def _test_authentication(self) -> None:
        """Test Slack authentication and print detailed info."""
        try:
            logger.info("Testing Slack authentication...")

            # Print token info
            token_info = self.auth.token
            if token_info:
                token = token_info.get("access_token", "")
                logger.info(f"Token type: {token_info.get('token_type', 'unknown')}")
                logger.info(f"Scopes: {token_info.get('scope', 'unknown')}")
                logger.info(f"User ID: {token_info.get('user_id', 'unknown')}")
                logger.info(f"Team ID: {token_info.get('team_id', 'unknown')}")
                logger.info(f"Token starts with: {token[:20]}...")

                # Check if this is an Enterprise Grid rotated token
                if token.startswith("xoxe."):
                    logger.warning("⚠️  Detected Enterprise Grid rotated token (xoxe.)")
                    logger.warning("This token may need special handling or refresh.")

                    # Try to refresh the token
                    logger.info("Attempting to refresh Enterprise Grid token...")
                    self.auth.refresh_token()

                    # Update client with potentially new token
                    new_token_info = self.auth.token
                    if new_token_info and new_token_info.get("access_token") != token:
                        self.client = self.auth.get_client()
                        logger.info("✅ Token refreshed successfully")
                    else:
                        logger.warning("Token refresh did not change the token")

            else:
                logger.error("No token information available!")
                return

            # Test auth
            response = self.client.auth_test()
            if response["ok"]:
                logger.info("✅ Slack auth test successful!")
                logger.info(f"Authenticated as: {response.get('user', 'unknown')}")
                logger.info(f"Team: {response.get('team', 'unknown')}")
                logger.info(f"URL: {response.get('url', 'unknown')}")
                logger.info(f"User ID: {response.get('user_id', 'unknown')}")
                logger.info(
                    f"Is Enterprise Grid: {response.get('is_enterprise_install', False)}"
                )
            else:
                logger.error(
                    f"❌ Slack auth test failed: {response.get('error', 'unknown')}"
                )
                logger.error(f"Full response: {response}")

                # If auth failed, try to refresh token and retry
                if response.get("error") == "invalid_auth":
                    logger.info("Attempting to refresh token due to invalid_auth...")
                    self.auth.refresh_token()
                    self.client = self.auth.get_client()

                    # Retry auth test
                    retry_response = self.client.auth_test()
                    if retry_response["ok"]:
                        logger.info("✅ Auth successful after token refresh!")
                    else:
                        logger.error(
                            f"❌ Auth still failed after refresh: {retry_response}"
                        )

        except SlackApiError as e:
            logger.error(f"❌ Slack API error during auth test: {e}")
            logger.error(f"Response: {e.response}")

            # Try token refresh on auth errors
            if "invalid_auth" in str(e):
                logger.info("Attempting token refresh due to auth error...")
                try:
                    self.auth.refresh_token()
                    self.client = self.auth.get_client()
                    logger.info("Token refreshed, you may need to restart the app")
                except Exception as refresh_error:
                    logger.error(f"Token refresh failed: {refresh_error}")

        except Exception as e:
            logger.error(f"❌ Unexpected error during auth test: {e}")
            import traceback

            logger.error(traceback.format_exc())

    def _warmup_channel_cache(self) -> None:
        """Discover and cache accessible channels/conversations."""
        logger.info("Warming up channel cache...")

        conversation_types = [
            ("public_channel", {"types": "public_channel"}),
            ("private_channel", {"types": "private_channel"}),
            ("mpim", {"types": "mpim"}),
            ("im", {"types": "im"}),
        ]

        with Session(self.engine) as session:
            for conv_type, params in conversation_types:
                try:
                    response = self.client.conversations_list(**params)
                    if response["ok"]:
                        channels = response["channels"]
                        logger.info(f"Found {len(channels)} {conv_type}s")

                        for channel in channels:
                            # Create or update channel summary
                            existing = session.get(ChannelSummaryRecord, channel["id"])
                            if not existing:
                                summary = ChannelSummaryRecord(
                                    id=channel["id"],
                                    name=channel.get("name", channel["id"]),
                                    type=conv_type,
                                    participants="[]",  # Will be populated when needed
                                    message_count=0,
                                )
                                session.add(summary)

                except SlackApiError as e:
                    logger.error(f"Failed to fetch {conv_type}s: {e}")
                    logger.error(f"Response: {e.response}")
                    if e.response.get("error") == "invalid_auth":
                        logger.error(
                            "❌ Authentication failed! Check your token and scopes."
                        )
                        logger.error("Required scopes for conversations.list:")
                        logger.error("- channels:read (for public channels)")
                        logger.error("- groups:read (for private channels)")
                        logger.error("- im:read (for DMs)")
                        logger.error("- mpim:read (for group DMs)")
                    continue

            session.commit()

        logger.info("Channel cache warmed up successfully")

    def get_client(self) -> WebClient:
        """Get the authenticated Slack client."""
        return self.client

    def search_channels_by_name(self, channel_name: str) -> List[str]:
        """Search for channel IDs by name (supports partial matching)."""
        clean_name = channel_name.lstrip("#").lower()
        matching_channels = []

        with Session(self.engine) as session:
            stmt = select(ChannelSummaryRecord).where(
                ChannelSummaryRecord.name.contains(clean_name)
            )
            channels = session.exec(stmt).all()

            for channel in channels:
                matching_channels.append(channel.id)

        return matching_channels

    def search_dms_with_person(self, person_name: str) -> List[str]:
        """Search for DM channel IDs with a specific person."""
        person_lower = person_name.lower()
        matching_dms = []

        with Session(self.engine) as session:
            stmt = select(ChannelSummaryRecord).where(ChannelSummaryRecord.type == "im")
            dms = session.exec(stmt).all()

            for dm in dms:
                # Check if person name is in the DM name
                if person_lower in dm.name.lower():
                    matching_dms.append(dm.id)

        return matching_dms

    def search_conversations_by_content(
        self, query: str, page_token: Optional[str] = None, page_size: int = 10
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search conversations by content across all channels."""
        try:
            # Get all channels that might have relevant content
            with Session(self.engine) as session:
                stmt = select(ChannelSummaryRecord)
                channels = session.exec(stmt).all()

            conversation_uris = []

            # For each channel, check if we need to ingest and search
            for channel in channels:
                # Check if channel needs ingestion (simplified - always ingest for now)
                channel_conversations = self._search_channel_content(channel.id, query)
                conversation_uris.extend(channel_conversations)

                # Limit results
                if len(conversation_uris) >= page_size:
                    break

            # Simple pagination (no real page tokens for now)
            start_idx = 0
            if page_token:
                try:
                    start_idx = int(page_token)
                except ValueError:
                    start_idx = 0

            end_idx = start_idx + page_size
            page_results = conversation_uris[start_idx:end_idx]
            next_token = str(end_idx) if end_idx < len(conversation_uris) else None

            return page_results, next_token

        except Exception as e:
            logger.error(f"Error searching conversations by content: {e}")
            return [], None

    def search_conversations_by_channel(
        self, channel_name: str, page_token: Optional[str] = None, page_size: int = 10
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search conversations in a specific channel."""
        try:
            # Find channel ID by name
            channel_ids = self.search_channels_by_name(channel_name)
            if not channel_ids:
                logger.warning(f"No channels found matching '{channel_name}'")
                return [], None

            # Use first matching channel
            channel_id = channel_ids[0]

            # Get conversations from this channel
            conversation_uris = self._get_channel_conversations(channel_id)

            # Simple pagination
            start_idx = 0
            if page_token:
                try:
                    start_idx = int(page_token)
                except ValueError:
                    start_idx = 0

            end_idx = start_idx + page_size
            page_results = conversation_uris[start_idx:end_idx]
            next_token = str(end_idx) if end_idx < len(conversation_uris) else None

            return page_results, next_token

        except Exception as e:
            logger.error(f"Error searching conversations by channel: {e}")
            return [], None

    def search_conversations_with_person(
        self, person_name: str, page_token: Optional[str] = None, page_size: int = 10
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search conversations involving a specific person."""
        try:
            # Find DMs with this person
            dm_channels = self.search_dms_with_person(person_name)

            conversation_uris = []

            # Get conversations from DM channels
            for channel_id in dm_channels:
                channel_conversations = self._get_channel_conversations(channel_id)
                conversation_uris.extend(channel_conversations)

            # Simple pagination
            start_idx = 0
            if page_token:
                try:
                    start_idx = int(page_token)
                except ValueError:
                    start_idx = 0

            end_idx = start_idx + page_size
            page_results = conversation_uris[start_idx:end_idx]
            next_token = str(end_idx) if end_idx < len(conversation_uris) else None

            return page_results, next_token

        except Exception as e:
            logger.error(f"Error searching conversations with person: {e}")
            return [], None

    def _search_channel_content(self, channel_id: str, query: str) -> List[PageURI]:
        """Search for content within a specific channel (with on-demand ingestion)."""
        # Check if channel has been ingested recently
        needs_ingestion = self._channel_needs_ingestion(channel_id)

        if needs_ingestion:
            self._ingest_channel(channel_id)

        # Search existing conversation chunks for content
        conversation_uris = []
        with Session(self.engine) as session:
            stmt = select(ConversationRecord).where(
                ConversationRecord.channel_id == channel_id
            )
            conversations = session.exec(stmt).all()

            query_lower = query.lower()
            for conv in conversations:
                if query_lower in conv.messages_content.lower():
                    uri = PageURI(
                        root=self.root,
                        type="slack_conversation",
                        id=conv.conversation_id,
                    )
                    conversation_uris.append(uri)

        return conversation_uris

    def _get_channel_conversations(self, channel_id: str) -> List[PageURI]:
        """Get all conversations from a channel (with on-demand ingestion)."""
        # Check if channel has been ingested recently
        needs_ingestion = self._channel_needs_ingestion(channel_id)

        if needs_ingestion:
            self._ingest_channel(channel_id)

        # Get all conversation chunks from this channel
        conversation_uris = []
        with Session(self.engine) as session:
            stmt = (
                select(ConversationRecord)
                .where(ConversationRecord.channel_id == channel_id)
                .order_by(ConversationRecord.start_time.desc())
            )
            conversations = session.exec(stmt).all()

            for conv in conversations:
                uri = PageURI(
                    root=self.root, type="slack_conversation", id=conv.conversation_id
                )
                conversation_uris.append(uri)

        return conversation_uris

    def _channel_needs_ingestion(self, channel_id: str) -> bool:
        """Check if a channel needs ingestion (simplified logic for now)."""
        with Session(self.engine) as session:
            channel = session.get(ChannelSummaryRecord, channel_id)
            if not channel:
                return True

            # Check if never ingested or ingested more than 1 hour ago
            if not channel.last_ingested:
                return True

            hours_since_ingestion = (
                datetime.now() - channel.last_ingested
            ).total_seconds() / 3600
            return hours_since_ingestion > 1

    def _ingest_channel(self, channel_id: str) -> None:
        """Ingest messages from a channel and create conversation chunks."""
        logger.info(f"Ingesting channel: {channel_id}")

        try:
            # Fetch recent messages from the channel
            response = self.client.conversations_history(
                channel=channel_id, limit=100  # Get last 100 messages
            )

            if not response["ok"]:
                logger.error(
                    f"Failed to fetch messages from {channel_id}: {response.get('error')}"
                )
                return

            messages = response.get("messages", [])
            if not messages:
                logger.info(f"No messages found in channel {channel_id}")
                return

            # Get channel info for display name
            channel_type, channel_name = self._get_channel_type_and_name(channel_id)

            # Group messages by time proximity (1 hour windows)
            conversation_chunks = self._chunk_messages_by_time(
                messages, channel_id, channel_name, channel_type
            )

            # Save conversation chunks to database
            with Session(self.engine) as session:
                for chunk in conversation_chunks:
                    session.merge(chunk)  # Use merge to handle duplicates

                # Update channel ingestion status
                channel_record = session.get(ChannelSummaryRecord, channel_id)
                if channel_record:
                    channel_record.last_ingested = datetime.now()
                    channel_record.message_count = len(messages)
                    session.add(channel_record)

                session.commit()

            logger.info(
                f"Successfully ingested {len(conversation_chunks)} conversation chunks from {channel_id}"
            )

        except SlackApiError as e:
            logger.error(f"Slack API error ingesting channel {channel_id}: {e}")
        except Exception as e:
            logger.error(f"Error ingesting channel {channel_id}: {e}")

    def _chunk_messages_by_time(
        self,
        messages: List[Dict],
        channel_id: str,
        channel_name: str,
        channel_type: str,
    ) -> List[ConversationRecord]:
        """Group messages into conversation chunks by temporal proximity."""
        if not messages:
            return []

        # Sort messages by timestamp (oldest first)
        sorted_messages = sorted(messages, key=lambda m: float(m.get("ts", "0")))

        chunks = []
        current_chunk_messages = []
        chunk_start_time = None
        chunk_index = 0

        for message in sorted_messages:
            message_time = datetime.fromtimestamp(
                float(message.get("ts", "0")), tz=timezone.utc
            )

            # Start new chunk if this is the first message or more than 1 hour gap
            if (
                not current_chunk_messages
                or (message_time - chunk_start_time).total_seconds() > 3600
            ):

                # Save previous chunk if exists
                if current_chunk_messages:
                    chunk = self._create_conversation_chunk(
                        current_chunk_messages,
                        channel_id,
                        channel_name,
                        channel_type,
                        chunk_index,
                    )
                    chunks.append(chunk)
                    chunk_index += 1

                # Start new chunk
                current_chunk_messages = [message]
                chunk_start_time = message_time
            else:
                # Add to current chunk
                current_chunk_messages.append(message)

        # Save final chunk
        if current_chunk_messages:
            chunk = self._create_conversation_chunk(
                current_chunk_messages,
                channel_id,
                channel_name,
                channel_type,
                chunk_index,
            )
            chunks.append(chunk)

        return chunks

    def _create_conversation_chunk(
        self,
        messages: List[Dict],
        channel_id: str,
        channel_name: str,
        channel_type: str,
        chunk_index: int,
    ) -> ConversationRecord:
        """Create a SlackConversation from a list of messages."""
        if not messages:
            raise ValueError("Cannot create conversation chunk from empty messages")

        # Sort messages by timestamp
        sorted_messages = sorted(messages, key=lambda m: float(m.get("ts", "0")))

        # Extract time range
        start_time = datetime.fromtimestamp(
            float(sorted_messages[0].get("ts", "0")), tz=timezone.utc
        )
        end_time = datetime.fromtimestamp(
            float(sorted_messages[-1].get("ts", "0")), tz=timezone.utc
        )

        # Extract participants (with display names)
        participant_ids = list(
            set(msg.get("user", "unknown") for msg in messages if msg.get("user"))
        )
        participants = [
            self._get_user_display_name(user_id) for user_id in participant_ids
        ]

        # Format messages content
        messages_content = self._format_messages_for_content(sorted_messages)

        # Create conversation ID
        conversation_id = f"{channel_id}({chunk_index})"

        return ConversationRecord(
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_name=channel_name,
            channel_type=channel_type,
            start_time=start_time,
            end_time=end_time,
            message_count=len(messages),
            participants=str(participants),  # Convert to JSON string
            messages_content=messages_content,
        )

    def _format_messages_for_content(self, messages: List[Dict]) -> str:
        """Format messages into readable content string."""
        formatted_lines = []

        for message in messages:
            user_id = message.get("user", "unknown")
            user_name = self._get_user_display_name(user_id)
            text = message.get("text", "")
            timestamp = message.get("ts", "0")

            # Convert timestamp to readable format
            msg_time = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            time_str = msg_time.strftime("%Y-%m-%d %H:%M:%S UTC")

            # Format: [timestamp] user_name: message
            formatted_lines.append(f"[{time_str}] {user_name}: {text}")

        return "\n".join(formatted_lines)

    def _get_user_display_name(self, user_id: str) -> str:
        """Get display name for a user ID, with caching."""
        if user_id == "unknown" or not user_id:
            return "Unknown User"

        # Check cache first
        with Session(self.engine) as session:
            user_record = session.get(UserRecord, user_id)

            # If cached and recent (within 24 hours), use cached name
            if (
                user_record
                and (datetime.now() - user_record.last_updated).total_seconds() < 86400
            ):
                return self._format_user_display_name(user_record)

            # Fetch from Slack API
            try:
                response = self.client.users_info(user=user_id)
                if response["ok"]:
                    user_info = response["user"]

                    # Create or update user record
                    user_record = UserRecord(
                        user_id=user_id,
                        real_name=user_info.get("real_name"),
                        display_name=user_info.get("profile", {}).get("display_name"),
                        name=user_info.get("name", user_id),
                        is_bot=user_info.get("is_bot", False),
                        last_updated=datetime.now(),
                    )

                    session.merge(user_record)
                    session.commit()

                    return self._format_user_display_name(user_record)

            except Exception as e:
                logger.warning(f"Failed to fetch user info for {user_id}: {e}")

            # Fallback to user ID if all else fails
            return user_id

    def _format_user_display_name(self, user_record: UserRecord) -> str:
        """Format a user's display name from their record."""
        # Prefer display_name (what users see in Slack), then real_name, then username
        if user_record.display_name and user_record.display_name.strip():
            return user_record.display_name
        elif user_record.real_name and user_record.real_name.strip():
            return user_record.real_name
        else:
            return user_record.name

    def _convert_conversation_record_to_page(
        self, record: ConversationRecord
    ) -> SlackConversation:
        """Convert a ConversationRecord to a SlackConversation page."""
        uri = PageURI(
            root=self.root, type="slack_conversation", id=record.conversation_id
        )

        # Parse participants from JSON string
        try:
            participants = (
                json.loads(record.participants) if record.participants else []
            )
        except json.JSONDecodeError:
            participants = []

        return SlackConversation(
            uri=uri,
            conversation_id=record.conversation_id,
            channel_id=record.channel_id,
            channel_name=record.channel_name,
            channel_type=record.channel_type,
            start_time=record.start_time,
            end_time=record.end_time,
            message_count=record.message_count,
            participants=participants,
            messages_content=record.messages_content,
        )

    def _convert_thread_record_to_page(self, record: ThreadRecord) -> SlackThread:
        """Convert a ThreadRecord to a SlackThread page."""
        uri = PageURI(root=self.root, type="slack_thread", id=record.thread_id)

        # Parse participants from JSON string
        try:
            participants = (
                json.loads(record.participants) if record.participants else []
            )
        except json.JSONDecodeError:
            participants = []

        return SlackThread(
            uri=uri,
            thread_ts=record.thread_ts,
            channel_id=record.channel_id,
            channel_name=record.channel_name,
            parent_message=record.parent_message,
            thread_messages=record.thread_messages,
            message_count=record.message_count,
            participants=participants,
            created_at=record.created_at,
            last_reply_at=record.last_reply_at,
            permalink=f"https://app.slack.com/client/{record.channel_id}/{record.thread_ts}",
        )
