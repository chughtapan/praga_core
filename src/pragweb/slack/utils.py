"""Slack utility classes for parsing and formatting data."""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class SlackParser:
    """Parser for Slack data that handles message formatting, ID encoding, and content extraction."""

    @staticmethod
    def encode_message_id(channel_id: str, message_ts: str) -> str:
        """Encode channel ID and message timestamp into a URI-safe message ID.

        Args:
            channel_id: Slack channel ID
            message_ts: Message timestamp

        Returns:
            Encoded message ID safe for PageURI
        """
        # Use underscore as separator since colons aren't allowed in PageURI IDs
        return f"{channel_id}_{message_ts}"

    @staticmethod
    def decode_message_id(message_id: str) -> tuple[str, str]:
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

    @staticmethod
    def encode_thread_id(channel_id: str, thread_ts: str) -> str:
        """Encode channel ID and thread timestamp into a URI-safe thread ID.

        Args:
            channel_id: Slack channel ID
            thread_ts: Thread timestamp

        Returns:
            Encoded thread ID safe for PageURI
        """
        # Use underscore as separator since colons aren't allowed in PageURI IDs
        return f"{channel_id}_{thread_ts}"

    @staticmethod
    def decode_thread_id(thread_id: str) -> tuple[str, str]:
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

    @staticmethod
    def determine_channel_type(channel_info: Dict[str, Any]) -> str:
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

    @staticmethod
    def get_user_display_name(user_info: Dict[str, Any]) -> str:
        """Get user display name for UI."""
        # Prefer display name, then real name, then username
        display_name = user_info.get("profile", {}).get("display_name")
        if display_name:
            return str(display_name)

        real_name = user_info.get("real_name")
        if real_name:
            return str(real_name)

        name = user_info.get("name", user_info.get("id", "unknown"))
        return str(name)

    @staticmethod
    def format_messages_for_content(
        messages: List[Dict[str, Any]], get_user_display_name_fn: Callable[[str], str]
    ) -> str:
        """Format messages into readable content.

        Args:
            messages: List of Slack message objects
            get_user_display_name_fn: Function to get display name for user ID
        """
        formatted_messages = []

        for msg in messages:
            user_id = msg.get("user", "unknown")
            user_name = get_user_display_name_fn(user_id)
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

    @staticmethod
    def validate_person_identifier(person: str) -> str:
        """Validate and format person identifier for Slack search.

        Args:
            person: Person identifier (should start with @ or be a user ID)

        Returns:
            Formatted person identifier for search

        Raises:
            ValueError: If person identifier format is invalid
        """
        if not person or not person.strip():
            raise ValueError("Person identifier cannot be empty")

        person = person.strip()

        # Handle @username format
        if person.startswith("@"):
            if len(person) == 1:  # Just "@"
                raise ValueError("Username cannot be empty after @")
            username = person[1:]
            # Basic validation: username should contain alphanumeric chars, dots, dashes, underscores
            if not username or not all(c.isalnum() or c in "._-" for c in username):
                raise ValueError(f"Invalid username format: {person}")
            return person

        # Handle Slack user ID format (U + 10 alphanumeric chars = 11 total)
        if person.startswith("U") and len(person) == 11 and person[1:].isalnum():
            return f"<@{person}>"

        # Reject everything else
        raise ValueError(
            f"Person identifier '{person}' is invalid. "
            f"Use @username (e.g., '@john.doe') or user ID (e.g., 'U1234567890') format."
        )
