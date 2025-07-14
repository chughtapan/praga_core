"""Tests for Microsoft email service functionality."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from praga_core.context import ServerContext
from praga_core.global_context import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.api_clients.microsoft.client import MicrosoftGraphClient
from pragweb.api_clients.microsoft.email import OutlookEmailClient
from pragweb.pages import EmailPage
from pragweb.services.email import EmailService


class TestMicrosoftEmailService:
    """Test Microsoft-specific email service functionality."""

    @pytest.fixture
    def mock_graph_client(self):
        """Create a mock Microsoft Graph client."""
        client = AsyncMock(spec=MicrosoftGraphClient)
        return client

    @pytest.fixture
    def mock_email_client(self, mock_graph_client):
        """Create a mock Outlook email client."""
        client = AsyncMock(spec=OutlookEmailClient)
        client.graph_client = mock_graph_client
        return client

    @pytest.fixture
    def mock_provider_client(self, mock_email_client):
        """Create a mock Microsoft provider client."""
        provider = AsyncMock(spec=BaseProviderClient)
        provider.email_client = mock_email_client
        return provider

    @pytest.fixture
    async def microsoft_service(self, mock_provider_client):
        """Create an EmailService instance with Microsoft provider."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        providers = {"microsoft": mock_provider_client}
        service = EmailService(providers)

        yield service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_microsoft_recent_emails_query_generation(self, microsoft_service):
        """Test that Microsoft recent emails generates correct OData filter."""
        # Mock the Graph client response
        mock_results = {
            "value": [
                {"id": "msg1"},
                {"id": "msg2"},
            ]
        }

        microsoft_service.provider_client.email_client.graph_client.list_messages = (
            AsyncMock(return_value=mock_results)
        )

        # Mock context.get_pages to return mock pages
        mock_pages = [
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="msg1"),
                thread_id="thread1",
                subject="Test 1",
                sender="sender1@example.com",
                recipients=["recipient1@example.com"],
                cc_list=[],
                body="Test body 1",
                time=datetime.now(timezone.utc),
                permalink="",
            ),
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="msg2"),
                thread_id="thread2",
                subject="Test 2",
                sender="sender2@example.com",
                recipients=["recipient2@example.com"],
                cc_list=[],
                body="Test body 2",
                time=datetime.now(timezone.utc),
                permalink="",
            ),
        ]
        microsoft_service.context.get_pages = AsyncMock(return_value=mock_pages)

        # Test recent emails
        result = await microsoft_service.get_recent_emails(days=7)

        # Verify the Graph API was called with correct filter
        microsoft_service.provider_client.email_client.graph_client.list_messages.assert_called_once()
        call_args = (
            microsoft_service.provider_client.email_client.graph_client.list_messages.call_args
        )

        assert call_args[1]["folder"] == "inbox"
        assert "receivedDateTime ge" in call_args[1]["filter_query"]
        assert call_args[1]["search"] is None
        assert call_args[1]["order_by"] == "receivedDateTime desc"

        # Verify results
        assert len(result.results) == 2
        assert isinstance(result.results[0], EmailPage)

    @pytest.mark.asyncio
    async def test_microsoft_unread_emails_query(self, microsoft_service):
        """Test that Microsoft unread emails generates correct OData filter."""
        # Mock the Graph client response
        mock_results = {"value": [{"id": "unread1"}]}

        microsoft_service.provider_client.email_client.graph_client.list_messages = (
            AsyncMock(return_value=mock_results)
        )

        # Mock context.get_pages
        mock_pages = [
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="unread1"),
                thread_id="thread1",
                subject="Unread email",
                sender="sender@example.com",
                recipients=["recipient@example.com"],
                cc_list=[],
                body="Unread body",
                time=datetime.now(timezone.utc),
                permalink="",
            )
        ]
        microsoft_service.context.get_pages = AsyncMock(return_value=mock_pages)

        # Test unread emails
        result = await microsoft_service.get_unread_emails()

        # Verify the Graph API was called with correct filter
        microsoft_service.provider_client.email_client.graph_client.list_messages.assert_called_once()
        call_args = (
            microsoft_service.provider_client.email_client.graph_client.list_messages.call_args
        )

        assert call_args[1]["folder"] == "inbox"
        assert call_args[1]["filter_query"] == "isRead eq false"
        assert call_args[1]["search"] is None

        # Verify results
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_microsoft_search_from_person(self, microsoft_service):
        """Test Microsoft search emails from person with correct OData filter."""
        # Mock the Graph client response
        mock_results = {"value": [{"id": "from_msg1"}]}

        microsoft_service.provider_client.email_client.graph_client.list_messages = (
            AsyncMock(return_value=mock_results)
        )

        # Mock context.get_pages
        mock_pages = [
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="from_msg1"),
                thread_id="thread1",
                subject="From John",
                sender="john@example.com",
                recipients=["recipient@example.com"],
                cc_list=[],
                body="Email from John",
                time=datetime.now(timezone.utc),
                permalink="",
            )
        ]
        microsoft_service.context.get_pages = AsyncMock(return_value=mock_pages)

        # Test search emails from person
        result = await microsoft_service.search_emails_from_person(
            person="john@example.com", content="meeting"
        )

        # Verify the Graph API was called with correct filter and search
        microsoft_service.provider_client.email_client.graph_client.list_messages.assert_called_once()
        call_args = (
            microsoft_service.provider_client.email_client.graph_client.list_messages.call_args
        )

        assert call_args[1]["folder"] == "inbox"
        assert (
            call_args[1]["filter_query"]
            == "from/emailAddress/address eq 'john@example.com'"
        )
        assert call_args[1]["search"] == "meeting"

        # Verify results
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_microsoft_search_to_person(self, microsoft_service):
        """Test Microsoft search emails to person with correct OData filter."""
        # Mock the Graph client response
        mock_results = {"value": [{"id": "to_msg1"}]}

        microsoft_service.provider_client.email_client.graph_client.list_messages = (
            AsyncMock(return_value=mock_results)
        )

        # Mock context.get_pages
        mock_pages = [
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="to_msg1"),
                thread_id="thread1",
                subject="To John",
                sender="sender@example.com",
                recipients=["john@example.com"],
                cc_list=[],
                body="Email to John",
                time=datetime.now(timezone.utc),
                permalink="",
            )
        ]
        microsoft_service.context.get_pages = AsyncMock(return_value=mock_pages)

        # Test search emails to person
        result = await microsoft_service.search_emails_to_person(
            person="john@example.com", content="project"
        )

        # Verify the Graph API was called with correct filter and search
        microsoft_service.provider_client.email_client.graph_client.list_messages.assert_called_once()
        call_args = (
            microsoft_service.provider_client.email_client.graph_client.list_messages.call_args
        )

        assert call_args[1]["folder"] == "inbox"
        expected_filter = "toRecipients/any(r:r/emailAddress/address eq 'john@example.com') or ccRecipients/any(r:r/emailAddress/address eq 'john@example.com')"
        assert call_args[1]["filter_query"] == expected_filter
        assert call_args[1]["search"] == "project"

        # Verify results
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_microsoft_search_by_content_only(self, microsoft_service):
        """Test Microsoft content-only search."""
        # Mock the Graph client response
        mock_results = {"value": [{"id": "content_msg1"}]}

        microsoft_service.provider_client.email_client.graph_client.list_messages = (
            AsyncMock(return_value=mock_results)
        )

        # Mock context.get_pages
        mock_pages = [
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="content_msg1"),
                thread_id="thread1",
                subject="Content search result",
                sender="sender@example.com",
                recipients=["recipient@example.com"],
                cc_list=[],
                body="Important meeting notes",
                time=datetime.now(timezone.utc),
                permalink="",
            )
        ]
        microsoft_service.context.get_pages = AsyncMock(return_value=mock_pages)

        # Test content search
        result = await microsoft_service.search_emails_by_content(
            content="meeting notes"
        )

        # Verify the Graph API was called with correct search only
        microsoft_service.provider_client.email_client.graph_client.list_messages.assert_called_once()
        call_args = (
            microsoft_service.provider_client.email_client.graph_client.list_messages.call_args
        )

        assert call_args[1]["folder"] == "inbox"
        assert call_args[1]["filter_query"] is None
        assert call_args[1]["search"] == "meeting notes"

        # Verify results
        assert len(result.results) == 1

    def test_microsoft_provider_type_detection(self, microsoft_service):
        """Test that the service correctly identifies as Microsoft provider."""
        assert microsoft_service.provider_type == "microsoft"
        assert microsoft_service.name == "outlook"

    @pytest.mark.asyncio
    async def test_microsoft_pagination(self, microsoft_service):
        """Test Microsoft pagination with skip parameter."""
        # Mock the Graph client response
        mock_results = {"value": [{"id": "page2_msg1"}]}

        microsoft_service.provider_client.email_client.graph_client.list_messages = (
            AsyncMock(return_value=mock_results)
        )

        # Mock context.get_pages
        mock_pages = [
            EmailPage(
                uri=PageURI(root="test", type="outlook_email", id="page2_msg1"),
                thread_id="thread1",
                subject="Page 2 result",
                sender="sender@example.com",
                recipients=["recipient@example.com"],
                cc_list=[],
                body="Second page content",
                time=datetime.now(timezone.utc),
                permalink="",
            )
        ]
        microsoft_service.context.get_pages = AsyncMock(return_value=mock_pages)

        # Test with pagination cursor
        result = await microsoft_service.get_recent_emails(days=5, cursor="10")

        # Verify pagination parameters
        microsoft_service.provider_client.email_client.graph_client.list_messages.assert_called_once()
        call_args = (
            microsoft_service.provider_client.email_client.graph_client.list_messages.call_args
        )

        assert call_args[1]["skip"] == 10
        assert call_args[1]["top"] == 10  # default page size
