"""Tests for Calendar service integration with the new architecture."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import CalendarEventPage
from pragweb.services import CalendarService


class MockGoogleCalendarClient:
    """Mock Google Calendar client for testing."""

    def __init__(self):
        self.events = {}

    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Get event by ID."""
        return self.events.get(f"{calendar_id}:{event_id}", {})

    async def search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search events."""
        return {"items": [], "nextPageToken": None}

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
        page_token: str = None,
    ) -> Dict[str, Any]:
        """List events."""
        return {"items": [], "nextPageToken": None}

    async def create_event(
        self, event_data: Dict[str, Any], calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Create a new event."""
        return {"id": "new_event_123"}

    async def update_event(
        self, event_id: str, event_data: Dict[str, Any], calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Update an event."""
        return {"id": event_id}

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete an event."""
        return True

    def parse_event_to_calendar_page(
        self, event_data: Dict[str, Any], page_uri: PageURI
    ) -> CalendarEventPage:
        """Parse event data to CalendarEventPage."""
        return CalendarEventPage(
            uri=page_uri,
            provider_event_id=event_data.get("id", "test_event"),
            summary=event_data.get("summary", "Test Event"),
            description=event_data.get("description", "Test description"),
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            location=event_data.get("location", "Test Location"),
            organizer="test@example.com",
            attendees=["attendee@example.com"],  # Simple email list
            calendar_id="primary",
            permalink="https://calendar.google.com/event/test",
        )


class MockGoogleProviderClient(BaseProviderClient):
    """Mock Google provider client."""

    def __init__(self):
        super().__init__(Mock())
        self._calendar_client = MockGoogleCalendarClient()

    @property
    def calendar_client(self):
        return self._calendar_client

    @property
    def email_client(self):
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


class TestCalendarService:
    """Test suite for Calendar service with new architecture."""

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
        service = CalendarService(providers)

        yield service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.name == "google_calendar"
        assert len(service.providers) == 1
        assert "google" in service.providers

    @pytest.mark.asyncio
    async def test_service_registration(self, service):
        """Test that service registers with context."""
        context = service.context
        registered_service = context.get_service("google_calendar")
        assert registered_service is service

    @pytest.mark.asyncio
    async def test_create_calendar_event_page(self, service):
        """Test creating a calendar event page from URI."""
        # Set up mock event data
        event_data = {
            "id": "test_event",
            "summary": "Test Event",
            "description": "Test description",
            "location": "Test Location",
        }

        service.providers["google"].calendar_client.get_event = AsyncMock(
            return_value=event_data
        )

        # Create page URI with new format
        page_uri = PageURI(
            root="test://example", type="google_calendar_event", id="test_event"
        )

        # Test page creation
        event_page = await service.create_page(page_uri, "test_event", "primary")

        assert isinstance(event_page, CalendarEventPage)
        assert event_page.uri == page_uri
        assert event_page.summary == "Test Event"

        # Verify API was called
        service.providers["google"].calendar_client.get_event.assert_called_once_with(
            "test_event", "primary"
        )

    @pytest.mark.asyncio
    async def test_search_events(self, service):
        """Test searching for events."""
        # Mock search results
        mock_results = {
            "items": [
                {"id": "event1", "summary": "Event 1"},
                {"id": "event2", "summary": "Event 2"},
            ],
            "nextPageToken": "next_token",
        }

        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value=mock_results
        )

        # Test search
        result = await service.get_events_by_keyword("test query")

        assert isinstance(result.results, list)
        assert result.next_cursor == "next_token"

        # Verify the search was called correctly
        service.providers["google"].calendar_client.search_events.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_calendar_events(self, service):
        """Test getting calendar events."""
        # Mock list results
        mock_results = {
            "items": [{"id": "event1", "summary": "Event 1"}],
            "nextPageToken": None,
        }

        service.providers["google"].calendar_client.list_events = AsyncMock(
            return_value=mock_results
        )

        # Test get events
        result = await service.get_upcoming_events()

        assert isinstance(result.results, list)

        # Verify the list was called correctly (with time parameters)
        assert service.providers["google"].calendar_client.list_events.called
        call_args = service.providers["google"].calendar_client.list_events.call_args
        assert call_args.kwargs["calendar_id"] == "primary"
        assert call_args.kwargs["max_results"] == 50
        assert "time_min" in call_args.kwargs
        assert "time_max" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_parse_event_uri(self, service):
        """Test parsing event URI."""
        page_uri = PageURI(
            root="test://example", type="google_calendar_event", id="event123"
        )

        provider_name, calendar_id, event_id = service._parse_event_uri(page_uri)

        assert provider_name == "google"
        assert calendar_id == "primary"
        assert event_id == "event123"

    @pytest.mark.asyncio
    async def test_empty_providers(self, service):
        """Test handling of service with no providers."""
        # Clear providers to simulate error
        service.providers = {}
        service.provider_client = None

        page_uri = PageURI(
            root="test://example", type="google_calendar_event", id="event123"
        )

        with pytest.raises(ValueError, match="No provider available"):
            await service.create_event_page(page_uri)

    @pytest.mark.asyncio
    async def test_search_with_no_results(self, service):
        """Test search when no events are found."""
        # Mock empty results
        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value={"items": [], "nextPageToken": None}
        )

        result = await service.get_events_by_keyword("test")

        assert len(result.results) == 0
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_get_events_by_date_range_basic(self, service):
        """Test get_events_by_date_range without keywords."""
        mock_events = [{"id": "event1"}, {"id": "event2"}]
        service.providers["google"].calendar_client.list_events = AsyncMock(
            return_value={"items": mock_events, "nextPageToken": None}
        )

        result = await service.get_events_by_date_range("2023-06-15", num_days=7)

        service.providers["google"].calendar_client.list_events.assert_called_once()
        assert isinstance(result.results, list)
        assert len(result.results) == 2
        assert all(isinstance(page, CalendarEventPage) for page in result.results)

    @pytest.mark.asyncio
    async def test_get_events_by_date_range_with_keywords(self, service):
        """Test get_events_by_date_range with keywords."""
        mock_events = [
            {
                "id": "event1",
                "summary": "meeting",
                "start": {"dateTime": "2023-06-16T10:00:00Z"},
            }
        ]
        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value={"items": mock_events, "nextPageToken": None}
        )

        result = await service.get_events_by_date_range(
            "2023-06-15", num_days=7, content="meeting"
        )

        service.providers["google"].calendar_client.search_events.assert_called_once()
        assert isinstance(result.results, list)
        assert len(result.results) == 1
        assert isinstance(result.results[0], CalendarEventPage)

    @pytest.mark.asyncio
    async def test_get_events_with_person_basic(self, service):
        """Test get_events_with_person without keywords."""
        mock_events = [{"id": "event1"}]
        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value={"items": mock_events, "nextPageToken": None}
        )

        with patch(
            "pragweb.services.calendar.resolve_person_identifier",
            return_value="test@example.com",
        ):
            result = await service.get_events_with_person("test@example.com")

        service.providers["google"].calendar_client.search_events.assert_called_once()
        assert isinstance(result.results, list)
        assert len(result.results) == 1
        assert isinstance(result.results[0], CalendarEventPage)

    @pytest.mark.asyncio
    async def test_get_events_with_person_with_keywords(self, service):
        """Test get_events_with_person with keywords."""
        mock_events = [{"id": "event1"}]
        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value={"items": mock_events, "nextPageToken": None}
        )

        with patch(
            "pragweb.services.calendar.resolve_person_identifier",
            return_value="test@example.com",
        ):
            result = await service.get_events_with_person(
                "test@example.com", content="meeting"
            )

        service.providers["google"].calendar_client.search_events.assert_called_once()
        assert isinstance(result.results, list)
        assert len(result.results) == 1
        assert isinstance(result.results[0], CalendarEventPage)

    @pytest.mark.asyncio
    async def test_get_events_by_keyword(self, service):
        """Test getting events by keyword."""
        mock_events = [{"id": "event1"}]
        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value={"items": mock_events, "nextPageToken": None}
        )

        result = await service.get_events_by_keyword("meeting")

        service.providers["google"].calendar_client.search_events.assert_called_once()
        assert isinstance(result.results, list)
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_get_upcoming_events_with_keywords(self, service):
        """Test upcoming events retrieval with keywords."""
        # Use a future date to ensure it's within the upcoming events range
        from datetime import datetime, timedelta

        future_date = (datetime.now() + timedelta(days=2)).isoformat() + "Z"

        mock_events = [
            {"id": "event1", "summary": "meeting", "start": {"dateTime": future_date}}
        ]
        service.providers["google"].calendar_client.search_events = AsyncMock(
            return_value={"items": mock_events, "nextPageToken": None}
        )

        result = await service.get_upcoming_events(days=7, content="meeting")

        service.providers["google"].calendar_client.search_events.assert_called_once()
        assert isinstance(result.results, list)
        assert len(result.results) == 1
