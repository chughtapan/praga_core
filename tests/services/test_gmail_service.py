"""Tests for Gmail integration with the new EmailService architecture."""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import EmailPage, EmailSummary, EmailThreadPage
from pragweb.services import EmailService


class MockGmailClient:
    """Mock Gmail client for testing."""

    def __init__(self):
        self.messages = {}
        self.threads = {}

    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get message by ID."""
        return self.messages.get(message_id, {})

    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get thread by ID."""
        return self.threads.get(thread_id, {})

    async def search_messages(
        self, query: str, max_results: int = 10, page_token: str = None
    ) -> Dict[str, Any]:
        """Search messages."""
        return {"messages": [], "nextPageToken": None}

    def parse_message_to_email_page(
        self, message_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailPage:
        """Parse message data to EmailPage."""
        headers = {
            h["name"]: h["value"]
            for h in message_data.get("payload", {}).get("headers", [])
        }

        # Parse recipients from To header
        recipients = []
        if "To" in headers:
            recipients = [email.strip() for email in headers["To"].split(",")]

        # Parse CC list
        cc_list = []
        if "Cc" in headers:
            cc_list = [email.strip() for email in headers["Cc"].split(",")]

        # Parse date
        email_time = datetime.now(timezone.utc)
        if "Date" in headers:
            try:
                from email.utils import parsedate_to_datetime

                email_time = parsedate_to_datetime(headers["Date"])
            except Exception:
                pass

        return EmailPage(
            uri=page_uri,
            thread_id=message_data.get("threadId", message_data.get("id", "test_msg")),
            subject=headers.get("Subject", ""),
            sender=headers.get("From", ""),
            recipients=recipients,
            cc_list=cc_list,
            body="Test email body content",
            time=email_time,
            permalink=f"https://mail.google.com/mail/u/0/#inbox/{message_data.get('threadId', message_data.get('id', 'test_msg'))}",
        )

    def parse_thread_to_thread_page(
        self, thread_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailThreadPage:
        """Parse thread data to EmailThreadPage."""
        messages = thread_data.get("messages", [])
        if not messages:
            raise ValueError(
                f"Thread {thread_data.get('id', 'unknown')} contains no messages"
            )

        # Get subject from first message
        first_message = messages[0]
        headers = {
            h["name"]: h["value"]
            for h in first_message.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "")

        # Create email summaries
        email_summaries = []
        for msg in messages:
            msg_headers = {
                h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
            }

            # Parse recipients
            recipients = []
            if "To" in msg_headers:
                recipients = [email.strip() for email in msg_headers["To"].split(",")]

            # Parse CC list
            cc_list = []
            if "Cc" in msg_headers:
                cc_list = [email.strip() for email in msg_headers["Cc"].split(",")]

            # Parse date
            email_time = datetime.now(timezone.utc)
            if "Date" in msg_headers:
                try:
                    from email.utils import parsedate_to_datetime

                    email_time = parsedate_to_datetime(msg_headers["Date"])
                except Exception:
                    pass

            email_uri = PageURI(
                root=page_uri.root,
                type="gmail_email",
                id=msg["id"],
                version=page_uri.version,
            )

            email_summary = EmailSummary(
                uri=email_uri,
                sender=msg_headers.get("From", ""),
                recipients=recipients,
                cc_list=cc_list,
                body="Email body content",
                time=email_time,
            )
            email_summaries.append(email_summary)

        # Calculate participants and timing info
        participants = list({email.sender for email in email_summaries})
        last_message_time = max(
            (email.time for email in email_summaries),
            default=datetime.now(timezone.utc),
        )
        message_count = len(email_summaries)

        return EmailThreadPage(
            uri=page_uri,
            thread_id=thread_data.get("id", "test_thread"),
            subject=subject,
            emails=email_summaries,
            participants=participants,
            last_message_time=last_message_time,
            message_count=message_count,
            permalink=f"https://mail.google.com/mail/u/0/#inbox/{thread_data.get('id', 'test_thread')}",
        )


class MockGoogleProviderClient(BaseProviderClient):
    """Mock Google provider client."""

    def __init__(self):
        super().__init__(Mock())
        self._email_client = MockGmailClient()

    @property
    def email_client(self):
        return self._email_client

    @property
    def calendar_client(self):
        return Mock()

    @property
    def people_client(self):
        return Mock()

    @property
    def documents_client(self):
        return Mock()

    async def test_connection(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "google"


class TestEmailService:
    """Test suite for EmailService with Gmail provider."""

    @pytest.fixture
    async def service(self):
        """Create service with test context and mock providers."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create service
        service = EmailService(providers)

        yield service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.name == "gmail"
        assert len(service.providers) == 1
        assert "google" in service.providers

    @pytest.mark.asyncio
    async def test_service_registration(self, service):
        """Test that service registers with context."""
        context = service.context
        registered_service = context.get_service("gmail")
        assert registered_service is service

    @pytest.mark.asyncio
    async def test_create_email_page_success(self, service):
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

        service.providers["google"].email_client.get_message = AsyncMock(
            return_value=mock_message
        )

        # Create page URI with new format
        page_uri = PageURI(root="test://example", type="gmail_email", id="msg123")

        # Test page creation
        result = await service.create_email_page(page_uri)

        # Verify API client call
        service.providers["google"].email_client.get_message.assert_called_once_with(
            "msg123"
        )

        # Verify result
        assert isinstance(result, EmailPage)
        assert result.uri == page_uri
        assert result.uri.id == "msg123"
        assert result.thread_id == "thread456"
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient1@example.com", "recipient2@example.com"]
        assert result.cc_list == ["cc1@example.com", "cc2@example.com"]
        assert result.permalink == "https://mail.google.com/mail/u/0/#inbox/thread456"

    @pytest.mark.asyncio
    async def test_email_page_thread_uri_property(self, service):
        """Test that EmailPage has thread_uri property that links to thread page."""
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

        service.providers["google"].email_client.get_message = AsyncMock(
            return_value=mock_message
        )

        # Create email page
        page_uri = PageURI(root="test://example", type="gmail_email", id="msg123")
        email_page = await service.create_email_page(page_uri)

        # Test thread_uri property
        thread_uri = email_page.thread_uri
        assert isinstance(thread_uri, PageURI)
        assert thread_uri.root == "test://example"
        assert thread_uri.type == "gmail_thread"
        assert thread_uri.id == "thread456"

    @pytest.mark.asyncio
    async def test_create_thread_page_success(self, service):
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

        service.providers["google"].email_client.get_thread = AsyncMock(
            return_value=mock_thread
        )

        # Call create_thread_page
        page_uri = PageURI(root="test://example", type="gmail_thread", id="thread456")
        result = await service.create_thread_page(page_uri)

        # Verify API client call
        service.providers["google"].email_client.get_thread.assert_called_once_with(
            "thread456"
        )

        # Verify result
        assert isinstance(result, EmailThreadPage)
        assert result.uri == page_uri
        assert result.thread_id == "thread456"
        assert result.subject == "Original Subject"  # Should be from first message
        assert len(result.emails) == 3

        # Verify email summaries
        assert all(hasattr(email, "uri") for email in result.emails)
        assert all(hasattr(email, "sender") for email in result.emails)
        assert all(hasattr(email, "body") for email in result.emails)

        # Check first email summary
        first_email = result.emails[0]
        assert first_email.uri.type == "gmail_email"
        assert first_email.uri.id == "msg1"
        assert first_email.sender == "alice@example.com"
        assert first_email.recipients == ["bob@example.com"]

        # Verify permalink
        assert result.permalink == "https://mail.google.com/mail/u/0/#inbox/thread456"

    @pytest.mark.asyncio
    async def test_create_thread_page_api_error(self, service):
        """Test create_thread_page handles API errors."""
        service.providers["google"].email_client.get_thread = AsyncMock(
            side_effect=Exception("API Error")
        )

        with pytest.raises(
            ValueError, match="Failed to fetch thread thread456: API Error"
        ):
            page_uri = PageURI(
                root="test://example", type="gmail_thread", id="thread456"
            )
            await service.create_thread_page(page_uri)

    @pytest.mark.asyncio
    async def test_create_thread_page_empty_thread(self, service):
        """Test create_thread_page handles thread with no messages."""
        mock_thread = {"id": "thread456", "messages": []}
        service.providers["google"].email_client.get_thread = AsyncMock(
            return_value=mock_thread
        )

        with pytest.raises(ValueError, match="Thread thread456 contains no messages"):
            page_uri = PageURI(
                root="test://example", type="gmail_thread", id="thread456"
            )
            await service.create_thread_page(page_uri)

    @pytest.mark.asyncio
    async def test_create_thread_page_minimal_headers(self, service):
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

        service.providers["google"].email_client.get_thread = AsyncMock(
            return_value=mock_thread
        )

        page_uri = PageURI(root="test://example", type="gmail_thread", id="thread456")
        result = await service.create_thread_page(page_uri)

        assert isinstance(result, EmailThreadPage)
        assert result.thread_id == "thread456"
        assert result.subject == "Test Subject"
        assert len(result.emails) == 1
        assert result.emails[0].sender == "sender@example.com"
        assert result.emails[0].recipients == ["recipient@example.com"]
        assert result.emails[0].uri.type == "gmail_email"
        assert result.emails[0].uri.id == "msg1"

    @pytest.mark.asyncio
    async def test_create_email_page_minimal_headers(self, service):
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

        service.providers["google"].email_client.get_message = AsyncMock(
            return_value=mock_message
        )

        page_uri = PageURI(root="test://example", type="gmail_email", id="msg123")
        result = await service.create_email_page(page_uri)

        assert isinstance(result, EmailPage)
        assert result.uri.id == "msg123"
        assert result.thread_id == "thread456"
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient@example.com"]
        assert result.uri == page_uri

    @pytest.mark.asyncio
    async def test_create_email_page_missing_thread_id(self, service):
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

        service.providers["google"].email_client.get_message = AsyncMock(
            return_value=mock_message
        )

        page_uri = PageURI(root="test://example", type="gmail_email", id="msg123")
        result = await service.create_email_page(page_uri)

        assert isinstance(result, EmailPage)
        assert result.uri.id == "msg123"
        assert result.thread_id == "msg123"  # Should use message ID as thread ID
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient@example.com"]
        assert result.uri == page_uri

    @pytest.mark.asyncio
    async def test_search_emails_basic(self, service):
        """Test basic email search functionality."""
        # Setup mock search response
        mock_messages = [
            {"id": "msg1", "threadId": "thread1"},
            {"id": "msg2", "threadId": "thread2"},
        ]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        # Call _search_emails with Gmail's expected query format
        result = await service._search_emails(content_query="test query")

        # Verify API client call - Gmail adds "in:inbox" prefix
        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox test query", page_token=None, max_results=10
        )

        # Verify results
        assert len(result.results) == 2
        assert all(isinstance(page, EmailPage) for page in result.results)
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_search_emails_with_inbox_filter(self, service):
        """Test search passes query through to API client."""
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": [], "nextPageToken": None}
        )

        await service._search_emails(metadata_query="in:sent test query")

        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox in:sent test query", page_token=None, max_results=10
        )

    @pytest.mark.asyncio
    async def test_search_emails_with_pagination(self, service):
        """Test search with pagination parameters."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        result = await service._search_emails(
            content_query="test", cursor="prev_token", page_size=10
        )

        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox test", page_token="prev_token", max_results=10
        )

        assert len(result.results) == 1
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_search_emails_empty_query(self, service):
        """Test search with empty query."""
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": [], "nextPageToken": None}
        )

        await service._search_emails()

        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox", page_token=None, max_results=10
        )

    @pytest.mark.asyncio
    async def test_search_emails_api_error(self, service):
        """Test search_emails propagates API errors."""
        service.providers["google"].email_client.search_messages = AsyncMock(
            side_effect=Exception("Search API Error")
        )

        # The service should propagate exceptions to the caller
        with pytest.raises(Exception, match="Search API Error"):
            await service._search_emails(content_query="test query")

    @pytest.mark.asyncio
    async def test_search_emails_no_results(self, service):
        """Test search with no results."""
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": [], "nextPageToken": None}
        )

        result = await service._search_emails(content_query="no results query")

        assert result.results == []
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_parse_email_uri(self, service):
        """Test parsing email URI."""
        page_uri = PageURI(root="test://example", type="gmail_email", id="msg123")

        # Since parse methods are removed, test direct access to page_uri.id
        message_id = page_uri.id

        assert message_id == "msg123"

    @pytest.mark.asyncio
    async def test_parse_thread_uri(self, service):
        """Test parsing thread URI."""
        page_uri = PageURI(root="test://example", type="gmail_thread", id="thread456")

        # Since parse methods are removed, test direct access to page_uri.id
        thread_id = page_uri.id

        assert thread_id == "thread456"

    @pytest.mark.asyncio
    async def test_empty_providers(self, service):
        """Test handling of service with no providers."""
        # Clear providers to simulate error
        service.providers = {}

        page_uri = PageURI(root="test://example", type="gmail_email", id="msg123")

        with pytest.raises(ValueError, match="No provider available"):
            await service.create_email_page(page_uri)

    @pytest.mark.asyncio
    async def test_search_with_no_results(self, service):
        """Test search when no emails are found."""
        # Mock empty results
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": [], "nextPageToken": None}
        )

        result = await service._search_emails(content_query="test")

        assert len(result.results) == 0
        assert result.next_cursor is None


