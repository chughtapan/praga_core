"""Tests for SlackAPIClient."""

from unittest.mock import Mock

import pytest
from slack_sdk.errors import SlackApiError
from slack_sdk.web.slack_response import SlackResponse

from pragweb.slack.client import SlackAPIClient


class TestSlackAPIClient:
    """Test suite for SlackAPIClient."""

    def setup_method(self):
        """Set up test environment."""
        # Create mock auth manager
        self.mock_auth_manager = Mock()
        self.mock_web_client = Mock()
        self.mock_auth_manager.get_client.return_value = self.mock_web_client

        self.client = SlackAPIClient(self.mock_auth_manager)

    def test_init(self):
        """Test SlackAPIClient initialization."""
        # Test with custom auth manager
        assert self.client.auth_manager is self.mock_auth_manager

        # Test with default auth manager
        default_client = SlackAPIClient()
        assert default_client.auth_manager is not None

    def test_client_property(self):
        """Test client property lazy loading."""
        # First access should call get_client
        client = self.client.client
        assert client is self.mock_web_client
        self.mock_auth_manager.get_client.assert_called_once()

        # Second access should use cached client
        client2 = self.client.client
        assert client2 is self.mock_web_client
        # Should still only be called once
        self.mock_auth_manager.get_client.assert_called_once()

    def test_get_channel_info_success(self):
        """Test successful channel info retrieval."""
        # Mock successful response
        mock_channel_data = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
            "topic": {"value": "General discussion"},
            "purpose": {"value": "Company-wide announcements"},
            "created": 1234567890,
            "is_archived": False,
        }

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "channel": mock_channel_data}
        self.mock_web_client.conversations_info.return_value = mock_response

        # Call method
        result = self.client.get_channel_info("C1234567890")

        # Verify API call
        self.mock_web_client.conversations_info.assert_called_once_with(
            channel="C1234567890"
        )

        # Verify result
        assert result == mock_channel_data

    def test_get_channel_info_error(self):
        """Test channel info retrieval with error."""
        # Mock error response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "channel_not_found"}
        self.mock_web_client.conversations_info.return_value = mock_response

        # Should raise SlackApiError
        with pytest.raises(SlackApiError):
            self.client.get_channel_info("C1234567890")

    def test_get_channel_info_invalid_data(self):
        """Test channel info retrieval with invalid channel data."""
        # Mock response with invalid channel data
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "channel": "invalid_data"}
        self.mock_web_client.conversations_info.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Invalid channel data received"):
            self.client.get_channel_info("C1234567890")

    def test_list_channels_success(self):
        """Test successful channel list retrieval."""
        # Mock channel data
        mock_channels = [
            {
                "id": "C1234567890",
                "name": "general",
                "is_channel": True,
                "is_member": True,
            },
            {
                "id": "C0987654321",
                "name": "random",
                "is_channel": True,
                "is_member": True,
            },
            {
                "id": "C1111111111",
                "name": "private-group",
                "is_group": True,
            },
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "channels": mock_channels,
            "response_metadata": {"next_cursor": ""},
        }
        self.mock_web_client.conversations_list.return_value = mock_response

        # Call method
        result = self.client.list_channels()

        # Verify API call
        self.mock_web_client.conversations_list.assert_called_once()

        # Verify result - should include all channels where user is member
        assert len(result) == 3  # All channels should be included

    def test_list_channels_with_pagination(self):
        """Test channel list with pagination."""
        # Mock first page
        mock_channels_page1 = [
            {
                "id": "C1234567890",
                "name": "general",
                "is_channel": True,
                "is_member": True,
            }
        ]
        mock_response_page1 = Mock(spec=SlackResponse)
        mock_response_page1.data = {
            "ok": True,
            "channels": mock_channels_page1,
            "response_metadata": {"next_cursor": "cursor123"},
        }

        # Mock second page
        mock_channels_page2 = [
            {
                "id": "C0987654321",
                "name": "random",
                "is_channel": True,
                "is_member": True,
            }
        ]
        mock_response_page2 = Mock(spec=SlackResponse)
        mock_response_page2.data = {
            "ok": True,
            "channels": mock_channels_page2,
            "response_metadata": {"next_cursor": ""},
        }

        # Set up side_effect for multiple calls
        self.mock_web_client.conversations_list.side_effect = [
            mock_response_page1,
            mock_response_page2,
        ]

        # Call method
        result = self.client.list_channels()

        # Verify multiple API calls
        assert self.mock_web_client.conversations_list.call_count == 2

        # Verify result combines both pages
        assert len(result) == 2

    def test_list_channels_member_filtering(self):
        """Test that list_channels filters to only channels where user is member."""
        # Mock channels with mixed membership
        mock_channels = [
            {
                "id": "C1234567890",
                "name": "general",
                "is_channel": True,
                "is_member": True,  # User is member
            },
            {
                "id": "C0987654321",
                "name": "other-team",
                "is_channel": True,
                "is_member": False,  # User is NOT member
            },
            {
                "id": "G1111111111",
                "name": "private-group",
                "is_group": True,
                # Private groups don't have is_member field
            },
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "channels": mock_channels,
            "response_metadata": {"next_cursor": ""},
        }
        self.mock_web_client.conversations_list.return_value = mock_response

        # Call method
        result = self.client.list_channels()

        # Should only include channels where user is member + private groups
        assert len(result) == 2
        channel_ids = [ch["id"] for ch in result]
        assert "C1234567890" in channel_ids  # Member of public channel
        assert "C0987654321" not in channel_ids  # Not member of public channel
        assert "G1111111111" in channel_ids  # Private group (always included)

    def test_get_channel_members_success(self):
        """Test successful channel members retrieval."""
        # Mock members data
        mock_members = ["U1234567890", "U0987654321", "U1111111111"]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "members": mock_members,
            "response_metadata": {"next_cursor": ""},
        }
        self.mock_web_client.conversations_members.return_value = mock_response

        # Call method
        result = self.client.get_channel_members("C1234567890")

        # Verify API call
        self.mock_web_client.conversations_members.assert_called_once_with(
            channel="C1234567890", cursor=None
        )

        # Verify result
        assert result == mock_members

    def test_get_conversation_history_success(self):
        """Test successful conversation history retrieval."""
        # Mock message data
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U1234567890",
                "text": "Hello everyone!",
            },
            {
                "ts": "1234567890.002",
                "user": "U0987654321",
                "text": "Hi there!",
            },
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "messages": mock_messages,
            "response_metadata": {"next_cursor": "cursor123"},
        }
        self.mock_web_client.conversations_history.return_value = mock_response

        # Call method
        messages, next_cursor = self.client.get_conversation_history(
            channel_id="C1234567890",
            oldest="1234567880.000",
            latest="1234567900.000",
            inclusive=True,
            limit=50,
        )

        # Verify API call
        self.mock_web_client.conversations_history.assert_called_once_with(
            channel="C1234567890",
            limit=50,
            oldest="1234567880.000",
            latest="1234567900.000",
            cursor=None,
            inclusive=True,
        )

        # Verify result
        assert messages == mock_messages
        assert next_cursor == "cursor123"

    def test_get_conversation_history_error(self):
        """Test conversation history retrieval with error."""
        # Mock error response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "channel_not_found"}
        self.mock_web_client.conversations_history.return_value = mock_response

        # Should raise SlackApiError
        with pytest.raises(SlackApiError):
            self.client.get_conversation_history("C1234567890")

    def test_get_thread_replies_success(self):
        """Test successful thread replies retrieval."""
        # Mock thread messages
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U1234567890",
                "text": "Parent message",
            },
            {
                "ts": "1234567890.002",
                "user": "U0987654321",
                "text": "Reply message",
            },
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "messages": mock_messages}
        self.mock_web_client.conversations_replies.return_value = mock_response

        # Call method
        result = self.client.get_thread_replies("C1234567890", "1234567890.001")

        # Verify API call
        self.mock_web_client.conversations_replies.assert_called_once_with(
            channel="C1234567890", ts="1234567890.001"
        )

        # Verify result
        assert result == mock_messages

    def test_search_messages_success(self):
        """Test successful message search."""
        # Mock search results
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U1234567890",
                "text": "Found message 1",
                "channel": {"id": "C1234567890"},
            },
            {
                "ts": "1234567890.002",
                "user": "U0987654321",
                "text": "Found message 2",
                "channel": {"id": "C0987654321"},
            },
        ]

        mock_pagination = {
            "page": 1,
            "page_count": 1,
            "total": 2,
        }

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "messages": {
                "matches": mock_messages,
                "pagination": mock_pagination,
            },
        }
        self.mock_web_client.search_messages.return_value = mock_response

        # Call method
        messages, pagination = self.client.search_messages(
            query="test query", sort="timestamp", sort_dir="desc", count=20, page=1
        )

        # Verify API call
        self.mock_web_client.search_messages.assert_called_once_with(
            query="test query", sort="timestamp", sort_dir="desc", count=20, page=1
        )

        # Verify result
        assert messages == mock_messages
        assert pagination == mock_pagination

    def test_search_messages_in_channel_success(self):
        """Test successful message search within channel."""
        # Mock search results
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U1234567890",
                "text": "Channel message 1",
                "channel": {"id": "C1234567890"},
            },
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "messages": {
                "matches": mock_messages,
                "pagination": {},
            },
        }
        self.mock_web_client.search_messages.return_value = mock_response

        # Call method
        result = self.client.search_messages_in_channel(
            channel_id="C1234567890",
            query="test content",
            oldest="1234567880.000",
            latest="1234567900.000",
            limit=50,
        )

        # Verify API call was made with channel filter
        self.mock_web_client.search_messages.assert_called_once()
        call_args = self.mock_web_client.search_messages.call_args
        query_arg = call_args[1]["query"]

        # Should include channel filter and content
        assert "test content" in query_arg
        assert "in:<#C1234567890>" in query_arg
        assert "after:" in query_arg  # Date filters
        assert "before:" in query_arg

        # Verify result
        assert result == mock_messages

    def test_get_user_info_success(self):
        """Test successful user info retrieval."""
        # Mock user data
        mock_user_data = {
            "id": "U1234567890",
            "name": "alice",
            "real_name": "Alice Smith",
            "is_bot": False,
            "is_admin": True,
            "profile": {
                "display_name": "Alice",
                "email": "alice@example.com",
                "title": "Software Engineer",
            },
        }

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "user": mock_user_data}
        self.mock_web_client.users_info.return_value = mock_response

        # Call method
        result = self.client.get_user_info("U1234567890")

        # Verify API call
        self.mock_web_client.users_info.assert_called_once_with(user="U1234567890")

        # Verify result
        assert result == mock_user_data

    def test_get_user_info_error(self):
        """Test user info retrieval with error."""
        # Mock error response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "user_not_found"}
        self.mock_web_client.users_info.return_value = mock_response

        # Should raise SlackApiError
        with pytest.raises(SlackApiError):
            self.client.get_user_info("U1234567890")

    def test_list_users_success(self):
        """Test successful user list retrieval."""
        # Mock user data
        mock_users = [
            {
                "id": "U1234567890",
                "name": "alice",
                "real_name": "Alice Smith",
            },
            {
                "id": "U0987654321",
                "name": "bob",
                "real_name": "Bob Jones",
            },
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "members": mock_users,
            "response_metadata": {"next_cursor": ""},
        }
        self.mock_web_client.users_list.return_value = mock_response

        # Call method
        result = self.client.list_users()

        # Verify API call
        self.mock_web_client.users_list.assert_called_once()

        # Verify result
        assert result == mock_users

    def test_lookup_user_by_email_success(self):
        """Test successful user lookup by email."""
        # Mock user data
        mock_user_data = {
            "id": "U1234567890",
            "name": "alice",
            "profile": {"email": "alice@example.com"},
        }

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "user": mock_user_data}
        self.mock_web_client.users_lookupByEmail.return_value = mock_response

        # Call method
        result = self.client.lookup_user_by_email("alice@example.com")

        # Verify API call
        self.mock_web_client.users_lookupByEmail.assert_called_once_with(
            email="alice@example.com"
        )

        # Verify result
        assert result == mock_user_data

    def test_lookup_user_by_email_not_found(self):
        """Test user lookup by email when user not found."""
        # Mock not found response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "users_not_found"}
        self.mock_web_client.users_lookupByEmail.return_value = mock_response

        # Should return None for not found
        result = self.client.lookup_user_by_email("nonexistent@example.com")
        assert result is None

    def test_lookup_user_by_email_other_error(self):
        """Test user lookup by email with other error."""
        # Mock other error response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "invalid_email"}
        self.mock_web_client.users_lookupByEmail.return_value = mock_response

        # Should raise SlackApiError for other errors
        with pytest.raises(SlackApiError):
            self.client.lookup_user_by_email("invalid-email")

    def test_test_auth_success(self):
        """Test successful auth test."""
        # Mock auth response
        mock_auth_data = {
            "ok": True,
            "url": "https://example.slack.com/",
            "team": "Example Team",
            "user": "alice",
            "team_id": "T1234567890",
            "user_id": "U1234567890",
        }

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = mock_auth_data
        self.mock_web_client.auth_test.return_value = mock_response

        # Call method
        result = self.client.test_auth()

        # Verify API call
        self.mock_web_client.auth_test.assert_called_once()

        # Verify result
        assert result == mock_auth_data

    def test_test_auth_error(self):
        """Test auth test with error."""
        # Mock error response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "invalid_auth"}
        self.mock_web_client.auth_test.return_value = mock_response

        # Should raise SlackApiError
        with pytest.raises(SlackApiError):
            self.client.test_auth()

    def test_get_team_info_success(self):
        """Test successful team info retrieval."""
        # Mock team data
        mock_team_data = {
            "id": "T1234567890",
            "name": "Example Team",
            "domain": "example",
            "email_domain": "example.com",
        }

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "team": mock_team_data}
        self.mock_web_client.team_info.return_value = mock_response

        # Call method
        result = self.client.get_team_info()

        # Verify API call
        self.mock_web_client.team_info.assert_called_once()

        # Verify result
        assert result == mock_team_data

    def test_get_team_info_error(self):
        """Test team info retrieval with error."""
        # Mock error response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "access_denied"}
        self.mock_web_client.team_info.return_value = mock_response

        # Should raise SlackApiError
        with pytest.raises(SlackApiError):
            self.client.get_team_info()

    def test_get_team_info_invalid_data(self):
        """Test team info retrieval with invalid team data."""
        # Mock response with invalid team data
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": True, "team": "invalid_data"}
        self.mock_web_client.team_info.return_value = mock_response

        # Should raise ValueError
        with pytest.raises(ValueError, match="Invalid team data received"):
            self.client.get_team_info()


