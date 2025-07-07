"""Tests for GoogleAPIClient."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from pragweb.google_api.auth import _SCOPES, GoogleAuthManager
from pragweb.google_api.client import GoogleAPIClient


class TestGoogleAPIClient:
    """Tests for GoogleAPIClient."""

    def setup_method(self):
        """Setup before each test."""
        # Mock the auth manager to avoid actual authentication
        self.mock_auth_manager = Mock(spec=GoogleAuthManager)
        self.mock_gmail_service = MagicMock()
        self.mock_calendar_service = MagicMock()
        self.mock_people_service = MagicMock()

        self.mock_auth_manager.get_gmail_service.return_value = self.mock_gmail_service
        self.mock_auth_manager.get_calendar_service.return_value = (
            self.mock_calendar_service
        )
        self.mock_auth_manager.get_people_service.return_value = (
            self.mock_people_service
        )

        self.client = GoogleAPIClient(auth_manager=self.mock_auth_manager)

    def test_init_with_auth_manager(self):
        """Test initialization with provided auth manager."""
        client = GoogleAPIClient(auth_manager=self.mock_auth_manager)
        assert client.auth_manager is self.mock_auth_manager

    @patch("pragweb.google_api.client.GoogleAuthManager")
    def test_init_without_auth_manager(self, mock_auth_class):
        """Test initialization creates default auth manager."""
        mock_instance = Mock()
        mock_auth_class.return_value = mock_instance

        client = GoogleAPIClient()

        mock_auth_class.assert_called_once_with()
        assert client.auth_manager is mock_instance

    @pytest.mark.asyncio
    async def test_get_message(self):
        """Test get_message method."""
        # Setup mock response
        mock_message = {"id": "msg123", "payload": {"headers": []}}
        self.mock_gmail_service.users().messages().get().execute.return_value = (
            mock_message
        )

        result = await self.client.get_message("msg123")

        # Verify the get method was called with correct parameters
        self.mock_gmail_service.users().messages().get.assert_called_with(
            userId="me", id="msg123", format="full"
        )
        assert result == mock_message

    @pytest.mark.asyncio
    async def test_get_thread(self):
        """Test get_thread method."""
        # Setup mock response
        mock_thread = {
            "id": "thread456",
            "messages": [
                {"id": "msg1", "payload": {"headers": []}},
                {"id": "msg2", "payload": {"headers": []}},
            ],
        }
        self.mock_gmail_service.users().threads().get().execute.return_value = (
            mock_thread
        )

        result = await self.client.get_thread("thread456")

        # Verify the get method was called with correct parameters
        self.mock_gmail_service.users().threads().get.assert_called_with(
            userId="me", id="thread456", format="full"
        )
        assert result == mock_thread
        assert len(result["messages"]) == 2
        assert result["id"] == "thread456"

    @pytest.mark.asyncio
    async def test_search_messages_basic(self):
        """Test search_messages with basic query."""
        # Setup mock response
        mock_response = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "token123",
        }
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        messages, next_token = await self.client.search_messages("test query")

        # Verify API call - should add inbox filter
        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="test query in:inbox", maxResults=20
        )

        assert messages == [{"id": "msg1"}, {"id": "msg2"}]
        assert next_token == "token123"

    @pytest.mark.asyncio
    async def test_search_messages_with_inbox_filter(self):
        """Test search_messages doesn't add inbox filter if already present."""
        mock_response = {"messages": [], "nextPageToken": None}
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        await self.client.search_messages("in:sent test")

        # Should not add inbox filter
        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="in:sent test", maxResults=20
        )

    @pytest.mark.asyncio
    async def test_search_messages_with_pagination(self):
        """Test search_messages with pagination parameters."""
        mock_response = {"messages": [{"id": "msg1"}], "nextPageToken": None}
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        messages, next_token = await self.client.search_messages(
            "test", page_token="prev_token", page_size=10
        )

        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="test in:inbox", maxResults=10, pageToken="prev_token"
        )

    @pytest.mark.asyncio
    async def test_search_messages_empty_query(self):
        """Test search_messages with empty query."""
        mock_response = {"messages": [], "nextPageToken": None}
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        await self.client.search_messages("")

        # Should default to inbox search
        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="in:inbox", maxResults=20
        )

    @pytest.mark.asyncio
    async def test_get_event(self):
        """Test get_event method."""
        mock_event = {"id": "event123", "summary": "Test Event"}
        self.mock_calendar_service.events().get().execute.return_value = mock_event

        result = await self.client.get_event("event123")

        self.mock_calendar_service.events().get.assert_called_with(
            calendarId="primary", eventId="event123"
        )
        assert result == mock_event

    @pytest.mark.asyncio
    async def test_get_event_with_calendar_id(self):
        """Test get_event with custom calendar ID."""
        mock_event = {"id": "event123", "summary": "Test Event"}
        self.mock_calendar_service.events().get().execute.return_value = mock_event

        result = await self.client.get_event("event123", calendar_id="custom@gmail.com")

        self.mock_calendar_service.events().get.assert_called_with(
            calendarId="custom@gmail.com", eventId="event123"
        )
        assert result["id"] == "event123"
        assert result["summary"] == "Test Event"

    @pytest.mark.asyncio
    async def test_search_events(self):
        """Test search_events method."""
        mock_response = {
            "items": [{"id": "event1"}, {"id": "event2"}],
            "nextPageToken": "event_token",
        }
        self.mock_calendar_service.events().list().execute.return_value = mock_response

        query_params = {"calendarId": "primary", "q": "meeting"}
        events, next_token = await self.client.search_events(query_params)

        expected_params = {"calendarId": "primary", "q": "meeting", "maxResults": 20}
        self.mock_calendar_service.events().list.assert_called_with(**expected_params)

        assert events == [{"id": "event1"}, {"id": "event2"}]
        assert next_token == "event_token"

    @pytest.mark.asyncio
    async def test_search_events_with_pagination(self):
        """Test search_events with pagination."""
        mock_response = {"items": [{"id": "event1"}], "nextPageToken": None}
        self.mock_calendar_service.events().list().execute.return_value = mock_response

        query_params = {"calendarId": "primary"}
        events, next_token = await self.client.search_events(
            query_params, page_token="prev_token", page_size=5
        )

        expected_params = {
            "calendarId": "primary",
            "maxResults": 5,
            "pageToken": "prev_token",
        }
        self.mock_calendar_service.events().list.assert_called_with(**expected_params)

    @pytest.mark.asyncio
    async def test_search_contacts(self):
        """Test search_contacts method."""
        # Setup mock response
        mock_response = {
            "results": [
                {"person": {"names": [{"displayName": "John Doe"}]}},
                {"person": {"names": [{"displayName": "Jane Smith"}]}},
            ]
        }
        self.mock_people_service.people().searchContacts().execute.return_value = (
            mock_response
        )

        # Call search_contacts
        contacts = await self.client.search_contacts("John")

        # Verify API call
        self.mock_people_service.people().searchContacts.assert_called_with(
            query="John",
            readMask="names,emailAddresses",
            sources=[
                "READ_SOURCE_TYPE_PROFILE",
                "READ_SOURCE_TYPE_CONTACT",
                "READ_SOURCE_TYPE_DOMAIN_CONTACT",
            ],
        )

        # Verify results
        assert len(contacts) == 2
        assert contacts[0]["person"]["names"][0]["displayName"] == "John Doe"
        assert contacts[1]["person"]["names"][0]["displayName"] == "Jane Smith"

    @pytest.mark.asyncio
    async def test_search_contacts_empty_response(self):
        """Test search_contacts with empty response."""
        mock_response = {}
        self.mock_people_service.people().searchContacts().execute.return_value = (
            mock_response
        )

        result = await self.client.search_contacts("nonexistent")

        assert result == []


