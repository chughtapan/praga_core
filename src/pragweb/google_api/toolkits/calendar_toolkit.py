"""Calendar toolkit for retrieving and searching calendar events."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool
from praga_core.context import ServerContext

from ..pages.calendar import CalendarEventPage
from ..services.calendar_service import CalendarService
from .utils import resolve_person_to_email

logger = logging.getLogger(__name__)


class CalendarToolkit(RetrieverToolkit):
    """Toolkit for retrieving calendar events using Calendar service."""

    def __init__(self, context: ServerContext, calendar_service: CalendarService):
        super().__init__(context)
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
        self, start_date: str, num_days: int, cursor: Optional[str] = None
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            num_days: Number of days to search
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
        return self._search_events_paginated_response(query_params, cursor)

    @tool()
    def get_events_with_person(
        self, person: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events where a specific person is involved (as attendee or organizer).

        Args:
            person: Email address or name of the person to search for
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(person, self.context)
        if not email:
            logger.warning(f"Could not resolve person '{person}' to email address")
            return PaginatedResponse(results=[], next_cursor=None)

        # Search for events with this person (attendee or organizer)
        now = datetime.utcnow()
        query_params = {
            "q": email,
            "calendarId": "primary",
            "timeMin": now.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }
        return self._search_events_paginated_response(query_params, cursor)

    @tool()
    def get_upcoming_events(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get upcoming events for the next N days."""
        now = datetime.utcnow()
        end = now + timedelta(days=days)

        query_params = {
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
