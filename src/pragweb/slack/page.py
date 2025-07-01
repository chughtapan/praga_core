"""Slack page definitions."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field

from praga_core.types import Page, PageURI


class SlackMessageSummary(BaseModel):
    """A compressed representation of a Slack message for use in thread/conversation pages."""

    display_name: str = Field(
        description="Display name of the user who sent the message"
    )
    text: str = Field(description="Message text content")
    timestamp: datetime = Field(description="Message timestamp")


class SlackConversationPage(Page):
    """A chunk of Slack conversation messages grouped by temporal proximity."""

    conversation_id: str = Field(
        description="Unique identifier for this conversation chunk", exclude=True
    )
    channel_id: str = Field(
        description="Channel ID where conversation occurred", exclude=True
    )
    channel_name: Optional[str] = Field(description="Channel name for display")
    channel_type: str = Field(
        description="Type: public_channel, private_channel, im, mpim"
    )
    start_time: datetime = Field(description="Start time of conversation chunk")
    end_time: datetime = Field(description="End time of conversation chunk")
    message_count: int = Field(description="Number of messages in this chunk")
    participants: List[str] = Field(
        description="List of user display names who participated"
    )
    messages_content: str = Field(
        description="Combined formatted content of all messages"
    )
    permalink: str = Field(description="Slack permalink to conversation")

    @computed_field
    def next_conversation_uri(self) -> Optional[PageURI]:
        """URI to next conversation chunk if it exists."""
        # This will be populated by the service based on temporal ordering
        return None

    @computed_field
    def prev_conversation_uri(self) -> Optional[PageURI]:
        """URI to previous conversation chunk if it exists."""
        # This will be populated by the service based on temporal ordering
        return None

    @computed_field
    def related_threads(self) -> List[PageURI]:
        """URIs to related thread pages in this conversation."""
        # This will be populated by the service when threads are detected
        return []


class SlackThreadPage(Page):
    """A Slack thread containing all messages within a specific thread."""

    thread_ts: str = Field(description="Thread timestamp identifier", exclude=True)
    channel_id: str = Field(description="Channel ID where thread exists", exclude=True)
    channel_name: Optional[str] = Field(description="Channel name for display")
    parent_message: str = Field(description="Parent message that started the thread")
    messages: List[SlackMessageSummary] = Field(
        description="All messages in the thread"
    )
    message_count: int = Field(description="Total number of messages in thread")
    participants: List[str] = Field(
        description="List of user display names who participated"
    )
    created_at: datetime = Field(description="When the thread was created")
    last_reply_at: Optional[datetime] = Field(description="When last reply was posted")
    permalink: str = Field(description="Slack permalink to thread")

    @property
    def thread_messages(self) -> str:
        """Formatted string of all thread messages for content search."""
        formatted_messages = []
        for msg in self.messages:
            formatted_messages.append(f"{msg.display_name}: {msg.text}")
        return "\n".join(formatted_messages)


class SlackChannelPage(Page):
    """A Slack channel with metadata and recent activity summary."""

    channel_id: str = Field(description="Slack channel ID", exclude=True)
    name: str = Field(description="Channel name")
    channel_type: str = Field(
        description="Type: public_channel, private_channel, im, mpim"
    )
    topic: Optional[str] = Field(description="Channel topic")
    purpose: Optional[str] = Field(description="Channel purpose")
    member_count: int = Field(description="Number of members in channel")
    created: datetime = Field(description="When channel was created")
    is_archived: bool = Field(description="Whether channel is archived")
    last_activity: Optional[datetime] = Field(description="Last message timestamp")
    message_urls: List[str] = Field(
        default=[],
        description="List of recent message URLs in this channel",
        exclude=True,
    )
    permalink: str = Field(description="Slack permalink to channel")


class SlackUserPage(Page):
    """A Slack user profile with information."""

    user_id: str = Field(description="Slack user ID", exclude=True)
    name: str = Field(description="Username")
    real_name: Optional[str] = Field(description="Real name")
    display_name: Optional[str] = Field(description="Display name")
    email: Optional[str] = Field(description="Email address")
    title: Optional[str] = Field(description="Job title")
    is_bot: bool = Field(description="Whether this is a bot user")
    is_admin: bool = Field(description="Whether user is admin")
    status_text: Optional[str] = Field(description="Status message")
    status_emoji: Optional[str] = Field(description="Status emoji")
    last_updated: datetime = Field(description="When user info was last updated")


class SlackMessagePage(Page):
    """A single Slack message with context and links to related conversation."""

    message_ts: str = Field(description="Message timestamp identifier", exclude=True)
    channel_id: str = Field(description="Channel ID where message exists", exclude=True)
    channel_name: Optional[str] = Field(description="Channel name for display")
    channel_type: str = Field(
        description="Type: public_channel, private_channel, im, mpim"
    )
    user_id: str = Field(description="User ID who sent the message", exclude=True)
    display_name: str = Field(description="Display name of message sender")
    text_content: str = Field(description="Message text content")
    timestamp: datetime = Field(description="When message was sent")
    thread_ts: Optional[str] = Field(
        description="Thread timestamp if message is part of a thread"
    )
    next_message_uri: Optional[PageURI] = Field(
        default=None, description="URI to the next message in chronological order"
    )
    previous_message_uri: Optional[PageURI] = Field(
        default=None,
        description="URI to the previous message in reverse chronological order",
    )
    permalink: str = Field(description="Slack permalink to message")

    @computed_field
    def conversation_uri(self) -> Optional[PageURI]:
        """URI to the full conversation containing this message."""
        # This will be populated by the service
        return None

    @computed_field
    def thread_uri(self) -> Optional[PageURI]:
        """URI to thread page if this message is part of a thread."""
        if self.thread_ts:
            # Use underscore separator since colons aren't allowed in PageURI IDs
            thread_id = f"{self.channel_id}_{self.thread_ts}"
            return PageURI(
                root=self.uri.root, type="slack_thread", id=thread_id, version=1
            )
        return None


class SlackChannelListPage(Page):
    """A page containing all workspace channels for reference and search."""

    workspace_id: str = Field(description="Slack workspace/team ID", exclude=True)
    workspace_name: str = Field(description="Workspace name")
    total_channels: int = Field(description="Total number of channels")
    public_channels: int = Field(description="Number of public channels")
    private_channels: int = Field(description="Number of private channels")
    channels: List[Dict[str, Any]] = Field(description="List of channel metadata")
    last_updated: datetime = Field(description="When channel list was last updated")