class TestGoogleAPIClientErrorHandling:
    """Tests for GoogleAPIClient error handling."""

    def setup_method(self):
        """Setup before each test."""
        self.mock_auth_manager = Mock(spec=GoogleAuthManager)
        self.client = GoogleAPIClient(auth_manager=self.mock_auth_manager)

    @pytest.mark.asyncio
    async def test_get_message_api_error(self):
        """Test get_message handles API errors."""
        mock_gmail_service = MagicMock()
        self.mock_auth_manager.get_gmail_service.return_value = mock_gmail_service

        # Simulate API error
        mock_gmail_service.users().messages().get().execute.side_effect = Exception(
            "API Error"
        )

        with pytest.raises(Exception, match="API Error"):
            await self.client.get_message("msg123")

    @pytest.mark.asyncio
    async def test_search_messages_api_error(self):
        """Test search_messages handles API errors."""
        mock_gmail_service = MagicMock()
        self.mock_auth_manager.get_gmail_service.return_value = mock_gmail_service

        mock_gmail_service.users().messages().list().execute.side_effect = Exception(
            "API Error"
        )

        with pytest.raises(Exception, match="API Error"):
            await self.client.search_messages("test")

    @pytest.mark.asyncio
    async def test_get_thread_api_error(self):
        """Test get_thread handles API errors."""
        mock_gmail_service = MagicMock()
        self.mock_auth_manager.get_gmail_service.return_value = mock_gmail_service

        # Simulate API error
        mock_gmail_service.users().threads().get().execute.side_effect = Exception(
            "Thread API Error"
        )

        with pytest.raises(Exception, match="Thread API Error"):
            await self.client.get_thread("thread456")


