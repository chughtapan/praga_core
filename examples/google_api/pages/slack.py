from datetime import datetime
from typing import List, Optional

from pydantic import Field

from praga_core.types import Page, PageURI


class SlackThread(Page):
    """
    A Slack thread containing all messages within a specific thread.
    Maps to messages within a thread identified by thread_ts.
    """

    type: str = Field(default="slack_thread", description="Page type identifier")
    thread_ts: str = Field(description="Thread timestamp identifier")
    channel_id: str = Field(description="Channel ID where thread exists")
    channel_name: Optional[str] = Field(description="Channel name for display")
    parent_message: str = Field(description="Parent message that started the thread")
    thread_messages: str = Field(description="All messages in the thread formatted")
    message_count: int = Field(description="Total number of messages in thread")
    participants: List[str] = Field(description="List of user IDs who participated")
    created_at: datetime = Field(description="When the thread was created")
    last_reply_at: Optional[datetime] = Field(description="When last reply was posted")
    permalink: str = Field(description="Slack permalink to thread", exclude=True)

    def get_content(self) -> str:
        """Return the full thread messages for indexing."""
        return self.thread_messages

    def get_title(self) -> str:
        """Generate a title for the thread."""
        # Use first few words of parent message as title
        words = self.parent_message.split()[:8]
        title = " ".join(words)
        if len(self.parent_message.split()) > 8:
            title += "..."
        return f"Thread: {title}"


class SlackConversation(Page):
    """
    A chunk of Slack conversation messages grouped by temporal proximity.
    Contains messages from a channel/DM within a specific time window.
    """

    type: str = Field(default="slack_conversation", description="Page type identifier")
    conversation_id: str = Field(
        description="Unique identifier for this conversation chunk"
    )
    channel_id: str = Field(description="Channel ID where conversation occurred")
    channel_name: Optional[str] = Field(description="Channel name for display")
    channel_type: str = Field(description="Type: channel, group, im, mpim")
    start_time: datetime = Field(description="Start time of conversation chunk")
    end_time: datetime = Field(description="End time of conversation chunk")
    message_count: int = Field(description="Number of messages in this chunk")
    participants: List[str] = Field(description="List of user IDs who participated")
    messages_content: str = Field(description="Combined content of all messages")
    next_conversation_uri: Optional[PageURI] = Field(
        description="URI to next conversation chunk", default=None
    )
    prev_conversation_uri: Optional[PageURI] = Field(
        description="URI to previous conversation chunk", default=None
    )
    related_threads: List[PageURI] = Field(
        description="URIs to related thread pages", default_factory=list
    )

    def get_content(self) -> str:
        """Return the combined messages content for indexing."""
        return self.messages_content

    def get_title(self) -> str:
        """Generate a title for the conversation chunk."""
        # Use first sentence or few words from messages
        first_sentence = self.messages_content.split(".")[0]
        if len(first_sentence) > 100:
            words = first_sentence.split()[:15]
            first_sentence = " ".join(words) + "..."
        return f"Conversation: {first_sentence}"
