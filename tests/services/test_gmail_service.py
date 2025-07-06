"""Tests for existing GmailService before refactoring."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.gmail import (
    EmailPage,
    EmailSummary,
    EmailThreadPage,
    GmailService,
)


class TestGmailService:
    """Test suite for GmailService."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing global context first
        clear_global_context()

        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}  # Mock services dictionary

        # Mock the register_service method to actually register
        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service

        # Mock create_page_uri to return predictable URIs
        self.mock_context.create_page_uri = AsyncMock(
            side_effect=lambda page_type, type_path, id, version=None: PageURI(
                root="test-root", type=type_path, id=id, version=version or 1
            )
        )

        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()

        # Mock the client methods (now async)
        self.mock_api_client.get_message = AsyncMock()
        self.mock_api_client.search_messages = AsyncMock()
        self.mock_api_client.get_thread = AsyncMock()

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

    def test_toolkit_property(self):
        """Test that toolkit property returns self (merged functionality)."""
        toolkit = self.service.toolkit
        assert toolkit is self.service
        # Verify it has the toolkit methods
        assert hasattr(toolkit, "search_emails_from_person")
        assert hasattr(toolkit, "search_emails_to_person")
        assert hasattr(toolkit, "search_emails_by_content")
        assert hasattr(toolkit, "get_recent_emails")
        assert hasattr(toolkit, "get_unread_emails")

    def test_root_property(self):
        """Test root property returns context root."""
        assert self.service.context.root == "test-root"

    @pytest.mark.asyncio
    async def test_create_email_page_success(self):
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

        # Call create_email_page
        expected_uri = PageURI(root="test-root", type="email", id="msg123", version=1)
        result = await self.service.create_email_page(expected_uri)

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

    @pytest.mark.asyncio
    async def test_email_page_thread_uri_property(self):
        """Test that EmailPage has thread_uri property that links to thread page."""
        # Setup mock message response with all required fields
        mock_message = {
            "id": "msg123",
            "threadId": "thread456",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Date", "value": "Thu, 15 Jun 2023 10:30:00 +0000"},
                ]
            },
        }

        self.mock_api_client.get_message.return_value = mock_message
        self.service.parser.extract_body = Mock(return_value="Test body")

        # Create email page
        expected_uri = PageURI(root="test-root", type="email", id="msg123", version=1)
        email_page = await self.service.create_email_page(expected_uri)

        # Test thread_uri property
        thread_uri = email_page.thread_uri
        assert isinstance(thread_uri, PageURI)
        assert thread_uri.root == "test-root"
        assert thread_uri.type == "email_thread"
        assert thread_uri.id == "thread456"
        assert thread_uri.version == 1

    @pytest.mark.asyncio
    async def test_create_thread_page_success(self):
        """Test successful thread page creation."""
        # Setup mock thread response with multiple messages
        mock_thread = {
            "id": "thread456",
            "messages": [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Original Subject"},
                            {"name": "From", "value": "alice@example.com"},
                            {"name": "To", "value": "bob@example.com"},
                            {
                                "name": "Date",
                                "value": "Mon, 10 Jun 2023 09:00:00 +0000",
                            },
                        ]
                    },
                },
                {
                    "id": "msg2",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Re: Original Subject"},
                            {"name": "From", "value": "bob@example.com"},
                            {"name": "To", "value": "alice@example.com"},
                            {"name": "Cc", "value": "charlie@example.com"},
                            {
                                "name": "Date",
                                "value": "Mon, 10 Jun 2023 10:00:00 +0000",
                            },
                        ]
                    },
                },
                {
                    "id": "msg3",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Re: Original Subject"},
                            {"name": "From", "value": "alice@example.com"},
                            {"name": "To", "value": "bob@example.com"},
                            {
                                "name": "Date",
                                "value": "Mon, 10 Jun 2023 11:00:00 +0000",
                            },
                        ]
                    },
                },
            ],
        }

        self.mock_api_client.get_thread.return_value = mock_thread

        # Mock parser for body extraction
        self.service.parser.extract_body = Mock(return_value="Email body content")

        # Call create_thread_page
        expected_uri = PageURI(
            root="test-root", type="email_thread", id="thread456", version=1
        )
        result = await self.service.create_thread_page(expected_uri)

        # Verify API client call
        self.mock_api_client.get_thread.assert_called_once_with("thread456")

        # Verify result
        assert isinstance(result, EmailThreadPage)
        assert result.thread_id == "thread456"
        assert result.subject == "Original Subject"  # Should be from first message
        assert len(result.emails) == 3

        # Verify email summaries
        assert all(hasattr(email, "uri") for email in result.emails)
        assert all(hasattr(email, "sender") for email in result.emails)
        assert all(hasattr(email, "body") for email in result.emails)

        # Check first email summary
        first_email = result.emails[0]
        assert first_email.uri.type == "email"
        assert first_email.uri.id == "msg1"
        assert first_email.sender == "alice@example.com"
        assert first_email.recipients == ["bob@example.com"]

        # Verify permalink
        assert result.permalink == "https://mail.google.com/mail/u/0/#inbox/thread456"

        # Verify URI
        expected_uri = PageURI(
            root="test-root", type="email_thread", id="thread456", version=1
        )
        assert result.uri == expected_uri

    @pytest.mark.asyncio
    async def test_create_thread_page_api_error(self):
        """Test create_thread_page handles API errors."""
        self.mock_api_client.get_thread.side_effect = Exception("API Error")

        with pytest.raises(
            ValueError, match="Failed to fetch thread thread456: API Error"
        ):
            expected_uri = PageURI(
                root="test-root", type="email_thread", id="thread456", version=1
            )
            await self.service.create_thread_page(expected_uri)

    @pytest.mark.asyncio
    async def test_create_thread_page_empty_thread(self):
        """Test create_thread_page handles thread with no messages."""
        mock_thread = {"id": "thread456", "messages": []}
        self.mock_api_client.get_thread.return_value = mock_thread

        with pytest.raises(ValueError, match="Thread thread456 contains no messages"):
            expected_uri = PageURI(
                root="test-root", type="email_thread", id="thread456", version=1
            )
            await self.service.create_thread_page(expected_uri)

    @pytest.mark.asyncio
    async def test_create_thread_page_minimal_headers(self):
        """Test create_thread_page with minimal headers."""
        mock_thread = {
            "id": "thread456",
            "messages": [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Test Subject"},
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "To", "value": "recipient@example.com"},
                            {
                                "name": "Date",
                                "value": "Thu, 15 Jun 2023 10:30:00 +0000",
                            },
                        ]
                    },
                }
            ],
        }

        self.mock_api_client.get_thread.return_value = mock_thread
        self.service.parser.extract_body = Mock(return_value="Test body")

        expected_uri = PageURI(
            root="test-root", type="email_thread", id="thread456", version=1
        )
        result = await self.service.create_thread_page(expected_uri)

        assert isinstance(result, EmailThreadPage)
        assert result.thread_id == "thread456"
        assert result.subject == "Test Subject"
        assert len(result.emails) == 1
        assert result.emails[0].sender == "sender@example.com"
        assert result.emails[0].recipients == ["recipient@example.com"]
        assert result.emails[0].body == "Test body"
        assert result.emails[0].uri == PageURI(
            root="test-root", type="email", id="msg1", version=1
        )

    @pytest.mark.asyncio
    async def test_create_email_page_minimal_headers(self):
        """Test email page creation with minimal headers."""
        # Setup mock message response with minimal headers
        mock_message = {
            "id": "msg123",
            "threadId": "thread456",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Date", "value": "Thu, 15 Jun 2023 10:30:00 +0000"},
                ]
            },
        }

        self.mock_api_client.get_message.return_value = mock_message
        self.service.parser.extract_body = Mock(return_value="Test body")

        expected_uri = PageURI(root="test-root", type="email", id="msg123", version=1)
        result = await self.service.create_email_page(expected_uri)

        assert isinstance(result, EmailPage)
        assert result.message_id == "msg123"
        assert result.thread_id == "thread456"
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient@example.com"]
        assert result.body == "Test body"
        assert result.uri == PageURI(
            root="test-root", type="email", id="msg123", version=1
        )

    @pytest.mark.asyncio
    async def test_create_email_page_missing_thread_id(self):
        """Test email page creation with missing thread ID."""
        # Setup mock message response with missing thread ID
        mock_message = {
            "id": "msg123",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Date", "value": "Thu, 15 Jun 2023 10:30:00 +0000"},
                ]
            },
        }

        self.mock_api_client.get_message.return_value = mock_message
        self.service.parser.extract_body = Mock(return_value="Test body")

        expected_uri = PageURI(root="test-root", type="email", id="msg123", version=1)
        result = await self.service.create_email_page(expected_uri)

        assert isinstance(result, EmailPage)
        assert result.message_id == "msg123"
        assert result.thread_id == "msg123"  # Should use message ID as thread ID
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient@example.com"]
        assert result.body == "Test body"
        assert result.uri == PageURI(
            root="test-root", type="email", id="msg123", version=1
        )

    @pytest.mark.asyncio
    async def test_search_emails_basic(self):
        """Test basic email search functionality."""
        # Setup mock search response
        mock_messages = [
            {"id": "msg1", "threadId": "thread1"},
            {"id": "msg2", "threadId": "thread2"},
        ]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)

        # Call search_emails
        uris, next_token = await self.service.search_emails("test query")

        # Verify API client call
        self.mock_api_client.search_messages.assert_called_once_with(
            "test query", page_token=None, page_size=20
        )

        # Verify results
        assert len(uris) == 2
        assert all(isinstance(uri, PageURI) for uri in uris)
        assert uris[0].id == "msg1"
        assert uris[1].id == "msg2"
        assert next_token is None

    @pytest.mark.asyncio
    async def test_search_emails_with_inbox_filter(self):
        """Test search passes query through to API client."""
        self.mock_api_client.search_messages.return_value = ([], None)

        await self.service.search_emails("in:sent test query")

        self.mock_api_client.search_messages.assert_called_once_with(
            "in:sent test query", page_token=None, page_size=20
        )

    @pytest.mark.asyncio
    async def test_search_emails_with_pagination(self):
        """Test search with pagination parameters."""
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)

        uris, next_token = await self.service.search_emails(
            "test", page_token="prev_token", page_size=10
        )

        self.mock_api_client.search_messages.assert_called_once_with(
            "test", page_token="prev_token", page_size=10
        )

        assert len(uris) == 1
        assert next_token is None

    @pytest.mark.asyncio
    async def test_search_emails_empty_query(self):
        """Test search with empty query."""
        self.mock_api_client.search_messages.return_value = ([], None)

        await self.service.search_emails("")

        self.mock_api_client.search_messages.assert_called_once_with(
            "", page_token=None, page_size=20
        )

    @pytest.mark.asyncio
    async def test_search_emails_api_error(self):
        """Test search_emails handles API errors."""
        self.mock_api_client.search_messages.side_effect = Exception("Search API Error")

        with pytest.raises(Exception, match="Search API Error"):
            await self.service.search_emails("test query")

    @pytest.mark.asyncio
    async def test_search_emails_no_results(self):
        """Test search with no results."""
        self.mock_api_client.search_messages.return_value = ([], None)

        uris, next_token = await self.service.search_emails("no results query")

        assert uris == []
        assert next_token is None

    def test_name_property(self):
        """Test name property."""
        assert self.service.name == "email"


