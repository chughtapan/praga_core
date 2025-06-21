"""Tests for existing CalendarService before refactoring."""

from datetime import datetime
from unittest.mock import Mock

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.calendar.page import CalendarEventPage
from pragweb.google_api.calendar.service import CalendarService


class TestCalendarService:
    """Test suite for CalendarService."""

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
        self.mock_api_client.get_event = Mock()
        self.mock_api_client.search_events = Mock()

        self.service = CalendarService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test CalendarService initialization."""
        assert self.service.api_client is self.mock_api_client
        assert self.service.name == "calendar_event"

        # Verify service is registered in context (service auto-registers via ServiceContext)
        assert "calendar_event" in self.mock_context.services
        assert self.mock_context.services["calendar_event"] is self.service

    def test_root_property(self):
        """Test root property returns context root."""
        assert self.service.context.root == "test-root"

    def test_create_page_success(self):
        """Test successful calendar event page creation."""
        # Setup mock event response
        mock_event = {
            "id": "event123",
            "summary": "Team Meeting",
            "description": "Monthly team sync meeting",
            "location": "Conference Room A",
            "start": {"dateTime": "2023-06-15T10:00:00Z"},
            "end": {"dateTime": "2023-06-15T11:00:00Z"},
            "attendees": [
                {"email": "alice@example.com"},
                {"email": "bob@example.com"},
                {"email": ""},  # Empty email should be filtered
            ],
            "organizer": {"email": "organizer@example.com"},
        }

        self.mock_api_client.get_event.return_value = mock_event

        # Call create_page
        result = self.service.create_page("event123", "primary")

        # Verify API client call
        self.mock_api_client.get_event.assert_called_once_with("event123", "primary")

        # Verify result
        assert isinstance(result, CalendarEventPage)
        assert result.event_id == "event123"
        assert result.calendar_id == "primary"
        assert result.summary == "Team Meeting"
        assert result.description == "Monthly team sync meeting"
        assert result.location == "Conference Room A"
        assert result.start_time == datetime.fromisoformat("2023-06-15T10:00:00+00:00")
        assert result.end_time == datetime.fromisoformat("2023-06-15T11:00:00+00:00")
        assert result.attendees == [
            "alice@example.com",
            "bob@example.com",
        ]  # Empty filtered out
        assert result.organizer == "organizer@example.com"
        assert (
            result.permalink
            == "https://calendar.google.com/calendar/u/0/r/eventedit/event123"
        )

        # Verify URI
        expected_uri = PageURI(root="test-root", type="calendar_event", id="event123")
        assert result.uri == expected_uri

    def test_create_page_default_calendar(self):
        """Test create_page with default calendar ID."""
        mock_event = {
            "id": "event123",
            "start": {"dateTime": "2023-06-15T10:00:00Z"},
            "end": {"dateTime": "2023-06-15T11:00:00Z"},
        }

        self.mock_api_client.get_event.return_value = mock_event

        result = self.service.create_page("event123")  # No calendar_id provided

        # Should default to "primary"
        self.mock_api_client.get_event.assert_called_once_with("event123", "primary")
        assert result.calendar_id == "primary"

    def test_create_page_date_only_event(self):
        """Test create_page with all-day event (date only)."""
        mock_event = {
            "id": "event123",
            "summary": "All Day Event",
            "start": {"date": "2023-06-15"},
            "end": {"date": "2023-06-16"},
        }

        self.mock_api_client.get_event.return_value = mock_event

        result = self.service.create_page("event123")

        # Should handle date-only format
        assert result.start_time == datetime.fromisoformat("2023-06-15")
        assert result.end_time == datetime.fromisoformat("2023-06-16")

    def test_create_page_minimal_event(self):
        """Test create_page with minimal event data."""
        mock_event = {
            "id": "event123",
            "start": {"dateTime": "2023-06-15T10:00:00Z"},
            "end": {"dateTime": "2023-06-15T11:00:00Z"},
        }

        self.mock_api_client.get_event.return_value = mock_event

        result = self.service.create_page("event123")

        assert result.summary == ""
        assert result.description is None
        assert result.location is None
        assert result.attendees == []
        assert result.organizer == ""

    def test_create_page_api_error(self):
        """Test create_page handles API errors."""
        self.mock_api_client.get_event.side_effect = Exception("API Error")

        with pytest.raises(
            ValueError, match="Failed to fetch event event123: API Error"
        ):
            self.service.create_page("event123")

    def test_search_events_basic(self):
        """Test basic event search."""
        query_params = {"calendarId": "primary", "q": "meeting"}
        mock_events = [{"id": "event1"}, {"id": "event2"}, {"id": "event3"}]

        self.mock_api_client.search_events.return_value = (mock_events, "token123")

        uris, next_token = self.service.search_events(query_params)

        # Verify API call
        self.mock_api_client.search_events.assert_called_once_with(
            query_params, page_token=None, page_size=20
        )

        # Verify results
        assert len(uris) == 3
        assert all(isinstance(uri, PageURI) for uri in uris)
        assert uris[0].id == "event1"
        assert uris[1].id == "event2"
        assert uris[2].id == "event3"
        assert all(uri.type == "calendar_event" for uri in uris)
        assert all(uri.root == "test-root" for uri in uris)
        assert next_token == "token123"

    def test_search_events_with_pagination(self):
        """Test search with pagination parameters."""
        query_params = {"calendarId": "primary", "q": "meeting"}
        mock_events = [{"id": "event1"}]
        self.mock_api_client.search_events.return_value = (mock_events, None)

        uris, next_token = self.service.search_events(
            query_params, page_token="prev_token", page_size=10
        )

        self.mock_api_client.search_events.assert_called_once_with(
            query_params, page_token="prev_token", page_size=10
        )

        assert len(uris) == 1
        assert next_token is None

    def test_search_events_api_error(self):
        """Test search_events handles API errors."""
        query_params = {"calendarId": "primary", "q": "meeting"}
        self.mock_api_client.search_events.side_effect = Exception("API Error")

        with pytest.raises(Exception, match="API Error"):
            self.service.search_events(query_params)

    def test_search_events_no_results(self):
        """Test search with no results."""
        query_params = {"calendarId": "primary", "q": "nonexistent"}
        self.mock_api_client.search_events.return_value = ([], None)

        uris, next_token = self.service.search_events(query_params)

        assert uris == []
        assert next_token is None

    def test_search_events_complex_query(self):
        """Test search with complex query parameters."""
        query_params = {
            "calendarId": "primary",
            "q": "team meeting",
            "timeMin": "2023-06-01T00:00:00Z",
            "timeMax": "2023-06-30T23:59:59Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }
        mock_events = [{"id": "event1"}, {"id": "event2"}]
        self.mock_api_client.search_events.return_value = (mock_events, "next_token")

        uris, next_token = self.service.search_events(query_params, page_size=50)

        self.mock_api_client.search_events.assert_called_once_with(
            query_params, page_token=None, page_size=50
        )

        assert len(uris) == 2
        assert next_token == "next_token"

    def test_name_property(self):
        """Test name property returns correct service name."""
        assert self.service.name == "calendar_event"