class TestGoogleAuthManagerIntegration:
    """Integration tests for GoogleAuthManager with scope validation."""

    def setup_method(self):
        """Setup before each test."""
        # Reset singleton instance
        GoogleAuthManager._instance = None
        GoogleAuthManager._initialized = False

    @patch("pragweb.google_api.auth.get_current_config")
    @patch("pragweb.google_api.auth.get_secrets_manager")
    @patch("pragweb.google_api.auth.InstalledAppFlow")
    def test_auth_manager_forces_reauth_on_scope_mismatch(
        self, mock_flow_class, mock_get_secrets, mock_get_config
    ):
        """Test that auth manager forces reauth when scopes don't match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock()
        # Mock token data with insufficient scopes (only first 2 scopes)
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "scopes": _SCOPES[:2],  # Insufficient scopes
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        # Mock the OAuth flow
        mock_flow = Mock()
        mock_new_creds = Mock()
        mock_new_creds.token = "new_access_token"
        mock_new_creds.refresh_token = "new_refresh_token"
        mock_new_creds.scopes = _SCOPES
        mock_flow.run_local_server.return_value = mock_new_creds
        mock_flow_class.from_client_secrets_file.return_value = mock_flow

        # Create auth manager - should trigger reauth due to scope mismatch
        GoogleAuthManager()

        # Verify that new OAuth flow was initiated
        mock_flow_class.from_client_secrets_file.assert_called_once_with(
            "test_creds.json", _SCOPES
        )
        mock_flow.run_local_server.assert_called_once_with(port=0)
        mock_secrets.store_oauth_token.assert_called_once()

    @patch("pragweb.google_api.auth.get_current_config")
    @patch("pragweb.google_api.auth.get_secrets_manager")
    def test_auth_manager_uses_existing_creds_when_scopes_match(
        self, mock_get_secrets, mock_get_config
    ):
        """Test that auth manager uses existing credentials when scopes match."""
        mock_config = Mock()
        mock_config.google_credentials_file = "test_creds.json"
        mock_config.secrets_database_url = "test_url"
        mock_get_config.return_value = mock_config

        mock_secrets = Mock()
        # Mock token data with matching scopes
        mock_token_data = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "scopes": _SCOPES,  # All required scopes
            "extra_data": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "token_uri": "https://oauth2.googleapis.com/token",
            },
        }
        mock_secrets.get_oauth_token.return_value = mock_token_data
        mock_get_secrets.return_value = mock_secrets

        # Mock the credentials to appear valid
        with patch("pragweb.google_api.auth.Credentials") as mock_creds_class:
            mock_creds = Mock()
            mock_creds.valid = True
            mock_creds_class.return_value = mock_creds

            # Create auth manager - should use existing credentials
            GoogleAuthManager()

            # Verify credentials were loaded but no new OAuth flow was initiated
            mock_secrets.get_oauth_token.assert_called_once_with("google")
            # store_oauth_token should not be called since we're using existing creds
            mock_secrets.store_oauth_token.assert_not_called()