class TestEmailPage:
    """Test EmailPage functionality."""

    def test_email_page_creation(self):
        """Test creating an EmailPage with all fields."""
        uri = PageURI(root="test", type="email", id="msg123", version=1)
        email_time = datetime(2023, 6, 15, 10, 30, 0)

        email_page = EmailPage(
            uri=uri,
            message_id="msg123",
            thread_id="thread456",
            subject="Test Email Subject",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            cc_list=["cc@example.com"],
            body="Test email body content",
            time=email_time,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread456",
        )

        assert email_page.uri == uri
        assert email_page.message_id == "msg123"
        assert email_page.thread_id == "thread456"
        assert email_page.subject == "Test Email Subject"
        assert email_page.sender == "sender@example.com"
        assert email_page.recipients == ["recipient@example.com"]
        assert email_page.cc_list == ["cc@example.com"]
        assert email_page.body == "Test email body content"
        assert email_page.time == email_time
        assert (
            email_page.permalink == "https://mail.google.com/mail/u/0/#inbox/thread456"
        )

    def test_email_page_minimal_creation(self):
        """Test creating an EmailPage with minimal required fields."""
        uri = PageURI(root="test", type="email", id="msg123", version=1)

        email_page = EmailPage(
            uri=uri,
            message_id="msg123",
            thread_id="thread456",
            subject="",
            sender="",
            recipients=[],
            body="",
            time=datetime.now(),
            permalink="",
        )

        assert email_page.uri == uri
        assert email_page.message_id == "msg123"
        assert email_page.thread_id == "thread456"
        assert email_page.cc_list == []  # Should default to empty list

    def test_email_page_thread_uri_property(self):
        """Test that EmailPage.thread_uri property returns correct PageURI."""
        uri = PageURI(root="test-root", type="email", id="msg123", version=2)
        email_time = datetime(2023, 6, 15, 10, 30, 45)

        email_page = EmailPage(
            uri=uri,
            message_id="msg123",
            thread_id="thread456",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=[],
            body="Test body",
            time=email_time,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread456",
        )

        thread_uri = email_page.thread_uri

        assert isinstance(thread_uri, PageURI)
        assert thread_uri.root == "test-root"
        assert thread_uri.type == "email_thread"
        assert thread_uri.id == "thread456"
        assert thread_uri.version == 2  # Should match the email's version

    def test_email_page_thread_uri_with_different_root(self):
        """Test thread_uri with different root values."""
        uri = PageURI(root="production", type="email", id="msg789", version=1)

        email_page = EmailPage(
            uri=uri,
            message_id="msg789",
            thread_id="thread123",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=[],
            body="Test body",
            time=datetime.now(),
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        thread_uri = email_page.thread_uri

        assert thread_uri.root == "production"
        assert thread_uri.type == "email_thread"
        assert thread_uri.id == "thread123"
        assert thread_uri.version == 1


class TestEmailSummary:
    """Test EmailSummary functionality."""

    def test_email_summary_creation(self):
        """Test creating an EmailSummary with all fields."""
        uri = PageURI(root="test", type="email", id="msg123", version=1)
        email_time = datetime(2023, 6, 15, 10, 30, 0)

        email_summary = EmailSummary(
            uri=uri,
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            cc_list=["cc@example.com"],
            body="Test email body content",
            time=email_time,
        )

        assert email_summary.uri == uri
        assert email_summary.sender == "sender@example.com"
        assert email_summary.recipients == ["recipient@example.com"]
        assert email_summary.cc_list == ["cc@example.com"]
        assert email_summary.body == "Test email body content"
        assert email_summary.time == email_time

    def test_email_summary_minimal_creation(self):
        """Test creating an EmailSummary with minimal fields."""
        uri = PageURI(root="test", type="email", id="msg123", version=1)

        email_summary = EmailSummary(
            uri=uri,
            sender="",
            recipients=[],
            body="",
            time=datetime.now(),
        )

        assert email_summary.uri == uri
        assert email_summary.sender == ""
        assert email_summary.recipients == []
        assert email_summary.cc_list == []  # Should default to empty list
        assert email_summary.body == ""


class TestEmailThreadPage:
    """Test EmailThreadPage functionality."""

    def test_email_thread_page_creation(self):
        """Test creating an EmailThreadPage with all fields."""
        uri = PageURI(root="test", type="email_thread", id="thread456", version=1)
        email_summaries = [
            EmailSummary(
                uri=PageURI(root="test", type="email", id="msg1", version=1),
                sender="alice@example.com",
                recipients=["bob@example.com"],
                body="First message",
                time=datetime(2023, 6, 15, 10, 0, 0),
            ),
            EmailSummary(
                uri=PageURI(root="test", type="email", id="msg2", version=1),
                sender="bob@example.com",
                recipients=["alice@example.com"],
                body="Second message",
                time=datetime(2023, 6, 15, 11, 0, 0),
            ),
        ]

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread456",
            subject="Thread Subject",
            emails=email_summaries,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread456",
        )

        assert thread_page.uri == uri
        assert thread_page.thread_id == "thread456"
        assert thread_page.subject == "Thread Subject"
        assert thread_page.emails == email_summaries
        assert (
            thread_page.permalink == "https://mail.google.com/mail/u/0/#inbox/thread456"
        )

    def test_email_thread_page_minimal_creation(self):
        """Test creating an EmailThreadPage with minimal fields."""
        uri = PageURI(root="test", type="email_thread", id="thread456", version=1)

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread456",
            subject="",
            emails=[],
            permalink="",
        )

        assert thread_page.uri == uri
        assert thread_page.thread_id == "thread456"
        assert thread_page.subject == ""
        assert thread_page.emails == []

    def test_email_thread_page_with_many_emails(self):
        """Test EmailThreadPage with a large number of emails."""
        uri = PageURI(root="test", type="email_thread", id="thread789", version=1)

        # Create 10 email summaries
        email_summaries = [
            EmailSummary(
                uri=PageURI(root="test", type="email", id=f"msg{i}", version=1),
                sender=f"user{i}@example.com",
                recipients=["recipient@example.com"],
                body=f"Message {i} content",
                time=datetime(2023, 6, 15, 10, i, 0),
            )
            for i in range(1, 11)
        ]

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread789",
            subject="Long Thread Subject",
            emails=email_summaries,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread789",
        )

        assert len(thread_page.emails) == 10
        assert all(email.uri.type == "email" for email in thread_page.emails)
        assert all(email.uri.root == "test" for email in thread_page.emails)

    def test_email_thread_page_consistency(self):
        """Test that EmailThreadPage works with different numbers of emails."""
        uri = PageURI(root="test", type="email_thread", id="thread456", version=1)
        email_summaries = [
            EmailSummary(
                uri=PageURI(root="test", type="email", id="msg1", version=1),
                sender="sender1@example.com",
                recipients=["recipient@example.com"],
                body="First message",
                time=datetime.now(),
            ),
            EmailSummary(
                uri=PageURI(root="test", type="email", id="msg2", version=1),
                sender="sender2@example.com",
                recipients=["recipient@example.com"],
                body="Second message",
                time=datetime.now(),
            ),
        ]

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread456",
            subject="Consistency Test",
            emails=email_summaries,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread456",
        )

        assert len(thread_page.emails) == 2