class TestEmailPage:
    """Test EmailPage functionality."""

    def test_email_page_creation(self):
        """Test creating an EmailPage with all fields."""
        uri = PageURI(root="test", type="gmail_email", id="msg123", version=1)
        email_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

        email_page = EmailPage(
            uri=uri,
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
        assert email_page.uri.id == "msg123"
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
        uri = PageURI(root="test", type="gmail_email", id="msg123", version=1)

        email_page = EmailPage(
            uri=uri,
            thread_id="thread456",
            subject="",
            sender="",
            recipients=[],
            body="",
            time=datetime.now(timezone.utc),
            permalink="",
        )

        assert email_page.uri == uri
        assert email_page.uri.id == "msg123"
        assert email_page.thread_id == "thread456"
        assert email_page.cc_list == []  # Should default to empty list

    def test_email_page_thread_uri_property(self):
        """Test that EmailPage.thread_uri property returns correct PageURI."""
        uri = PageURI(root="test-root", type="gmail_email", id="msg123", version=2)
        email_time = datetime(2023, 6, 15, 10, 30, 45, tzinfo=timezone.utc)

        email_page = EmailPage(
            uri=uri,
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
        assert thread_uri.type == "gmail_thread"
        assert thread_uri.id == "thread456"
        assert thread_uri.version == 2  # Should match the email's version

    def test_email_page_thread_uri_with_different_root(self):
        """Test thread_uri with different root values."""
        uri = PageURI(root="production", type="gmail_email", id="msg789", version=1)

        email_page = EmailPage(
            uri=uri,
            thread_id="thread123",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=[],
            body="Test body",
            time=datetime.now(timezone.utc),
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        thread_uri = email_page.thread_uri

        assert thread_uri.root == "production"
        assert thread_uri.type == "gmail_thread"
        assert thread_uri.id == "thread123"
        assert thread_uri.version == 1


class TestEmailSummary:
    """Test EmailSummary functionality."""

    def test_email_summary_creation(self):
        """Test creating an EmailSummary with all fields."""
        uri = PageURI(root="test", type="gmail_email", id="msg123", version=1)
        email_time = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)

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
        uri = PageURI(root="test", type="gmail_email", id="msg123", version=1)

        email_summary = EmailSummary(
            uri=uri,
            sender="",
            recipients=[],
            body="",
            time=datetime.now(timezone.utc),
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
        uri = PageURI(root="test", type="gmail_thread", id="thread456", version=1)
        email_summaries = [
            EmailSummary(
                uri=PageURI(root="test", type="gmail_email", id="msg1", version=1),
                sender="alice@example.com",
                recipients=["bob@example.com"],
                body="First message",
                time=datetime(2023, 6, 15, 10, 0, 0, tzinfo=timezone.utc),
            ),
            EmailSummary(
                uri=PageURI(root="test", type="gmail_email", id="msg2", version=1),
                sender="bob@example.com",
                recipients=["alice@example.com"],
                body="Second message",
                time=datetime(2023, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
            ),
        ]

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread456",
            subject="Thread Subject",
            emails=email_summaries,
            participants=["alice@example.com", "bob@example.com"],
            last_message_time=datetime(2023, 6, 15, 11, 0, 0, tzinfo=timezone.utc),
            message_count=2,
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
        uri = PageURI(root="test", type="gmail_thread", id="thread456", version=1)

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread456",
            subject="",
            emails=[],
            participants=[],
            last_message_time=datetime.now(timezone.utc),
            message_count=0,
            permalink="",
        )

        assert thread_page.uri == uri
        assert thread_page.thread_id == "thread456"
        assert thread_page.subject == ""
        assert thread_page.emails == []

    def test_email_thread_page_with_many_emails(self):
        """Test EmailThreadPage with a large number of emails."""
        uri = PageURI(root="test", type="gmail_thread", id="thread789", version=1)

        # Create 10 email summaries
        email_summaries = [
            EmailSummary(
                uri=PageURI(root="test", type="gmail_email", id=f"msg{i}", version=1),
                sender=f"user{i}@example.com",
                recipients=["recipient@example.com"],
                body=f"Message {i} content",
                time=datetime(2023, 6, 15, 10, i, 0, tzinfo=timezone.utc),
            )
            for i in range(1, 11)
        ]

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread789",
            subject="Long Thread Subject",
            emails=email_summaries,
            participants=[f"user{i}@example.com" for i in range(1, 11)],
            last_message_time=datetime(2023, 6, 15, 10, 10, 0, tzinfo=timezone.utc),
            message_count=10,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread789",
        )

        assert len(thread_page.emails) == 10
        assert all(email.uri.type == "gmail_email" for email in thread_page.emails)
        assert all(email.uri.root == "test" for email in thread_page.emails)

    def test_email_thread_page_consistency(self):
        """Test that EmailThreadPage works with different numbers of emails."""
        uri = PageURI(root="test", type="gmail_thread", id="thread456", version=1)
        email_summaries = [
            EmailSummary(
                uri=PageURI(root="test", type="gmail_email", id="msg1", version=1),
                sender="sender1@example.com",
                recipients=["recipient@example.com"],
                body="First message",
                time=datetime.now(timezone.utc),
            ),
            EmailSummary(
                uri=PageURI(root="test", type="gmail_email", id="msg2", version=1),
                sender="sender2@example.com",
                recipients=["recipient@example.com"],
                body="Second message",
                time=datetime.now(timezone.utc),
            ),
        ]

        thread_page = EmailThreadPage(
            uri=uri,
            thread_id="thread456",
            subject="Consistency Test",
            emails=email_summaries,
            participants=["sender1@example.com", "sender2@example.com"],
            last_message_time=datetime.now(timezone.utc),
            message_count=2,
            permalink="https://mail.google.com/mail/u/0/#inbox/thread456",
        )

        assert len(thread_page.emails) == 2


class TestEmailThreadPageIntegration:
    """Integration tests for EmailThreadPage with EmailService."""

    @pytest.fixture
    async def service(self):
        """Create service with test context and mock providers."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create service
        service = EmailService(providers)

        yield service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_email_page_thread_uri_matches_thread_page_uri(self, service):
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

        service.providers["google"].email_client.get_message = AsyncMock(
            return_value=mock_message
        )
        service.providers["google"].email_client.get_thread = AsyncMock(
            return_value=mock_thread
        )

        # Create email page and thread page
        email_uri = PageURI(root="test://example", type="gmail_email", id="msg123")
        thread_uri = PageURI(root="test://example", type="gmail_thread", id="thread456")
        email_page = await service.create_email_page(email_uri)
        thread_page = await service.create_thread_page(thread_uri)

        # Verify that EmailPage.thread_uri matches EmailThreadPage.uri
        assert email_page.thread_uri.root == thread_page.uri.root
        assert email_page.thread_uri.type == thread_page.uri.type
        assert email_page.thread_uri.id == thread_page.uri.id

    @pytest.mark.asyncio
    async def test_thread_page_contains_email_summaries(self, service):
        """Test that email summaries in thread page can be used to access individual emails."""
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

        service.providers["google"].email_client.get_thread = AsyncMock(
            return_value=mock_thread
        )

        # Create thread page
        thread_uri = PageURI(root="test://example", type="gmail_thread", id="thread456")
        thread_page = await service.create_thread_page(thread_uri)

        # Verify email summaries have correct URIs
        assert len(thread_page.emails) == 2
        assert thread_page.emails[0].uri.id == "msg1"
        assert thread_page.emails[1].uri.id == "msg2"

        # Verify URI structure
        for email_summary in thread_page.emails:
            assert email_summary.uri.root == "test://example"
            assert email_summary.uri.type == "gmail_email"
            assert email_summary.body == "Email body content"
            assert isinstance(email_summary.time, datetime)


class TestGmailToolkit:
    """Test suite for EmailService toolkit methods with Gmail provider."""

    @pytest.fixture
    async def service(self):
        """Create service with test context and mock providers."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create service
        service = EmailService(providers)

        yield service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_search_emails_from_person_basic(self, service):
        """Test search_emails_from_person without keywords."""
        mock_messages = [{"id": "msg1"}, {"id": "msg2"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        with patch(
            "pragweb.utils.resolve_person_identifier",
            return_value="test@example.com",
        ):
            result = await service.search_emails_from_person("test@example.com")

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert query == 'in:inbox from:"test@example.com"'
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_search_emails_from_person_with_keywords(self, service):
        """Test search_emails_from_person with content keywords."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        with patch(
            "pragweb.utils.resolve_person_identifier",
            return_value="test@example.com",
        ):
            result = await service.search_emails_from_person(
                "test@example.com", content="urgent project"
            )

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert query == 'in:inbox from:"test@example.com" urgent project'
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_search_emails_to_person_basic(self, service):
        """Test search_emails_to_person without keywords."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        with patch(
            "pragweb.utils.resolve_person_identifier",
            return_value="recipient@example.com",
        ):
            result = await service.search_emails_to_person("recipient@example.com")

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert (
            query == 'in:inbox to:"recipient@example.com" OR cc:"recipient@example.com"'
        )
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_search_emails_to_person_with_keywords(self, service):
        """Test search_emails_to_person with content keywords."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        with patch(
            "pragweb.utils.resolve_person_identifier",
            return_value="recipient@example.com",
        ):
            result = await service.search_emails_to_person(
                "recipient@example.com", content="meeting notes"
            )

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert (
            query
            == 'in:inbox to:"recipient@example.com" OR cc:"recipient@example.com" meeting notes'
        )
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_search_emails_by_content(self, service):
        """Test search_emails_by_content."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        result = await service.search_emails_by_content("important announcement")

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert query == "in:inbox important announcement"
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_get_recent_emails_basic(self, service):
        """Test get_recent_emails without keywords."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        result = await service.get_recent_emails(days=7)

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert query == "in:inbox newer_than:7d"
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_get_recent_emails_with_keywords(self, service):
        """Test get_recent_emails with different day count."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        result = await service.get_recent_emails(days=3)

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert query == "in:inbox newer_than:3d"
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_get_unread_emails(self, service):
        """Test get_unread_emails."""
        mock_messages = [{"id": "msg1"}]
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": mock_messages, "nextPageToken": None}
        )

        result = await service.get_unread_emails()

        args, kwargs = service.providers[
            "google"
        ].email_client.search_messages.call_args
        query = kwargs["query"]
        assert query == "in:inbox is:unread"
        assert len(result.results) == 1