class TestSlackAPIClientEdgeCases:
    """Test edge cases and error handling for SlackAPIClient."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_auth_manager = Mock()
        self.mock_web_client = Mock()
        self.mock_auth_manager.get_client.return_value = self.mock_web_client

        self.client = SlackAPIClient(self.mock_auth_manager)

    def test_list_channels_with_limit(self):
        """Test list_channels respects limit parameter."""
        # Mock response with many channels
        mock_channels = [
            {
                "id": f"C{i:010d}",
                "name": f"channel{i}",
                "is_channel": True,
                "is_member": True,
            }
            for i in range(50)
        ]

        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "channels": mock_channels,
            "response_metadata": {"next_cursor": ""},
        }
        self.mock_web_client.conversations_list.return_value = mock_response

        # Call with limit
        result = self.client.list_channels(limit=10)

        # Should only return 10 channels
        assert len(result) == 10

    def test_get_conversation_history_with_all_params(self):
        """Test conversation history with all parameters."""
        # Mock response
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "messages": [],
            "response_metadata": {"next_cursor": ""},
        }
        self.mock_web_client.conversations_history.return_value = mock_response

        # Call with all parameters
        self.client.get_conversation_history(
            channel_id="C1234567890",
            oldest="1234567880.000",
            latest="1234567900.000",
            inclusive=True,
            limit=50,
            cursor="cursor123",
        )

        # Verify all parameters passed correctly
        self.mock_web_client.conversations_history.assert_called_once_with(
            channel="C1234567890",
            limit=50,
            oldest="1234567880.000",
            latest="1234567900.000",
            cursor="cursor123",
            inclusive=True,
        )

    def test_search_messages_invalid_response(self):
        """Test search_messages with invalid response structure."""
        # Mock response with invalid messages section
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {
            "ok": True,
            "messages": "invalid_structure",  # Should be dict
        }
        self.mock_web_client.search_messages.return_value = mock_response

        # Should handle gracefully and return empty results
        messages, pagination = self.client.search_messages("test")
        assert messages == []
        assert pagination == {}

    def test_large_member_list_pagination(self):
        """Test handling of large member lists with pagination."""
        # Mock first page
        mock_members_page1 = [f"U{i:010d}" for i in range(1000)]
        mock_response_page1 = Mock(spec=SlackResponse)
        mock_response_page1.data = {
            "ok": True,
            "members": mock_members_page1,
            "response_metadata": {"next_cursor": "cursor123"},
        }

        # Mock second page
        mock_members_page2 = [f"U{i:010d}" for i in range(1000, 1500)]
        mock_response_page2 = Mock(spec=SlackResponse)
        mock_response_page2.data = {
            "ok": True,
            "members": mock_members_page2,
            "response_metadata": {"next_cursor": ""},
        }

        self.mock_web_client.conversations_members.side_effect = [
            mock_response_page1,
            mock_response_page2,
        ]

        # Call method
        result = self.client.get_channel_members("C1234567890")

        # Should combine all pages
        assert len(result) == 1500
        assert result[0] == "U0000000000"
        assert result[-1] == "U0000001499"

    def test_api_rate_limit_handling(self):
        """Test handling of API rate limit errors."""
        # Mock rate limit error
        mock_response = Mock(spec=SlackResponse)
        mock_response.data = {"ok": False, "error": "rate_limited"}
        self.mock_web_client.conversations_info.return_value = mock_response

        # Should raise SlackApiError with rate limit info
        with pytest.raises(SlackApiError):
            self.client.get_channel_info("C1234567890")
