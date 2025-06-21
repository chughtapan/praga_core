"""Tests for GoogleAPIClient."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from pragweb.google_api.auth import GoogleAuthManager
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

    def test_lazy_loading_gmail_service(self):
        """Test Gmail service is lazy-loaded."""
        # Initially no service should be loaded
        assert self.client._gmail_service is None

        # Access gmail property should trigger loading
        gmail_service = self.client._gmail

        self.mock_auth_manager.get_gmail_service.assert_called_once()
        assert gmail_service is self.mock_gmail_service
        assert self.client._gmail_service is self.mock_gmail_service

        # Second access should not call auth manager again
        gmail_service2 = self.client._gmail
        assert gmail_service2 is self.mock_gmail_service
        assert self.mock_auth_manager.get_gmail_service.call_count == 1

    def test_lazy_loading_calendar_service(self):
        """Test Calendar service is lazy-loaded."""
        assert self.client._calendar_service is None

        calendar_service = self.client._calendar

        self.mock_auth_manager.get_calendar_service.assert_called_once()
        assert calendar_service is self.mock_calendar_service

    def test_lazy_loading_people_service(self):
        """Test People service is lazy-loaded."""
        assert self.client._people_service is None

        people_service = self.client._people

        self.mock_auth_manager.get_people_service.assert_called_once()
        assert people_service is self.mock_people_service

    def test_get_message(self):
        """Test get_message method."""
        # Setup mock response
        mock_message = {"id": "msg123", "payload": {"headers": []}}
        self.mock_gmail_service.users().messages().get().execute.return_value = (
            mock_message
        )

        result = self.client.get_message("msg123")

        # Verify the get method was called with correct parameters
        self.mock_gmail_service.users().messages().get.assert_called_with(
            userId="me", id="msg123", format="full"
        )
        assert result == mock_message

    def test_search_messages_basic(self):
        """Test search_messages with basic query."""
        # Setup mock response
        mock_response = {
            "messages": [{"id": "msg1"}, {"id": "msg2"}],
            "nextPageToken": "token123",
        }
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        messages, next_token = self.client.search_messages("test query")

        # Verify API call - should add inbox filter
        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="test query in:inbox", maxResults=20
        )

        assert messages == [{"id": "msg1"}, {"id": "msg2"}]
        assert next_token == "token123"

    def test_search_messages_with_inbox_filter(self):
        """Test search_messages doesn't add inbox filter if already present."""
        mock_response = {"messages": [], "nextPageToken": None}
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        self.client.search_messages("in:sent test")

        # Should not add inbox filter
        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="in:sent test", maxResults=20
        )

    def test_search_messages_with_pagination(self):
        """Test search_messages with pagination parameters."""
        mock_response = {"messages": [{"id": "msg1"}], "nextPageToken": None}
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        messages, next_token = self.client.search_messages(
            "test", page_token="prev_token", page_size=10
        )

        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="test in:inbox", maxResults=10, pageToken="prev_token"
        )

    def test_search_messages_empty_query(self):
        """Test search_messages with empty query."""
        mock_response = {"messages": [], "nextPageToken": None}
        self.mock_gmail_service.users().messages().list().execute.return_value = (
            mock_response
        )

        self.client.search_messages("")

        # Should default to inbox search
        self.mock_gmail_service.users().messages().list.assert_called_with(
            userId="me", q="in:inbox", maxResults=20
        )

    def test_get_event(self):
        """Test get_event method."""
        mock_event = {"id": "event123", "summary": "Test Event"}
        self.mock_calendar_service.events().get().execute.return_value = mock_event

        result = self.client.get_event("event123")

        self.mock_calendar_service.events().get.assert_called_with(
            calendarId="primary", eventId="event123"
        )
        assert result == mock_event

    def test_get_event_with_calendar_id(self):
        """Test get_event with custom calendar ID."""
        mock_event = {"id": "event123", "summary": "Test Event"}
        self.mock_calendar_service.events().get().execute.return_value = mock_event

        result = self.client.get_event("event123", calendar_id="custom@gmail.com")

        self.mock_calendar_service.events().get.assert_called_with(
            calendarId="custom@gmail.com", eventId="event123"
        )
        assert result["id"] == "event123"
        assert result["summary"] == "Test Event"

    def test_search_events(self):
        """Test search_events method."""
        mock_response = {
            "items": [{"id": "event1"}, {"id": "event2"}],
            "nextPageToken": "event_token",
        }
        self.mock_calendar_service.events().list().execute.return_value = mock_response

        query_params = {"calendarId": "primary", "q": "meeting"}
        events, next_token = self.client.search_events(query_params)

        expected_params = {"calendarId": "primary", "q": "meeting", "maxResults": 20}
        self.mock_calendar_service.events().list.assert_called_with(**expected_params)

        assert events == [{"id": "event1"}, {"id": "event2"}]
        assert next_token == "event_token"

    def test_search_events_with_pagination(self):
        """Test search_events with pagination."""
        mock_response = {"items": [{"id": "event1"}], "nextPageToken": None}
        self.mock_calendar_service.events().list().execute.return_value = mock_response

        query_params = {"calendarId": "primary"}
        events, next_token = self.client.search_events(
            query_params, page_token="prev_token", page_size=5
        )

        expected_params = {
            "calendarId": "primary",
            "maxResults": 5,
            "pageToken": "prev_token",
        }
        self.mock_calendar_service.events().list.assert_called_with(**expected_params)

    def test_search_contacts(self):
        """Test search_contacts method."""
        mock_response = {
            "results": [
                {"person": {"names": [{"displayName": "John Doe"}]}},
                {"person": {"names": [{"displayName": "Jane Smith"}]}},
            ]
        }
        self.mock_people_service.people().searchContacts().execute.return_value = (
            mock_response
        )

        result = self.client.search_contacts("john")

        self.mock_people_service.people().searchContacts.assert_called_with(
            query="john", readMask="names,emailAddresses"
        )

        expected_results = [
            {"person": {"names": [{"displayName": "John Doe"}]}},
            {"person": {"names": [{"displayName": "Jane Smith"}]}},
        ]
        assert result == expected_results

    def test_search_contacts_empty_response(self):
        """Test search_contacts with empty response."""
        mock_response = {}
        self.mock_people_service.people().searchContacts().execute.return_value = (
            mock_response
        )

        result = self.client.search_contacts("nonexistent")

        assert result == []


class TestGoogleAPIClientErrorHandling:
    """Tests for GoogleAPIClient error handling."""

    def setup_method(self):
        """Setup before each test."""
        self.mock_auth_manager = Mock(spec=GoogleAuthManager)
        self.client = GoogleAPIClient(auth_manager=self.mock_auth_manager)

    def test_get_message_api_error(self):
        """Test get_message handles API errors."""
        mock_gmail_service = MagicMock()
        self.mock_auth_manager.get_gmail_service.return_value = mock_gmail_service

        # Simulate API error
        mock_gmail_service.users().messages().get().execute.side_effect = Exception(
            "API Error"
        )

        with pytest.raises(Exception, match="API Error"):
            self.client.get_message("msg123")

    def test_search_messages_api_error(self):
        """Test search_messages handles API errors."""
        mock_gmail_service = MagicMock()
        self.mock_auth_manager.get_gmail_service.return_value = mock_gmail_service

        mock_gmail_service.users().messages().list().execute.side_effect = Exception(
            "API Error"
        )

        with pytest.raises(Exception, match="API Error"):
            self.client.search_messages("test")
