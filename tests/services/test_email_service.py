"""Tests for the new EmailService orchestration layer."""

from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseEmailClient, BaseProviderClient
from pragweb.pages import EmailPage, EmailThreadPage
from pragweb.services import EmailService


class MockEmailClient(BaseEmailClient):
    """Mock email client for testing."""

    def __init__(self):
        self.messages = {}
        self.threads = {}

    async def get_message(self, message_id: str) -> Dict[str, Any]:
        return self.messages.get(message_id, {})

    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        return self.threads.get(thread_id, {})

    async def search_messages(
        self, query: str, max_results: int = 10, page_token: str = None
    ) -> Dict[str, Any]:
        return {"messages": [], "nextPageToken": None}

    async def send_message(
        self,
        to: list,
        subject: str,
        body: str,
        cc: list = None,
        bcc: list = None,
        thread_id: str = None,
    ) -> Dict[str, Any]:
        return {"id": "sent_message_123"}

    async def reply_to_message(
        self, message_id: str, body: str, reply_all: bool = False
    ) -> Dict[str, Any]:
        return {"id": "reply_123"}

    async def mark_as_read(self, message_id: str) -> bool:
        return True

    async def mark_as_unread(self, message_id: str) -> bool:
        return True

    def parse_message_to_email_page(
        self, message_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailPage:
        return EmailPage(
            uri=page_uri,
            thread_id=message_data.get("threadId", "test_thread"),
            subject=message_data.get("subject", "Test Subject"),
            sender=message_data.get("sender", "test@example.com"),
            recipients=message_data.get("recipients", ["recipient@example.com"]),
            cc_list=message_data.get("cc", []),
            bcc_list=message_data.get("bcc", []),
            body=message_data.get("body", "Test body"),
            time=datetime.now(),
            permalink="https://example.com/message",
        )

    def parse_thread_to_thread_page(
        self, thread_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailThreadPage:
        return EmailThreadPage(
            uri=page_uri,
            thread_id=thread_data.get("id", "test_thread"),
            subject=thread_data.get("subject", "Test Thread"),
            emails=[],
            permalink="https://example.com/thread",
            participants=["test@example.com"],
            labels=[],
            last_message_time=datetime.now(),
            message_count=1,
        )


class MockProviderClient(BaseProviderClient):
    """Mock provider client for testing."""

    def __init__(self, provider_name: str = "test"):
        self.provider_name = provider_name
        self._email_client = MockEmailClient()
        super().__init__(Mock())

    @property
    def email_client(self) -> MockEmailClient:
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
        return self.provider_name


class TestEmailService:
    """Test suite for EmailService."""

    @pytest.fixture
    async def service(self):
        """Create service with test context and mock providers."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider (single provider per service)
        google_provider = MockProviderClient("google")

        providers = {
            "google": google_provider,
        }

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
    async def test_search_emails_by_content(self, service):
        """Test searching for emails by content."""
        # Mock search results
        mock_results = {
            "messages": [
                {"id": "msg1"},
                {"id": "msg2"},
            ],
            "nextPageToken": "next_token",
        }

        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value=mock_results
        )

        # Test content search
        result = await service.search_emails_by_content("test query")

        assert isinstance(result.results, list)

        # Verify the search was called correctly with inbox prefix
        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox test query",
            page_token=None,
            max_results=10,
        )

    @pytest.mark.asyncio
    async def test_get_recent_emails(self, service):
        """Test getting recent emails."""
        # Mock search results
        mock_results = {"messages": [{"id": "recent1"}], "nextPageToken": None}

        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value=mock_results
        )

        # Test get recent
        result = await service.get_recent_emails(days=5)

        assert isinstance(result.results, list)

        # Verify the search was called with recent query and inbox prefix
        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox newer_than:5d",
            page_token=None,
            max_results=10,
        )

    @pytest.mark.asyncio
    async def test_get_unread_emails(self, service):
        """Test getting unread emails."""
        # Mock search results
        mock_results = {"messages": [{"id": "unread1"}], "nextPageToken": None}

        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value=mock_results
        )

        # Test get unread
        result = await service.get_unread_emails()

        assert isinstance(result.results, list)

        # Verify the search was called with unread query and inbox prefix
        service.providers[
            "google"
        ].email_client.search_messages.assert_called_once_with(
            query="in:inbox is:unread",
            page_token=None,
            max_results=10,
        )

    @pytest.mark.asyncio
    async def test_create_email_page(self, service):
        """Test creating an email page from URI."""
        # Set up mock message data
        message_data = {
            "id": "test_message",
            "threadId": "test_thread",
            "subject": "Test Email",
            "sender": "sender@example.com",
            "recipients": ["recipient@example.com"],
            "body": "Test body content",
        }

        service.providers["google"].email_client.get_message = AsyncMock(
            return_value=message_data
        )

        # Create page URI with new format
        page_uri = PageURI(root="test://example", type="gmail_email", id="test_message")

        # Test page creation
        email_page = await service.create_email_page(page_uri)

        assert isinstance(email_page, EmailPage)
        assert email_page.uri == page_uri
        assert email_page.subject == "Test Email"  # From mock data

        # Verify API was called
        service.providers["google"].email_client.get_message.assert_called_once_with(
            "test_message"
        )

    @pytest.mark.asyncio
    async def test_create_thread_page(self, service):
        """Test creating a thread page from URI."""
        # Set up mock thread data
        thread_data = {
            "id": "test_thread",
            "subject": "Test Thread",
            "messages": [],
        }

        service.providers["google"].email_client.get_thread = AsyncMock(
            return_value=thread_data
        )

        # Create page URI with new format
        page_uri = PageURI(root="test://example", type="gmail_thread", id="test_thread")

        # Test page creation
        thread_page = await service.create_thread_page(page_uri)

        assert isinstance(thread_page, EmailThreadPage)
        assert thread_page.uri == page_uri
        # Provider field was removed from pages

        # Verify API was called
        service.providers["google"].email_client.get_thread.assert_called_once_with(
            "test_thread"
        )

    @pytest.mark.asyncio
    async def test_parse_email_uri(self, service):
        """Test parsing email URI."""
        page_uri = PageURI(root="test://example", type="gmail_email", id="message123")

        # Since parse methods are removed, test direct access to page_uri.id
        message_id = page_uri.id

        assert message_id == "message123"

    @pytest.mark.asyncio
    async def test_parse_thread_uri(self, service):
        """Test parsing thread URI."""
        page_uri = PageURI(root="test://example", type="outlook_thread", id="thread456")

        # Since parse methods are removed, test direct access to page_uri.id
        thread_id = page_uri.id

        assert thread_id == "thread456"

    @pytest.mark.asyncio
    async def test_invalid_uri_format(self, service):
        """Test handling of invalid URI formats."""
        page_uri = PageURI(
            root="test://example", type="gmail_email", id="invalidformat"
        )

        # With new format, any ID is valid, so just test it returns the ID
        message_id = page_uri.id
        assert message_id == "invalidformat"

    @pytest.mark.asyncio
    async def test_unknown_provider(self, service):
        """Test handling of service with no providers."""
        with pytest.raises(
            ValueError, match="EmailService requires at least one provider"
        ):
            # Create a service with no providers to trigger the error
            EmailService({})

    @pytest.mark.asyncio
    async def test_search_with_no_results(self, service):
        """Test search when no messages are found."""
        # Mock empty results
        service.providers["google"].email_client.search_messages = AsyncMock(
            return_value={"messages": []}
        )

        result = await service.search_emails_by_content("test")

        assert len(result.results) == 0
        assert result.next_cursor is None
