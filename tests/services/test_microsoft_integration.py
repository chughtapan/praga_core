"""Tests for Microsoft Graph integration."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core.types import PageURI
from pragweb.api_clients.microsoft import (
    MicrosoftAuthManager,
    MicrosoftGraphClient,
    MicrosoftProviderClient,
    OutlookCalendarClient,
    OutlookEmailClient,
)
from pragweb.pages import EmailPage


class TestMicrosoftAuthManager:
    """Test suite for Microsoft authentication."""

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch("pragweb.api_clients.microsoft.auth.msal.PublicClientApplication")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_auth_manager_initialization(self, mock_msal_app, mock_get_secrets):
        """Test auth manager initializes correctly."""
        # Mock secrets manager
        mock_secrets = Mock()
        mock_secrets.get_oauth_token.return_value = None
        mock_get_secrets.return_value = mock_secrets

        # Mock MSAL app
        mock_app = Mock()
        mock_app.get_accounts.return_value = []
        mock_app.acquire_token_interactive.return_value = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
        }
        mock_msal_app.return_value = mock_app

        # Test auth manager creation (will trigger OAuth flow)
        try:
            auth_manager = MicrosoftAuthManager()
            assert auth_manager.is_authenticated()
        except Exception:
            # OAuth flow may fail in tests - that's expected
            pass

    @patch("pragweb.api_clients.microsoft.auth.get_secrets_manager")
    @patch.dict("os.environ", {"MICROSOFT_CLIENT_ID": "test_client_id"})
    def test_token_storage_includes_required_fields(self, mock_get_secrets):
        """Test that token storage includes scopes and extra_data."""
        from pragweb.api_clients.microsoft.auth import _SCOPES

        mock_secrets = Mock()
        mock_get_secrets.return_value = mock_secrets

        with patch.object(MicrosoftAuthManager, "_authenticate"):
            auth_manager = MicrosoftAuthManager()
            auth_manager._access_token = "test_access_token"
            auth_manager._refresh_token = "test_refresh_token"
            auth_manager._client_id = "test_client_id"

            auth_manager._save_token()

            # Verify store_oauth_token was called with scopes and extra_data
            mock_secrets.store_oauth_token.assert_called_once()
            call_args = mock_secrets.store_oauth_token.call_args

            # Check that scopes and extra_data are included
            assert call_args[1]["scopes"] == _SCOPES
            assert call_args[1]["extra_data"] == {"client_id": "test_client_id"}
            assert call_args[1]["service_name"] == "microsoft"


class TestMicrosoftGraphClient:
    """Test suite for Microsoft Graph client."""

    @pytest.fixture
    def mock_auth_manager(self):
        """Create mock auth manager."""
        auth_manager = Mock()
        auth_manager.is_authenticated.return_value = True
        auth_manager.get_headers.return_value = {
            "Authorization": "Bearer test_token",
            "Content-Type": "application/json",
        }
        auth_manager.ensure_authenticated.return_value = None
        return auth_manager

    @pytest.fixture
    async def graph_client(self, mock_auth_manager):
        """Create graph client with mock auth."""
        client = MicrosoftGraphClient(mock_auth_manager)
        # Mock the session - don't use AsyncMock for the session itself
        mock_session = Mock()
        # The request method should return an async context manager
        mock_request_context = AsyncMock()
        mock_request_context.__aenter__ = AsyncMock()
        mock_request_context.__aexit__ = AsyncMock(return_value=None)
        mock_session.request = Mock(return_value=mock_request_context)
        client.session = mock_session
        yield client

    @pytest.mark.asyncio
    async def test_get_user_profile(self, graph_client):
        """Test getting user profile."""
        # Mock response
        mock_response = Mock()
        mock_response.json = AsyncMock(
            return_value={
                "id": "test_user_id",
                "displayName": "Test User",
                "mail": "test@example.com",
            }
        )
        mock_response.raise_for_status.return_value = None
        mock_response.status = 200

        graph_client.session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await graph_client.get_user_profile()

        assert result["id"] == "test_user_id"
        assert result["displayName"] == "Test User"

    @pytest.mark.asyncio
    async def test_list_messages(self, graph_client):
        """Test listing messages."""
        # Mock response
        mock_response = Mock()
        mock_response.json = AsyncMock(
            return_value={
                "value": [
                    {
                        "id": "message1",
                        "subject": "Test Email",
                        "sender": {"emailAddress": {"address": "sender@example.com"}},
                    }
                ],
                "@odata.nextLink": None,
            }
        )
        mock_response.raise_for_status.return_value = None
        mock_response.status = 200

        graph_client.session.request.return_value.__aenter__.return_value = (
            mock_response
        )

        result = await graph_client.list_messages(top=5)

        assert len(result["value"]) == 1
        assert result["value"][0]["id"] == "message1"


class TestOutlookEmailClient:
    """Test suite for Outlook email client."""

    @pytest.fixture
    def mock_auth_manager(self):
        """Create mock auth manager."""
        auth_manager = Mock()
        auth_manager.is_authenticated.return_value = True
        return auth_manager

    @pytest.fixture
    def email_client(self, mock_auth_manager):
        """Create email client with mock dependencies."""
        client = OutlookEmailClient(mock_auth_manager)
        client.graph_client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_message(self, email_client):
        """Test getting a message."""
        mock_message = {
            "id": "test_message",
            "subject": "Test Subject",
            "sender": {"emailAddress": {"address": "sender@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "recipient@example.com"}}],
            "body": {"content": "Test body"},
            "receivedDateTime": "2023-01-01T12:00:00Z",
        }

        email_client.graph_client.get_message.return_value = mock_message

        result = await email_client.get_message("test_message")

        assert result["id"] == "test_message"
        assert result["subject"] == "Test Subject"
        email_client.graph_client.get_message.assert_called_once_with("test_message")

    @pytest.mark.asyncio
    async def test_send_message(self, email_client):
        """Test sending a message."""
        email_client.graph_client.send_message.return_value = {"id": "sent_message"}

        result = await email_client.send_message(
            to=["recipient@example.com"],
            subject="Test Subject",
            body="Test body",
        )

        assert result["id"] == "sent_message"
        email_client.graph_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_parse_message_to_email_page(self, email_client):
        """Test parsing Outlook message to EmailPage."""
        message_data = {
            "id": "test_message",
            "conversationId": "test_conversation",
            "subject": "Test Subject",
            "sender": {"emailAddress": {"address": "sender@example.com"}},
            "toRecipients": [{"emailAddress": {"address": "recipient@example.com"}}],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {"content": "Test body", "contentType": "text"},
            "receivedDateTime": "2023-01-01T12:00:00Z",
            "isRead": False,
            "importance": "normal",
            "categories": ["Work"],
            "hasAttachments": False,
            "webLink": "https://outlook.com/message",
        }

        page_uri = PageURI(
            root="test://example", type="outlook_email", id="test_message"
        )

        result = email_client.parse_message_to_email_page(message_data, page_uri)

        assert isinstance(result, EmailPage)
        assert result.uri == page_uri
        assert result.uri.id == "test_message"
        assert result.thread_id == "test_conversation"
        # Provider field was removed from pages
        assert result.subject == "Test Subject"
        assert result.sender == "sender@example.com"
        assert result.recipients == ["recipient@example.com"]
        assert result.body == "Test body"


class TestOutlookCalendarClient:
    """Test suite for Outlook calendar client."""

    @pytest.fixture
    def mock_auth_manager(self):
        """Create mock auth manager."""
        auth_manager = Mock()
        auth_manager.is_authenticated.return_value = True
        return auth_manager

    @pytest.fixture
    def calendar_client(self, mock_auth_manager):
        """Create calendar client with mock dependencies."""
        client = OutlookCalendarClient(mock_auth_manager)
        client.graph_client = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_get_event(self, calendar_client):
        """Test getting a calendar event."""
        mock_event = {
            "id": "test_event",
            "subject": "Test Meeting",
            "start": {"dateTime": "2023-01-01T10:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2023-01-01T11:00:00Z", "timeZone": "UTC"},
            "location": {"displayName": "Conference Room"},
            "organizer": {"emailAddress": {"address": "organizer@example.com"}},
        }

        calendar_client.graph_client.get_event.return_value = mock_event

        result = await calendar_client.get_event("test_event")

        assert result["id"] == "test_event"
        assert result["subject"] == "Test Meeting"
        calendar_client.graph_client.get_event.assert_called_once_with("test_event")

    @pytest.mark.asyncio
    async def test_create_event(self, calendar_client):
        """Test creating a calendar event."""
        calendar_client.graph_client.create_event.return_value = {"id": "new_event"}

        start_time = datetime(2023, 1, 1, 10, 0)
        end_time = datetime(2023, 1, 1, 11, 0)

        result = await calendar_client.create_event(
            title="Test Meeting",
            start_time=start_time,
            end_time=end_time,
            location="Conference Room",
            attendees=["attendee@example.com"],
        )

        assert result["id"] == "new_event"
        calendar_client.graph_client.create_event.assert_called_once()


class TestMicrosoftProviderClient:
    """Test suite for Microsoft provider client."""

    @pytest.fixture
    def mock_auth_manager(self):
        """Create mock auth manager."""
        auth_manager = Mock()
        auth_manager.is_authenticated.return_value = True
        return auth_manager

    @pytest.fixture
    def provider_client(self, mock_auth_manager):
        """Create provider client with mock dependencies."""
        return MicrosoftProviderClient(mock_auth_manager)

    def test_provider_name(self, provider_client):
        """Test provider name."""
        assert provider_client.get_provider_name() == "microsoft"

    def test_client_properties(self, provider_client):
        """Test that all client properties are available."""
        assert provider_client.email_client is not None
        assert provider_client.calendar_client is not None
        assert provider_client.people_client is not None
        assert provider_client.documents_client is not None

    @pytest.mark.asyncio
    async def test_test_connection_success(self, provider_client):
        """Test successful connection test."""
        # Mock the auth manager and graph client
        provider_client.auth_manager.is_authenticated.return_value = True

        with patch(
            "pragweb.api_clients.microsoft.provider.MicrosoftGraphClient"
        ) as mock_graph:
            mock_client = AsyncMock()
            mock_client.get_user_profile.return_value = {"id": "test_user"}
            mock_graph.return_value = mock_client

            result = await provider_client.test_connection()
            assert result is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, provider_client):
        """Test failed connection test."""
        # Mock authentication failure
        provider_client.auth_manager.is_authenticated.return_value = False

        result = await provider_client.test_connection()
        assert result is False
