"""Calendar toolkit for retrieving and searching calendar events."""

import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict

from praga_core.agents import PaginatedResponse, RetrieverToolkit
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.calendar import CalendarEventPage  # noqa: E402
from services.calendar_service import CalendarService  # noqa: E402

logger = logging.getLogger(__name__)


class CalendarToolkit(RetrieverToolkit):
    """Toolkit for retrieving calendar events using Calendar service."""

    def __init__(self, context: ServerContext, calendar_service: CalendarService):
        super().__init__(context)
        self.calendar_service = calendar_service

        # Register all calendar tools
        self.register_tool(self.get_events_by_date_range)
        self.register_tool(self.get_events_by_attendee)
        self.register_tool(self.get_events_by_organizer)
        self.register_tool(self.get_upcoming_events)
        self.register_tool(self.get_events_by_keyword)

        logger.info("Calendar toolkit initialized")

    @property
    def name(self) -> str:
        return "CalendarToolkit"

    def _search_events_paginated_response(
        self,
        query_params: Dict[str, Any],
        page: int = 0,
        page_size: int = 10,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Search events and return a paginated response."""
        page_token = None
        if page > 0:
            current_token = None
            for _ in range(page):
                _, current_token = self.calendar_service.search_events(
                    query_params, current_token, page_size
                )
                if not current_token:
                    # No more pages available
                    logger.debug(f"No more pages available at page {page}")
                    return PaginatedResponse(
                        results=[],
                        page_number=page,
                        has_next_page=False,
                    )
            page_token = current_token
        # Get the actual page data
        uris, next_page_token = self.calendar_service.search_events(
            query_params, page_token, page_size
        )

        # Resolve URIs to pages using context - throw errors, don't fail silently
        pages = [self.context.get_page(uri) for uri in uris]
        logger.debug(f"Successfully resolved {len(pages)} calendar pages")

        return PaginatedResponse(
            results=pages,
            page_number=page,
            has_next_page=bool(next_page_token),
        )

    def get_events_by_date_range(
        self, start_date: str, num_days: int, page: int = 0
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            num_days: Number of days to search
            page: Page number for pagination (0-based)
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
        return self._search_events_paginated_response(query_params, page)

    def get_events_by_attendee(
        self, attendee: str, page: int = 0
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events where a specific person is an attendee.

        Args:
            attendee: Email address or name of the attendee to search for
            page: Page number for pagination (0-based)
        """
        # Calculate time range
        now = datetime.utcnow()
        query_params = {
            "q": f"who:{attendee}",
            "calendarId": "primary",
            "timeMin": now.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }
        return self._search_events_paginated_response(query_params, page)

    def get_events_by_organizer(
        self, organizer: str, page: int = 0
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events organized by a specific person.

        Args:
            organizer: Email address or name of the organizer to search for
            page: Page number for pagination (0-based)
        """
        # Get upcoming events and filter by organizer
        now = datetime.utcnow()
        query_params = {
            "q": f"organizer:{organizer}",
            "calendarId": "primary",
            "timeMin": now.isoformat() + "Z",
            "singleEvents": True,
            "orderBy": "startTime",
        }
        return self._search_events_paginated_response(query_params, page)

    def get_upcoming_events(
        self, days: int = 7, page: int = 0
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
        return self._search_events_paginated_response(query_params, page)

    def get_events_by_keyword(
        self, keyword: str, page: int = 0
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
        return self._search_events_paginated_response(query_params, page)
