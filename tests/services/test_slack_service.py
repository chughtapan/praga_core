"""Tests for SlackService and SlackToolkit."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.slack import (
    SlackChannelListPage,
    SlackChannelPage,
    SlackConversationPage,
    SlackMessagePage,
    SlackMessageSummary,
    SlackService,
    SlackThreadPage,
    SlackToolkit,
    SlackUserPage,
)


class TestSlackService:
    """Test suite for SlackService."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing global context first
        clear_global_context()

        # Create real ServerContext with in-memory SQLite PageCache
        self.context = ServerContext(root="test-root", cache_url="sqlite:///:memory:")

        # Mock handler registration to avoid complexity
        self.context.handler = Mock()

        # Make handler decorator work as a no-op
        def mock_handler_decorator(page_type):
            def decorator(func):
                return func

            return decorator

        self.context.handler.side_effect = mock_handler_decorator

        set_global_context(self.context)

        # Create mock SlackAPIClient
        self.mock_api_client = Mock()
        self.mock_api_client.get_conversation_history = Mock()
        self.mock_api_client.get_thread_replies = Mock()
        self.mock_api_client.get_channel_info = Mock()
        self.mock_api_client.get_channel_members = Mock()
        self.mock_api_client.get_user_info = Mock()
        self.mock_api_client.list_channels = Mock()
        self.mock_api_client.get_team_info = Mock()
        self.mock_api_client.search_messages = Mock()

        self.service = SlackService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test SlackService initialization."""
        assert self.service.api_client is self.mock_api_client
        assert self.service.parser is not None
        assert self.service.name == "slack"
        assert "slack" in self.context.services
        assert self.context.services["slack"] is self.service

    def test_create_conversation_page_success(self):
        """Test successful conversation page creation."""
        # Mock conversation history response
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U123456",
                "text": "Hello everyone!",
            },
            {
                "ts": "1234567890.002",
                "user": "U789012",
                "text": "Hi there!",
            },
        ]

        self.mock_api_client.get_conversation_history.return_value = (
            mock_messages,
            None,
        )

        # Mock channel info
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = ["U123456", "U789012"]

        # Mock user info
        def mock_user_info(user_id):
            users = {
                "U123456": {
                    "id": "U123456",
                    "name": "alice",
                    "real_name": "Alice Smith",
                    "profile": {"display_name": "Alice"},
                },
                "U789012": {
                    "id": "U789012",
                    "name": "bob",
                    "real_name": "Bob Jones",
                    "profile": {"display_name": "Bob"},
                },
            }
            return users.get(user_id, {})

        self.mock_api_client.get_user_info.side_effect = mock_user_info

        # Real page cache is now being used - no mocking needed

        # Call create_conversation_page
        result = self.service.create_conversation_page("C1234567890")

        # Verify API calls
        self.mock_api_client.get_conversation_history.assert_called_once()
        self.mock_api_client.get_channel_info.assert_called_once_with("C1234567890")

        # Verify result
        assert isinstance(result, SlackConversationPage)
        assert result.conversation_id == "C1234567890"
        assert result.channel_id == "C1234567890"
        assert result.channel_name == "general"
        assert result.channel_type == "public_channel"
        assert result.message_count == 2
        assert "Alice" in result.participants
        assert "Bob" in result.participants
        assert "Hello everyone!" in result.messages_content
        assert "Hi there!" in result.messages_content

        # Verify URI
        expected_uri = PageURI(
            root="test-root", type="slack_conversation", id="C1234567890", version=1
        )
        assert result.uri == expected_uri

    def test_create_conversation_page_no_messages(self):
        """Test create_conversation_page with no messages."""
        self.mock_api_client.get_conversation_history.return_value = ([], None)

        # Mock channel info (needed for get_channel_page call)
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
            "created": 1234567890,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = []

        with pytest.raises(ValueError, match="No messages found in channel"):
            self.service.create_conversation_page("C1234567890")

    def test_create_message_page_success(self):
        """Test successful message page creation."""
        # Mock message data
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U123456",
                "text": "This is a test message",
                "thread_ts": None,
            }
        ]
        self.mock_api_client.get_conversation_history.return_value = (
            mock_messages,
            None,
        )

        # Mock channel info
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = ["U123456"]

        # Mock user info
        self.mock_api_client.get_user_info.return_value = {
            "id": "U123456",
            "name": "alice",
            "real_name": "Alice Smith",
            "profile": {"display_name": "Alice"},
        }

        # Real page cache is now being used - no mocking needed

        # Create message page
        message_id = "C1234567890_1234567890.001"
        result = self.service.create_message_page(message_id)

        # Verify result
        assert isinstance(result, SlackMessagePage)
        assert result.message_ts == "1234567890.001"
        assert result.channel_id == "C1234567890"
        assert result.channel_name == "general"
        assert result.display_name == "Alice"
        assert result.text_content == "This is a test message"
        assert result.thread_ts is None

        # Verify URI
        expected_uri = PageURI(
            root="test-root", type="slack_message", id=message_id, version=1
        )
        assert result.uri == expected_uri

    def test_create_message_page_not_found(self):
        """Test create_message_page when message not found."""
        self.mock_api_client.get_conversation_history.return_value = ([], None)

        # Mock channel info (needed for get_channel_page call)
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
            "created": 1234567890,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = []

        with pytest.raises(RuntimeError, match="Unable to find message"):
            self.service.create_message_page("C1234567890_1234567890.001")

    def test_create_thread_page_success(self):
        """Test successful thread page creation."""
        # Mock thread messages
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U123456",
                "text": "This is the parent message",
            },
            {
                "ts": "1234567890.002",
                "user": "U789012",
                "text": "This is a reply",
            },
        ]
        self.mock_api_client.get_thread_replies.return_value = mock_messages

        # Mock channel info
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = ["U123456", "U789012"]

        # Mock user info
        def mock_user_info(user_id):
            users = {
                "U123456": {
                    "id": "U123456",
                    "name": "alice",
                    "profile": {"display_name": "Alice"},
                },
                "U789012": {
                    "id": "U789012",
                    "name": "bob",
                    "profile": {"display_name": "Bob"},
                },
            }
            return users.get(user_id, {})

        self.mock_api_client.get_user_info.side_effect = mock_user_info

        # Real page cache is now being used - no mocking needed

        # Create thread page
        thread_id = "C1234567890_1234567890.001"
        result = self.service.create_thread_page(thread_id)

        # Verify result
        assert isinstance(result, SlackThreadPage)
        assert result.thread_ts == "1234567890.001"
        assert result.channel_id == "C1234567890"
        assert result.channel_name == "general"
        assert result.parent_message == "This is the parent message"
        assert result.message_count == 2
        assert len(result.messages) == 2
        assert "Alice" in result.participants
        assert "Bob" in result.participants

        # Verify messages
        assert result.messages[0].display_name == "Alice"
        assert result.messages[0].text == "This is the parent message"
        assert result.messages[1].display_name == "Bob"
        assert result.messages[1].text == "This is a reply"

    def test_create_thread_page_no_messages(self):
        """Test create_thread_page with no messages."""
        self.mock_api_client.get_thread_replies.return_value = []

        with pytest.raises(ValueError, match="Thread .* contains no messages"):
            self.service.create_thread_page("C1234567890_1234567890.001")

    def test_create_channel_page_success(self):
        """Test successful channel page creation."""
        # Mock channel info
        mock_channel_info = {
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
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = ["U123456", "U789012"]

        # Create channel page
        result = self.service.create_channel_page("C1234567890")

        # Verify result
        assert isinstance(result, SlackChannelPage)
        assert result.channel_id == "C1234567890"
        assert result.name == "general"
        assert result.channel_type == "public_channel"
        assert result.topic == "General discussion"
        assert result.purpose == "Company-wide announcements"
        assert result.member_count == 2
        assert not result.is_archived

        # Verify URI
        expected_uri = PageURI(
            root="test-root", type="slack_channel", id="C1234567890", version=1
        )
        assert result.uri == expected_uri

    def test_create_user_page_success(self):
        """Test successful user page creation."""
        # Mock user info
        mock_user_info = {
            "id": "U123456",
            "name": "alice",
            "real_name": "Alice Smith",
            "is_bot": False,
            "is_admin": True,
            "profile": {
                "display_name": "Alice",
                "email": "alice@example.com",
                "title": "Software Engineer",
                "status_text": "Working on tests",
                "status_emoji": ":computer:",
            },
        }
        self.mock_api_client.get_user_info.return_value = mock_user_info

        # Create user page
        result = self.service.create_user_page("U123456")

        # Verify result
        assert isinstance(result, SlackUserPage)
        assert result.user_id == "U123456"
        assert result.name == "alice"
        assert result.real_name == "Alice Smith"
        assert result.display_name == "Alice"
        assert result.email == "alice@example.com"
        assert result.title == "Software Engineer"
        assert not result.is_bot
        assert result.is_admin
        assert result.status_text == "Working on tests"
        assert result.status_emoji == ":computer:"

        # Verify URI
        expected_uri = PageURI(
            root="test-root", type="slack_user", id="U123456", version=1
        )
        assert result.uri == expected_uri

    def test_get_user_display_name(self):
        """Test get_user_display_name method."""
        # Mock user info with display name
        mock_user_info = {
            "id": "U123456",
            "name": "alice",
            "real_name": "Alice Smith",
            "profile": {"display_name": "Alice"},
        }
        self.mock_api_client.get_user_info.return_value = mock_user_info

        # Real page cache is now being used - no mocking needed

        result = self.service.get_user_display_name("U123456")
        assert result == "Alice"

        # Test with empty user ID
        result = self.service.get_user_display_name("")
        assert result == "unknown"

    def test_search_messages(self):
        """Test search_messages method."""
        # Mock search response
        mock_messages = [
            {
                "ts": "1234567890.001",
                "channel": {"id": "C1234567890"},
                "user": "U123456",
                "text": "Test message 1",
            },
            {
                "ts": "1234567890.002",
                "channel": {"id": "C1234567890"},
                "user": "U789012",
                "text": "Test message 2",
            },
        ]
        mock_pagination = {"page": 1, "page_count": 1, "total": 2}

        self.mock_api_client.search_messages.return_value = (
            mock_messages,
            mock_pagination,
        )

        # Call search_messages
        uris, next_token = self.service.search_messages("test query")

        # Verify API call
        self.mock_api_client.search_messages.assert_called_once()

        # Verify results
        assert len(uris) == 2
        assert all(isinstance(uri, PageURI) for uri in uris)
        assert all(uri.type == "slack_message" for uri in uris)
        assert all(uri.root == "test-root" for uri in uris)

    def test_name_property(self):
        """Test name property."""
        assert self.service.name == "slack"


class TestSlackPageTypes:
    """Test page type serialization and validation."""

    def setup_method(self):
        """Set up test data."""
        self.test_uri = PageURI(
            root="test", type="slack_message", id="test123", version=1
        )
        self.test_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_slack_message_summary_serialization(self):
        """Test SlackMessageSummary serialization."""
        summary = SlackMessageSummary(
            display_name="Alice",
            text="Test message",
            timestamp=self.test_time,
        )

        # Test serialization
        data = summary.model_dump()
        assert data["display_name"] == "Alice"
        assert data["text"] == "Test message"
        assert isinstance(data["timestamp"], datetime)

        # Test deserialization
        new_summary = SlackMessageSummary.model_validate(data)
        assert new_summary.display_name == "Alice"
        assert new_summary.text == "Test message"
        assert new_summary.timestamp == self.test_time

    def test_slack_message_summary_required_fields(self):
        """Test SlackMessageSummary with missing required fields."""
        with pytest.raises(ValidationError):
            SlackMessageSummary()

        with pytest.raises(ValidationError):
            SlackMessageSummary(display_name="Alice")

    def test_slack_conversation_page_serialization(self):
        """Test SlackConversationPage serialization."""
        # Create proper URI for slack_conversation page type
        conversation_uri = PageURI(
            root="test", type="slack_conversation", id="conv123", version=1
        )

        page = SlackConversationPage(
            uri=conversation_uri,
            conversation_id="conv123",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            start_time=self.test_time,
            end_time=self.test_time,
            message_count=5,
            participants=["Alice", "Bob"],
            messages_content="Alice: Hello\nBob: Hi",
            permalink="https://slack.com/app_redirect?channel=C1234567890",
        )

        # Test serialization
        data = page.model_dump()
        assert data["channel_name"] == "general"
        assert data["channel_type"] == "public_channel"
        assert data["message_count"] == 5
        assert data["participants"] == ["Alice", "Bob"]
        assert "conversation_id" not in data  # Should be excluded

        # Test deserialization
        data["uri"] = conversation_uri  # Add URI back for validation
        data["conversation_id"] = "conv123"  # Add excluded fields back for validation
        data["channel_id"] = "C1234567890"
        new_page = SlackConversationPage.model_validate(data)
        assert new_page.channel_name == "general"
        assert new_page.message_count == 5

    def test_slack_thread_page_serialization(self):
        """Test SlackThreadPage serialization."""
        message1 = SlackMessageSummary(
            display_name="Alice",
            text="Parent message",
            timestamp=self.test_time,
        )
        message2 = SlackMessageSummary(
            display_name="Bob",
            text="Reply message",
            timestamp=self.test_time,
        )

        # Create proper URI for slack_thread page type
        thread_uri = PageURI(
            root="test", type="slack_thread", id="thread123", version=1
        )

        page = SlackThreadPage(
            uri=thread_uri,
            thread_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            parent_message="Parent message",
            messages=[message1, message2],
            message_count=2,
            participants=["Alice", "Bob"],
            created_at=self.test_time,
            last_reply_at=self.test_time,
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        # Test serialization
        data = page.model_dump()
        assert data["channel_name"] == "general"
        assert data["parent_message"] == "Parent message"
        assert data["message_count"] == 2
        assert len(data["messages"]) == 2
        assert "thread_ts" not in data  # Should be excluded

        # Test deserialization
        data["uri"] = thread_uri  # Add URI back for validation
        data["thread_ts"] = "1234567890.001"  # Add excluded fields back for validation
        data["channel_id"] = "C1234567890"
        new_page = SlackThreadPage.model_validate(data)
        assert new_page.channel_name == "general"
        assert new_page.message_count == 2
        assert len(new_page.messages) == 2

    def test_slack_thread_page_methods(self):
        """Test SlackThreadPage helper methods."""
        message1 = SlackMessageSummary(
            display_name="Alice",
            text="Hello everyone",
            timestamp=self.test_time,
        )
        message2 = SlackMessageSummary(
            display_name="Bob",
            text="Hi there!",
            timestamp=self.test_time,
        )

        page = SlackThreadPage(
            uri=self.test_uri,
            thread_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            parent_message="Hello everyone, let's discuss this",
            messages=[message1, message2],
            message_count=2,
            participants=["Alice", "Bob"],
            created_at=self.test_time,
            last_reply_at=self.test_time,
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        # Test thread_messages property
        thread_messages = page.thread_messages
        assert "Alice: Hello everyone" in thread_messages
        assert "Bob: Hi there!" in thread_messages

    def test_slack_thread_page_long_parent_message(self):
        """Test SlackThreadPage with long parent message."""
        thread_uri = PageURI(
            root="test", type="slack_thread", id="thread123", version=1
        )

        long_message = "This is a very long message that should be stored properly in the thread page"
        page = SlackThreadPage(
            uri=thread_uri,
            thread_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            parent_message=long_message,
            messages=[],
            message_count=0,
            participants=[],
            created_at=self.test_time,
            last_reply_at=None,
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        assert page.parent_message == long_message
        assert page.message_count == 0
        assert len(page.messages) == 0

    def test_slack_channel_page_serialization(self):
        """Test SlackChannelPage serialization."""
        channel_uri = PageURI(
            root="test", type="slack_channel", id="C1234567890", version=1
        )

        page = SlackChannelPage(
            uri=channel_uri,
            channel_id="C1234567890",
            name="general",
            channel_type="public_channel",
            topic="General discussion",
            purpose="Company-wide announcements",
            member_count=100,
            created=self.test_time,
            is_archived=False,
            last_activity=self.test_time,
            permalink="https://slack.com/app_redirect?channel=C1234567890",
        )

        # Test serialization
        data = page.model_dump()
        assert data["name"] == "general"
        assert data["channel_type"] == "public_channel"
        assert data["member_count"] == 100
        assert not data["is_archived"]
        assert "channel_id" not in data  # Should be excluded

        # Test deserialization
        data["uri"] = channel_uri  # Add URI back for validation
        data["channel_id"] = "C1234567890"  # Add excluded fields back for validation
        new_page = SlackChannelPage.model_validate(data)
        assert new_page.name == "general"
        assert new_page.member_count == 100

    def test_slack_user_page_serialization(self):
        """Test SlackUserPage serialization."""
        user_uri = PageURI(root="test", type="slack_user", id="U123456", version=1)

        page = SlackUserPage(
            uri=user_uri,
            user_id="U123456",
            name="alice",
            real_name="Alice Smith",
            display_name="Alice",
            email="alice@example.com",
            title="Software Engineer",
            is_bot=False,
            is_admin=True,
            status_text="Working",
            status_emoji=":computer:",
            last_updated=self.test_time,
        )

        # Test serialization
        data = page.model_dump()
        assert data["name"] == "alice"
        assert data["real_name"] == "Alice Smith"
        assert data["email"] == "alice@example.com"
        assert not data["is_bot"]
        assert data["is_admin"]
        assert "user_id" not in data  # Should be excluded

        # Test deserialization
        data["uri"] = user_uri  # Add URI back for validation
        data["user_id"] = "U123456"  # Add excluded fields back for validation
        new_page = SlackUserPage.model_validate(data)
        assert new_page.name == "alice"
        assert new_page.is_admin

    def test_slack_message_page_serialization(self):
        """Test SlackMessagePage serialization."""
        message_uri = PageURI(
            root="test",
            type="slack_message",
            id="C1234567890_1234567890.001",
            version=1,
        )

        page = SlackMessagePage(
            uri=message_uri,
            message_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U123456",
            display_name="Alice",
            text_content="Test message",
            timestamp=self.test_time,
            thread_ts="1234567890.001",
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        # Test serialization
        data = page.model_dump()
        assert data["channel_name"] == "general"
        assert data["display_name"] == "Alice"
        assert data["text_content"] == "Test message"
        assert "message_ts" not in data  # Should be excluded
        assert "channel_id" not in data  # Should be excluded
        assert "user_id" not in data  # Should be excluded

        # Test deserialization
        data["uri"] = message_uri  # Add URI back for validation
        data["message_ts"] = "1234567890.001"  # Add excluded fields back for validation
        data["channel_id"] = "C1234567890"
        data["user_id"] = "U123456"
        new_page = SlackMessagePage.model_validate(data)
        assert new_page.channel_name == "general"
        assert new_page.display_name == "Alice"

    def test_slack_message_page_computed_fields(self):
        """Test SlackMessagePage computed field properties."""
        page = SlackMessagePage(
            uri=PageURI(
                root="test",
                type="slack_message",
                id="C1234567890_1234567890.001",
                version=1,
            ),
            message_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U123456",
            display_name="Alice",
            text_content="Test message",
            timestamp=self.test_time,
            thread_ts="1234567890.001",
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        # Test thread_uri property
        thread_uri = page.thread_uri
        assert isinstance(thread_uri, PageURI)
        assert thread_uri.root == "test"
        assert thread_uri.type == "slack_thread"
        assert thread_uri.id == "C1234567890_1234567890.001"
        assert thread_uri.version == 1

        # Test with no thread_ts
        page_no_thread = SlackMessagePage(
            uri=self.test_uri,
            message_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U123456",
            display_name="Alice",
            text_content="Test message",
            timestamp=self.test_time,
            thread_ts=None,
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        assert page_no_thread.thread_uri is None

    def test_slack_channel_list_page_serialization(self):
        """Test SlackChannelListPage serialization."""
        channels_data = [
            {
                "id": "C1234567890",
                "name": "general",
                "is_channel": True,
                "member_count": 100,
            },
            {
                "id": "C0987654321",
                "name": "random",
                "is_channel": True,
                "member_count": 50,
            },
        ]

        channel_list_uri = PageURI(
            root="test", type="slack_channel_list", id="T1234567890", version=1
        )

        page = SlackChannelListPage(
            uri=channel_list_uri,
            workspace_id="T1234567890",
            workspace_name="Test Workspace",
            total_channels=2,
            public_channels=2,
            private_channels=0,
            channels=channels_data,
            last_updated=self.test_time,
        )

        # Test serialization
        data = page.model_dump()
        assert data["workspace_name"] == "Test Workspace"
        assert data["total_channels"] == 2
        assert data["public_channels"] == 2
        assert len(data["channels"]) == 2
        assert "workspace_id" not in data  # Should be excluded

        # Test deserialization
        data["uri"] = channel_list_uri  # Add URI back for validation
        data["workspace_id"] = "T1234567890"  # Add excluded fields back for validation
        new_page = SlackChannelListPage.model_validate(data)
        assert new_page.workspace_name == "Test Workspace"
        assert new_page.total_channels == 2


class TestSlackToolkit:
    """Test SlackToolkit functionality."""

    def setup_method(self):
        """Set up test environment."""
        clear_global_context()

        # Create real ServerContext with in-memory SQLite PageCache
        self.context = ServerContext(root="test-root", cache_url="sqlite:///:memory:")

        # Mock handler registration to avoid complexity
        self.context.handler = Mock()

        def mock_handler_decorator(page_type):
            def decorator(func):
                return func

            return decorator

        self.context.handler.side_effect = mock_handler_decorator

        set_global_context(self.context)

        # Create mock SlackAPIClient and service
        self.mock_api_client = Mock()
        self.slack_service = SlackService(self.mock_api_client)
        self.toolkit = SlackToolkit(self.slack_service)

    def _create_mock_message_page(self, msg_id="msg1"):
        """Helper to create a mock SlackMessagePage."""
        mock_uri = PageURI(root="test-root", type="slack_message", id=msg_id, version=1)
        return SlackMessagePage(
            uri=mock_uri,
            message_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U123456",
            display_name="Alice",
            text_content="Test message",
            timestamp=datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
            thread_ts=None,  # Add missing required field
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_toolkit_init(self):
        """Test SlackToolkit initialization."""
        assert self.toolkit.slack_service is self.slack_service
        assert self.toolkit.name == "slack"

    def test_search_messages_by_content(self):
        """Test search_messages_by_content tool."""
        # Mock search results with actual message pages
        mock_uri1 = PageURI(
            root="test-root", type="slack_message", id="msg1", version=1
        )
        mock_uri2 = PageURI(
            root="test-root", type="slack_message", id="msg2", version=1
        )

        mock_page1 = SlackMessagePage(
            uri=mock_uri1,
            message_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U123456",
            display_name="Alice",
            text_content="Test message 1",
            timestamp=datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
            thread_ts=None,  # Add missing required field
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        mock_page2 = SlackMessagePage(
            uri=mock_uri2,
            message_ts="1234567890.002",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U789012",
            display_name="Bob",
            text_content="Test message 2",
            timestamp=datetime(2023, 6, 15, 10, 31, 0, tzinfo=timezone.utc),
            thread_ts=None,  # Add missing required field
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.002",
        )

        self.slack_service.search_messages = Mock(
            return_value=([mock_uri1, mock_uri2], "next_token")
        )

        # Mock the page resolution - use the global context
        def mock_get_page(uri):
            if uri.id == "msg1":
                return mock_page1
            elif uri.id == "msg2":
                return mock_page2
            return Mock()

        self.context.get_page = Mock(side_effect=mock_get_page)

        # Call tool
        result = self.toolkit.search_messages_by_content("test query")

        # Verify result
        assert len(result.results) == 2
        assert result.next_cursor == "next_token"
        assert all(isinstance(page, SlackMessagePage) for page in result.results)

    def test_search_messages_by_channel(self):
        """Test search_messages_by_channel tool."""
        # Create mock message page
        mock_uri = PageURI(root="test-root", type="slack_message", id="msg1", version=1)
        mock_page = SlackMessagePage(
            uri=mock_uri,
            message_ts="1234567890.001",
            channel_id="C1234567890",
            channel_name="general",
            channel_type="public_channel",
            user_id="U123456",
            display_name="Alice",
            text_content="Test message",
            timestamp=datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc),
            thread_ts=None,
            permalink="https://slack.com/app_redirect?channel=C1234567890&message_ts=1234567890.001",
        )

        self.slack_service.search_messages = Mock(return_value=([mock_uri], None))
        self.context.get_page = Mock(return_value=mock_page)

        self.toolkit.search_messages_by_channel("general")

        # Verify search query includes channel filter
        self.slack_service.search_messages.assert_called_once()
        search_query = self.slack_service.search_messages.call_args[0][0]
        assert "in:#general" in search_query

    def test_search_messages_by_person(self):
        """Test search_messages_by_person tool."""
        mock_page = self._create_mock_message_page()
        mock_uri = mock_page.uri

        self.slack_service.search_messages = Mock(return_value=([mock_uri], None))
        self.context.get_page = Mock(return_value=mock_page)

        self.toolkit.search_messages_by_person("@alice")

        # Verify search query includes person filter
        self.slack_service.search_messages.assert_called_once()
        search_query = self.slack_service.search_messages.call_args[0][0]
        assert "from:@alice" in search_query

    def test_search_messages_by_date_range(self):
        """Test search_messages_by_date_range tool."""
        mock_page = self._create_mock_message_page()
        mock_uri = mock_page.uri

        self.slack_service.search_messages = Mock(return_value=([mock_uri], None))
        self.context.get_page = Mock(return_value=mock_page)

        self.toolkit.search_messages_by_date_range("2023-06-15", 7)

        # Verify search query includes date filters
        self.slack_service.search_messages.assert_called_once()
        search_query = self.slack_service.search_messages.call_args[0][0]
        assert "after:2023-06-15" in search_query
        assert "before:2023-06-22" in search_query

    def test_search_recent_messages(self):
        """Test search_recent_messages tool."""
        mock_page = self._create_mock_message_page()
        mock_uri = mock_page.uri

        self.slack_service.search_messages = Mock(return_value=([mock_uri], None))
        self.context.get_page = Mock(return_value=mock_page)

        self.toolkit.search_recent_messages(days=3)

        # Verify search was called
        self.slack_service.search_messages.assert_called_once()

    def test_search_direct_messages(self):
        """Test search_direct_messages tool."""
        mock_page = self._create_mock_message_page()
        mock_uri = mock_page.uri

        self.slack_service.search_messages = Mock(return_value=([mock_uri], None))
        self.context.get_page = Mock(return_value=mock_page)

        self.toolkit.search_direct_messages(person="@alice")

        # Verify search query includes DM filters
        self.slack_service.search_messages.assert_called_once()
        search_query = self.slack_service.search_messages.call_args[0][0]
        assert "in:@alice" in search_query

    def test_get_conversation_with_person(self):
        """Test get_conversation_with_person tool."""
        mock_page = self._create_mock_message_page()
        mock_uri = mock_page.uri

        self.slack_service.search_messages = Mock(return_value=([mock_uri], None))
        self.context.get_page = Mock(return_value=mock_page)

        self.toolkit.get_conversation_with_person("@alice")

        # Verify search query
        self.slack_service.search_messages.assert_called_once()
        search_query = self.slack_service.search_messages.call_args[0][0]
        assert (
            search_query == "@alice"
        )  # The method just passes the validated person identifier


class TestSlackServiceIntegration:
    """Integration tests for SlackService components."""

    def setup_method(self):
        """Set up test environment."""
        clear_global_context()

        self.context = ServerContext(root="test-root", cache_url="sqlite:///:memory:")
        self.context.handler = Mock()

        def mock_handler_decorator(page_type):
            def decorator(func):
                return func

            return decorator

        self.context.handler.side_effect = mock_handler_decorator

        set_global_context(self.context)

        self.mock_api_client = Mock()
        self.service = SlackService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_message_page_thread_uri_matches_thread_page_uri(self):
        """Test that message page thread_uri matches thread page URI."""
        # Setup message with thread
        mock_messages = [
            {
                "ts": "1234567890.001",
                "user": "U123456",
                "text": "Test message in thread",
                "thread_ts": "1234567890.001",
            }
        ]
        self.mock_api_client.get_conversation_history.return_value = (
            mock_messages,
            None,
        )

        # Mock channel and user info
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = ["U123456"]

        mock_user_info = {
            "id": "U123456",
            "name": "alice",
            "profile": {"display_name": "Alice"},
        }
        self.mock_api_client.get_user_info.return_value = mock_user_info

        # Mock thread replies
        self.mock_api_client.get_thread_replies.return_value = mock_messages

        # Real page cache is now being used - no mocking needed

        # Create message page
        message_id = "C1234567890_1234567890.001"
        message_page = self.service.create_message_page(message_id)

        # Create thread page
        thread_id = "C1234567890_1234567890.001"
        thread_page = self.service.create_thread_page(thread_id)

        # Verify URIs match
        assert message_page.thread_uri == thread_page.uri

    def test_channel_page_caching(self):
        """Test that channel pages are properly cached."""
        # Mock channel info
        mock_channel_info = {
            "id": "C1234567890",
            "name": "general",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
        }
        self.mock_api_client.get_channel_info.return_value = mock_channel_info
        self.mock_api_client.get_channel_members.return_value = []

        # Real page cache is now being used - test actual caching behavior

        # First call should create the page
        page1 = self.service.get_channel_page("C1234567890")

        # Second call should return cached page
        page2 = self.service.get_channel_page("C1234567890")

        assert page1.uri == page2.uri
        assert page1.name == page2.name
        assert page1.channel_type == page2.channel_type

        # API should only be called once
        self.mock_api_client.get_channel_info.assert_called_once()

    def test_user_page_caching(self):
        """Test that user pages are properly cached."""
        # Mock user info
        mock_user_info = {
            "id": "U123456",
            "name": "alice",
            "profile": {"display_name": "Alice"},
        }
        self.mock_api_client.get_user_info.return_value = mock_user_info

        # First call should create the page
        page1 = self.service.get_user_page("U123456")

        # Second call should return cached page
        page2 = self.service.get_user_page("U123456")

        assert page1.uri == page2.uri
        assert page1.name == page2.name
        assert page1.user_id == page2.user_id

        self.mock_api_client.get_user_info.assert_called_once()
