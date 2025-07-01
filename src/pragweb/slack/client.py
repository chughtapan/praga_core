"""High-level Slack API client that abstracts API specifics."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.web.slack_response import SlackResponse

from .auth import SlackAuthManager

logger = logging.getLogger(__name__)


class SlackAPIClient:
    """High-level client for Slack API interactions."""

    def __init__(self, auth_manager: Optional[SlackAuthManager] = None):
        self.auth_manager = auth_manager or SlackAuthManager()
        self._client: Optional[WebClient] = None

    @property
    def client(self) -> WebClient:
        """Get the authenticated Slack client."""
        if self._client is None:
            self._client = self.auth_manager.get_client()
        return self._client

    # Channel Methods
    def get_channel_info(self, channel_id: str) -> Dict[str, Any]:
        """Get channel information by ID."""
        response: SlackResponse = self.client.conversations_info(channel=channel_id)
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            channel_data = response_data.get("channel")
            if not isinstance(channel_data, dict):
                raise ValueError("Invalid channel data received")
            return cast(Dict[str, Any], channel_data)
        else:
            # Handle SlackApiError constructor properly
            error_msg = f"Failed to get channel info: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    def list_channels(
        self, types: str = "public_channel,private_channel,mpim,im", limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """List only channels the authenticated user is a member of."""
        channels: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            response: SlackResponse = self.client.conversations_list(
                types=types,
                limit=min(limit, 1000),  # API max is 1000
                cursor=cursor,
                exclude_archived=True,  # Don't include archived channels
            )
            response_data = cast(Dict[str, Any], response.data)

            if response_data.get("ok"):
                channels_data = response_data.get("channels", [])
                if isinstance(channels_data, list):
                    # Filter to only channels the user is a member of
                    user_channels = []
                    for channel in cast(List[Dict[str, Any]], channels_data):
                        # For public channels, check is_member field
                        if channel.get("is_channel"):  # Public channel
                            if channel.get("is_member", False):
                                user_channels.append(channel)
                        else:
                            # Private channels, DMs, and group DMs should already be filtered by the API
                            # to only include channels the user is a member of
                            user_channels.append(channel)

                    channels.extend(user_channels)

                # Get next cursor
                metadata = response_data.get("response_metadata", {})
                if isinstance(metadata, dict):
                    cursor = metadata.get("next_cursor")
                else:
                    cursor = None

                if not cursor or len(channels) >= limit:
                    break
            else:
                error_msg = f"Failed to list channels: {response_data.get('error')}"
                raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

        return channels[:limit]

    def get_channel_members(self, channel_id: str) -> List[str]:
        """Get list of member IDs for a channel."""
        members: List[str] = []
        cursor: Optional[str] = None

        while True:
            response: SlackResponse = self.client.conversations_members(
                channel=channel_id, cursor=cursor
            )
            response_data = cast(Dict[str, Any], response.data)

            if response_data.get("ok"):
                members_data = response_data.get("members", [])
                if isinstance(members_data, list):
                    members.extend(cast(List[str], members_data))

                # Get next cursor
                metadata = response_data.get("response_metadata", {})
                if isinstance(metadata, dict):
                    cursor = metadata.get("next_cursor")
                else:
                    cursor = None

                if not cursor:
                    break
            else:
                error_msg = (
                    f"Failed to get channel members: {response_data.get('error')}"
                )
                raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]
        return members

    # Message Methods
    def get_conversation_history(
        self,
        channel_id: str,
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        inclusive: bool = False,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Get conversation history with pagination."""
        # Call conversations_history with explicit parameters instead of **params
        response: SlackResponse = self.client.conversations_history(
            channel=channel_id,
            limit=min(limit, 1000),  # API max is 1000
            oldest=oldest,
            latest=latest,
            cursor=cursor,
            inclusive=inclusive,
        )
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            messages_data = response_data.get("messages", [])
            messages = (
                cast(List[Dict[str, Any]], messages_data)
                if isinstance(messages_data, list)
                else []
            )

            # Get next cursor
            metadata = response_data.get("response_metadata", {})
            next_cursor = None
            if isinstance(metadata, dict):
                next_cursor = metadata.get("next_cursor")

            return messages, next_cursor
        else:
            error_msg = (
                f"Failed to get conversation history: {response_data.get('error')}"
            )
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    def get_thread_replies(
        self, channel_id: str, thread_ts: str
    ) -> List[Dict[str, Any]]:
        """Get all replies in a thread."""
        response: SlackResponse = self.client.conversations_replies(
            channel=channel_id, ts=thread_ts
        )
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            messages_data = response_data.get("messages", [])
            return (
                cast(List[Dict[str, Any]], messages_data)
                if isinstance(messages_data, list)
                else []
            )
        else:
            error_msg = f"Failed to get thread replies: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    # Search Methods
    def search_messages(
        self,
        query: str,
        sort: str = "timestamp",
        sort_dir: str = "desc",
        count: int = 20,
        page: int = 1,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Search messages across all channels."""
        response: SlackResponse = self.client.search_messages(
            query=query, sort=sort, sort_dir=sort_dir, count=count, page=page
        )
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            messages_section = response_data.get("messages", {})
            if isinstance(messages_section, dict):
                messages_data = messages_section.get("matches", [])
                pagination_data = messages_section.get("pagination", {})
                messages = (
                    cast(List[Dict[str, Any]], messages_data)
                    if isinstance(messages_data, list)
                    else []
                )
                pagination = (
                    cast(Dict[str, Any], pagination_data)
                    if isinstance(pagination_data, dict)
                    else {}
                )
                return messages, pagination
            else:
                return [], {}
        else:
            error_msg = f"Failed to search messages: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    def search_messages_in_channel(
        self,
        channel_id: str,
        query: str = "",
        oldest: Optional[str] = None,
        latest: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search messages within a specific channel."""
        # Build search query
        search_parts = []
        if query:
            search_parts.append(query)
        search_parts.append(f"in:<#{channel_id}>")

        if oldest:
            # Convert timestamp to readable date for search
            oldest_dt = datetime.fromtimestamp(float(oldest))
            search_parts.append(f"after:{oldest_dt.strftime('%Y-%m-%d')}")
        if latest:
            latest_dt = datetime.fromtimestamp(float(latest))
            search_parts.append(f"before:{latest_dt.strftime('%Y-%m-%d')}")

        search_query = " ".join(search_parts)

        messages, _ = self.search_messages(search_query, count=limit)
        return messages

    # User Methods
    def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Get user information by ID."""
        response: SlackResponse = self.client.users_info(user=user_id)
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            user_data = cast(Dict[str, Any], response_data.get("user"))

            if not isinstance(user_data, dict):
                raise ValueError("Invalid user data received")
            return user_data
        else:
            error_msg = f"Failed to get user info: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    def list_users(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """List all users in the workspace."""
        users: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        while True:
            response: SlackResponse = self.client.users_list(
                limit=min(limit, 1000), cursor=cursor  # API max is 1000
            )
            response_data = cast(Dict[str, Any], response.data)

            if response_data.get("ok"):
                members_data = response_data.get("members", [])
                if isinstance(members_data, list):
                    users.extend(cast(List[Dict[str, Any]], members_data))

                # Get next cursor
                metadata = response_data.get("response_metadata", {})
                if isinstance(metadata, dict):
                    cursor = metadata.get("next_cursor")
                else:
                    cursor = None

                if not cursor or len(users) >= limit:
                    break
            else:
                error_msg = f"Failed to list users: {response_data.get('error')}"
                raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

        return users[:limit]

    def lookup_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Look up user by email address."""
        response: SlackResponse = self.client.users_lookupByEmail(email=email)
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            user_data = response_data.get("user")
            if isinstance(user_data, dict):
                return cast(Dict[str, Any], user_data)
            return None
        else:
            # Email not found is not an error condition
            if response_data.get("error") == "users_not_found":
                return None
            error_msg = f"Failed to lookup user by email: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    # Utility Methods
    def test_auth(self) -> Dict[str, Any]:
        """Test authentication and return auth info."""
        response: SlackResponse = self.client.auth_test()
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            return response_data
        else:
            error_msg = f"Auth test failed: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]

    def get_team_info(self) -> Dict[str, Any]:
        """Get team/workspace information."""
        response: SlackResponse = self.client.team_info()
        response_data = cast(Dict[str, Any], response.data)

        if response_data.get("ok"):
            team_data = response_data.get("team")
            if not isinstance(team_data, dict):
                raise ValueError("Invalid team data received")
            return cast(Dict[str, Any], team_data)
        else:
            error_msg = f"Failed to get team info: {response_data.get('error')}"
            raise SlackApiError(error_msg, response)  # type: ignore[no-untyped-call]
