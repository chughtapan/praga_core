"""Tests for existing GmailService before refactoring."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.gmail import EmailPage, GmailService


class TestGmailService:
    """Test suite for GmailService."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}  # Mock services dictionary

        # Mock the register_service method to actually register
        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service

        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()

        # Mock the client methods
        self.mock_api_client.get_message = Mock()
        self.mock_api_client.search_messages = Mock()

        self.service = GmailService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test GmailService initialization."""
        assert self.service.api_client is self.mock_api_client
        assert self.service.parser is not None
        assert self.service.name == "email"

        # Verify service is registered in context (service auto-registers via ServiceContext)
        assert "email" in self.mock_context.services
        assert self.mock_context.services["email"] is self.service

    def test_root_property(self):
        """Test root property returns context root."""
        assert self.service.context.root == "test-root"

    def test_create_page_success(self):
        """Test successful email page creation."""
        # Setup mock message response
        mock_message = {
            "id": "msg123",
            "threadId": "thread456",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {
                        "name": "To",
                        "value": "recipient1@example.com, recipient2@example.com",
                    },
                    {"name": "Cc", "value": "cc1@example.com, cc2@example.com"},
                    {"name": "Date", "value": "Thu, 15 Jun 2023 10:30:00 +0000"},
                ]
            },
        }

        self.mock_api_client.get_message.return_value = mock_message

        # Mock parser
        mock_body = "Test email body content"
        self.service.parser.extract_body = Mock(return_value=mock_body)

        # Call create_page
        result = self.service.create_page("msg123")

        # Verify API client call
        self.mock_api_client.get_message.assert_called_once_with("msg123")

        # Verify result
        assert isinstance(result, EmailPage)
        assert result.message_id == "msg123"
        assert result.thread_id == "thread456"
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient1@example.com", "recipient2@example.com"]
        assert result.cc_list == ["cc1@example.com", "cc2@example.com"]
        assert result.body == mock_body
        assert result.permalink == "https://mail.google.com/mail/u/0/#inbox/thread456"

        # Verify URI
        expected_uri = PageURI(root="test-root", type="email", id="msg123", version=1)
        assert result.uri == expected_uri

    def test_create_page_api_error(self):
        """Test create_page handles API errors."""
        self.mock_api_client.get_message.side_effect = Exception("API Error")

        with pytest.raises(ValueError, match="Failed to fetch email msg123: API Error"):
            self.service.create_page("msg123")

    def test_create_page_minimal_headers(self):
        """Test create_page with minimal headers."""
        mock_message = {
            "id": "msg123",
            "threadId": "thread456",
            "payload": {"headers": []},
        }

        self.mock_api_client.get_message.return_value = mock_message
        self.service.parser.extract_body = Mock(return_value="")

        result = self.service.create_page("msg123")

        assert result.subject == ""
        assert result.sender == ""
        assert result.recipients == []
        assert result.cc_list == []
        assert isinstance(result.time, datetime)

    def test_create_page_missing_thread_id(self):
        """Test create_page when threadId is missing."""
        mock_message = {"id": "msg123", "payload": {"headers": []}}

        self.mock_api_client.get_message.return_value = mock_message
        self.service.parser.extract_body = Mock(return_value="")

        result = self.service.create_page("msg123")

        assert result.thread_id == "msg123"  # Falls back to message ID
        assert result.permalink == "https://mail.google.com/mail/u/0/#inbox/msg123"

    def test_search_emails_basic(self):
        """Test basic email search."""
        mock_messages = [{"id": "msg1"}, {"id": "msg2"}, {"id": "msg3"}]

        self.mock_api_client.search_messages.return_value = (mock_messages, "token123")

        uris, next_token = self.service.search_emails("test query")

        # Verify API call
        self.mock_api_client.search_messages.assert_called_once_with(
            "test query", page_token=None, page_size=20
        )

        # Verify results
        assert len(uris) == 3
        assert all(isinstance(uri, PageURI) for uri in uris)
        assert uris[0].id == "msg1"
        assert uris[1].id == "msg2"
        assert uris[2].id == "msg3"
        assert all(uri.type == "email" for uri in uris)
        assert all(uri.root == "test-root" for uri in uris)
        assert next_token == "token123"

    def test_search_emails_with_inbox_filter(self):
        """Test search passes query through to API client."""
        self.mock_api_client.search_messages.return_value = ([], None)

        self.service.search_emails("in:sent test query")

        self.mock_api_client.search_messages.assert_called_once_with(
            "in:sent test query", page_token=None, page_size=20
        )

    def test_search_emails_with_pagination(self):
        """Test search with pagination parameters."""
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)

        uris, next_token = self.service.search_emails(
            "test", page_token="prev_token", page_size=10
        )

        self.mock_api_client.search_messages.assert_called_once_with(
            "test", page_token="prev_token", page_size=10
        )

        assert len(uris) == 1
        assert next_token is None

    def test_search_emails_empty_query(self):
        """Test search with empty query."""
        self.mock_api_client.search_messages.return_value = ([], None)

        self.service.search_emails("")

        self.mock_api_client.search_messages.assert_called_once_with(
            "", page_token=None, page_size=20
        )

    def test_search_emails_api_error(self):
        """Test search_emails handles API errors."""
        self.mock_api_client.search_messages.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            self.service.search_emails("test")

    def test_search_emails_no_results(self):
        """Test search with no results."""
        self.mock_api_client.search_messages.return_value = ([], None)

        uris, next_token = self.service.search_emails("nonexistent")

        assert uris == []
        assert next_token is None

    def test_name_property(self):
        """Test name property returns correct value."""
        assert self.service.name == "email"
