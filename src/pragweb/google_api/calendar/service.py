"""Calendar service for handling Calendar API interactions and page creation."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from ..utils import resolve_person_identifier
from .page import CalendarEventPage

logger = logging.getLogger(__name__)


class CalendarService(ToolkitService):
    """Service for Calendar API interactions and CalendarEventPage creation."""

    def __init__(self, api_client: GoogleAPIClient) -> None:
        super().__init__()
        self.api_client = api_client

        # Register handlers using decorators
        self._register_handlers()
        logger.info("Calendar service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        @self.context.handler(self.name)
        def handle_event(
            event_id: str, calendar_id: str = "primary"
        ) -> CalendarEventPage:
            return self.create_page(event_id, calendar_id)

    def create_page(
        self, event_id: str, calendar_id: str = "primary"
    ) -> CalendarEventPage:
        """Create a CalendarEventPage from a Calendar event ID - matches old CalendarEventHandler.handle_event logic exactly."""
        # 1. Fetch event from Calendar API using shared client
        try:
            event = self.api_client.get_event(event_id, calendar_id)
        except Exception as e:
            raise ValueError(f"Failed to fetch event {event_id}: {e}")

        # 2. Extract basic fields
        summary = event.get("summary", "")
        description = event.get("description")
        location = event.get("location")

        # 3. Parse times (exact same as old handler)
        start = event.get("start", {})
        end = event.get("end", {})
        start_time = datetime.fromisoformat(start.get("dateTime", start.get("date")))
        end_time = datetime.fromisoformat(end.get("dateTime", end.get("date")))

        # 4. Extract attendees (exact same as old handler)
        attendees = [
            a.get("email", "") for a in event.get("attendees", []) if a.get("email")
        ]

        # 5. Get organizer (exact same as old handler)
        organizer = event.get("organizer", {}).get("email", "")

        # 6. Create permalink (exact same as old handler)
        permalink = f"https://calendar.google.com/calendar/u/0/r/eventedit/{event_id}"

        # 7. Create URI and return complete document
        uri = PageURI(root=self.context.root, type=self.name, id=event_id)
        return CalendarEventPage(
            uri=uri,
            event_id=event_id,
            calendar_id=calendar_id,
            summary=summary,
            description=description,
            location=location,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            organizer=organizer,
            permalink=permalink,
        )

    def search_events(
        self,
        query_params: Dict[str, Any],
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search events and return list of PageURIs and next page token."""
        try:
            logger.debug(f"Searching events with query params: {query_params}")
            events, next_page_token = self.api_client.search_events(
                query_params, page_token=page_token, page_size=page_size
            )

            logger.debug(
                f"Calendar API returned {len(events)} events, next_token: {bool(next_page_token)}"
            )

            # Convert to PageURIs
            uris = [
                PageURI(root=self.context.root, type=self.name, id=event["id"])
                for event in events
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching events: {e}")
            raise

    @property
    def toolkit(self) -> "CalendarToolkit":
        """Get the Calendar toolkit for this service."""
        return CalendarToolkit(calendar_service=self)

    @property
    def name(self) -> str:
        return "calendar_event"


class CalendarToolkit(RetrieverToolkit):
    """Toolkit for retrieving calendar events using Calendar service."""

    def __init__(self, calendar_service: CalendarService):
        super().__init__()  # No explicit context - will use global context
        self.calendar_service = calendar_service

        logger.info("Calendar toolkit initialized")

    @property
    def name(self) -> str:
        return "CalendarToolkit"

    def _search_events_paginated_response(
        self,
        query_params: Dict[str, Any],
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Search events and return a paginated response."""
        # Get the page data using the cursor directly
        uris, next_page_token = self.calendar_service.search_events(
            query_params, cursor, page_size
        )

        # Resolve URIs to pages using context - throw errors, don't fail silently
        pages: List[CalendarEventPage] = []
        for uri in uris:
            page_obj = self.context.get_page(uri)
            if not isinstance(page_obj, CalendarEventPage):
                raise TypeError(f"Expected CalendarEventPage but got {type(page_obj)}")
            pages.append(page_obj)
        logger.debug(f"Successfully resolved {len(pages)} calendar pages")

        return PaginatedResponse(
            results=pages,
            next_cursor=next_page_token,
        )

    @tool()
    def get_events_by_date_range(
        self,
        start_date: str,
        num_days: int,
        content: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            num_days: Number of days to search
            content: Optional content to search for in event title or description
            cursor: Cursor token for pagination (optional)
        """
        # Convert dates to RFC3339 timestamps
        start_dt = datetime.fromisoformat(start_date)
        end_dt = start_dt + timedelta(days=num_days)

        query_params = {
            "calendarId": "primary",
            "timeMin": start_dt.isoformat() + "Z",
            "timeMax": end_dt.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }

        # Add content to search query if provided
        if content:
            query_params["q"] = content

        return self._search_events_paginated_response(query_params, cursor)

    @tool()
    def get_events_with_person(
        self, person: str, content: Optional[str] = None, cursor: Optional[str] = None
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events where a specific person is involved (as attendee or organizer).

        Args:
            person: Email address or name of the person to search for
            content: Additional content to search for in event title or description (optional)
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        query = resolve_person_identifier(person)
        query = f'who:"{query}"'
        if content:
            query += f" {content}"

        # Search for events matching the query
        return self._search_events_paginated_response(
            {
                "q": query,
                "calendarId": "primary",
                "singleEvents": True,
                "orderBy": "startTime",
                "pageToken": cursor,
            }
        )

    @tool()
    def get_upcoming_events(
        self,
        days: int = 7,
        content: Optional[str] = None,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get upcoming events for the next N days.

        Args:
            days: Number of days to look ahead (default: 7)
            content: Optional content to search for in event title or description
            cursor: Cursor token for pagination (optional)
        """
        now = datetime.utcnow()
        end = now + timedelta(days=days)

        query_params = {
            "q": content,
            "calendarId": "primary",
            "timeMin": now.isoformat() + "Z",
            "timeMax": end.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }

        return self._search_events_paginated_response(query_params, cursor)

    @tool()
    def get_events_by_keyword(
        self, keyword: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get events containing a specific keyword in title or description."""
        now = datetime.utcnow()
        query_params = {
            "q": keyword,
            "calendarId": "primary",
            "timeMin": now.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }
        return self._search_events_paginated_response(query_params, cursor)