class TestEmailThreadPageIntegration:
    """Integration tests for EmailThreadPage with GmailService."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing global context first
        clear_global_context()

        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}

        # Mock create_page_uri to return predictable URIs
        def mock_create_page_uri(page_type, type_path, id, version=None):
            return PageURI(root="test-root", type=type_path, id=id, version=1)

        self.mock_context.create_page_uri = mock_create_page_uri

        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service
        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()
        self.mock_api_client.get_thread = AsyncMock()
        self.mock_api_client.get_message = AsyncMock()
        self.service = GmailService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    @pytest.mark.asyncio
    async def test_email_page_thread_uri_matches_thread_page_uri(self):
        """Test that EmailPage.thread_uri matches EmailThreadPage.uri for the same thread."""
        # Setup mock message response
        mock_message = {
            "id": "msg123",
            "threadId": "thread456",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Date", "value": "Thu, 15 Jun 2023 10:30:00 +0000"},
                ]
            },
        }

        # Setup mock thread response
        mock_thread = {
            "id": "thread456",
            "messages": [mock_message],
        }

        self.mock_api_client.get_message.return_value = mock_message
        self.mock_api_client.get_thread.return_value = mock_thread
        self.service.parser.extract_body = Mock(return_value="Test body")

        # Create email page and thread page
        email_uri = PageURI(root="test-root", type="email", id="msg123", version=1)
        thread_uri = PageURI(
            root="test-root", type="email_thread", id="thread456", version=1
        )
        email_page = await self.service.create_email_page(email_uri)
        thread_page = await self.service.create_thread_page(thread_uri)

        # Verify that EmailPage.thread_uri matches EmailThreadPage.uri
        assert email_page.thread_uri == thread_page.uri
        assert email_page.thread_uri.root == thread_page.uri.root
        assert email_page.thread_uri.type == thread_page.uri.type
        assert email_page.thread_uri.id == thread_page.uri.id
        assert email_page.thread_uri.version == thread_page.uri.version

    @pytest.mark.asyncio
    async def test_thread_page_contains_email_summaries(self):
        """Test that email summaries in thread page can be used to access individual emails."""
        # This test verifies that the EmailSummary objects in a thread contain
        # valid URIs that can be used to fetch the corresponding EmailPage objects

        # Setup mock thread with multiple messages
        mock_thread = {
            "id": "thread456",
            "messages": [
                {
                    "id": "msg1",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Original Subject"},
                            {"name": "From", "value": "alice@example.com"},
                            {"name": "To", "value": "bob@example.com"},
                            {
                                "name": "Date",
                                "value": "Mon, 10 Jun 2023 09:00:00 +0000",
                            },
                        ]
                    },
                },
                {
                    "id": "msg2",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Re: Original Subject"},
                            {"name": "From", "value": "bob@example.com"},
                            {"name": "To", "value": "alice@example.com"},
                            {
                                "name": "Date",
                                "value": "Mon, 10 Jun 2023 10:00:00 +0000",
                            },
                        ]
                    },
                },
            ],
        }

        self.mock_api_client.get_thread.return_value = mock_thread
        self.service.parser.extract_body = Mock(return_value="Email body content")

        # Create thread page
        thread_uri = PageURI(
            root="test-root", type="email_thread", id="thread456", version=1
        )
        thread_page = await self.service.create_thread_page(thread_uri)

        # Verify email summaries have correct URIs
        assert len(thread_page.emails) == 2
        assert thread_page.emails[0].uri.id == "msg1"
        assert thread_page.emails[1].uri.id == "msg2"

        # Verify URI structure
        for email_summary in thread_page.emails:
            assert email_summary.uri.root == "test-root"
            assert email_summary.uri.type == "email"
            assert email_summary.uri.version == 1
            assert email_summary.body == "Email body content"
            assert isinstance(email_summary.time, datetime)


class TestGmailToolkit:
    """Test suite for GmailService toolkit methods (now integrated into GmailService)."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing global context first
        clear_global_context()

        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_context.get_page = Mock()
        self.mock_context.get_pages = AsyncMock()
        # Ensure create_page_uri is an AsyncMock for toolkit tests
        self.mock_context.create_page_uri = AsyncMock(
            side_effect=lambda page_type, type_path, id, version=None: PageURI(
                root="test-root", type=type_path, id=id, version=version or 1
            )
        )
        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient and service
        self.mock_api_client = AsyncMock()
        self.mock_api_client.search_messages = AsyncMock()
        self.service = GmailService(self.mock_api_client)
        # Since GmailService now inherits from RetrieverToolkit, use service directly
        self.toolkit = self.service

        # The toolkit will use the global context automatically
        # Don't try to override the context property directly

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    @pytest.mark.asyncio
    async def test_search_emails_from_person_basic(self):
        """Test search_emails_from_person without keywords."""
        mock_messages = [{"id": "msg1"}, {"id": "msg2"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage), AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        with patch(
            "pragweb.google_api.utils.resolve_person_identifier",
            return_value="test@example.com",
        ):
            result = await self.toolkit.search_emails_from_person("test@example.com")
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert query == 'from:"test@example.com"'
        assert len(result) == 2
        assert all(isinstance(page, EmailPage) for page in result)

    @pytest.mark.asyncio
    async def test_search_emails_from_person_with_keywords(self):
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        with patch(
            "pragweb.google_api.utils.resolve_person_identifier",
            return_value="test@example.com",
        ):
            result = await self.toolkit.search_emails_from_person(
                "test@example.com", content="urgent project"
            )
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert query == 'from:"test@example.com" urgent project'
        assert len(result) == 1
        assert isinstance(result[0], EmailPage)

    @pytest.mark.asyncio
    async def test_search_emails_to_person_basic(self):
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        with patch(
            "pragweb.google_api.utils.resolve_person_identifier",
            return_value="recipient@example.com",
        ):
            result = await self.toolkit.search_emails_to_person("recipient@example.com")
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert query == 'to:"recipient@example.com" OR cc:"recipient@example.com"'
        assert len(result) == 1
        assert isinstance(result[0], EmailPage)

    @pytest.mark.asyncio
    async def test_search_emails_to_person_with_keywords(self):
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        with patch(
            "pragweb.google_api.utils.resolve_person_identifier",
            return_value="recipient@example.com",
        ):
            result = await self.toolkit.search_emails_to_person(
                "recipient@example.com", content="meeting notes"
            )
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert (
            query
            == 'to:"recipient@example.com" OR cc:"recipient@example.com" meeting notes'
        )
        assert len(result) == 1
        assert isinstance(result[0], EmailPage)

    @pytest.mark.asyncio
    async def test_search_emails_by_content(self):
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        result = await self.toolkit.search_emails_by_content("important announcement")
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert query == "important announcement"
        assert len(result) == 1
        assert isinstance(result[0], EmailPage)

    @pytest.mark.asyncio
    async def test_get_recent_emails_basic(self):
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        result = await self.toolkit.get_recent_emails(days=7)
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert query == "newer_than:7d"
        assert len(result) == 1
        assert isinstance(result[0], EmailPage)

    @pytest.mark.asyncio
    async def test_get_recent_emails_with_keywords(self):
        mock_messages = [{"id": "msg1"}]
        self.mock_api_client.search_messages.return_value = (mock_messages, None)
        mock_pages = [AsyncMock(spec=EmailPage)]
        self.mock_context.get_page.side_effect = mock_pages
        self.mock_context.get_pages.return_value = mock_pages
        result = await self.toolkit.get_recent_emails(days=3)
        args, kwargs = self.mock_api_client.search_messages.call_args
        query = args[0]
        assert query == "newer_than:3d"
        assert len(result) == 1
        assert isinstance(result[0], EmailPage)
