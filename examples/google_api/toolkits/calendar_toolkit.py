"""Google Calendar toolkit for retrieving and searching calendar events."""

import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from praga_core.agents.tool import PaginatedResponse
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.calendar import CalendarEventPage  # noqa: E402
from toolkits.google_base_toolkit import GoogleBaseToolkit  # noqa: E402


class CalendarToolkit(GoogleBaseToolkit):
    """Toolkit for retrieving calendar events from Google Calendar using Google API."""

    def __init__(
        self, context: ServerContext, secrets_dir: Optional[str] = None
    ) -> None:
        """Initialize the Calendar toolkit with authentication."""
        super().__init__(context, secrets_dir)
        self._service = None

        self.register_tool(self.get_calendar_entries_by_date_range)
        self.register_tool(self.get_calendar_entries_by_attendee)
        self.register_tool(self.get_calendar_entries_by_organizer)
        self.register_tool(self.get_calendar_entries_by_topic)
        self.register_tool(self.get_todays_events)
        self.register_tool(self.get_upcoming_events)
        self.register_tool(self.get_meetings_this_week)

    @property
    def name(self) -> str:
        return "CalendarToolkit"

    @property
    def service(self) -> Any:
        """Lazy initialization of Calendar service."""
        if self._service is None:
            self._service = self.auth_manager.get_calendar_service()
        return self._service

    def _validate_cached_document(
        self, cached_doc: CalendarEventPage, event: Dict[str, Any]
    ) -> bool:
        """Validate that a cached document matches the current event data."""
        # Check key fields match
        summary = event.get("summary", "")
        start_time = event.get("start", {}).get("dateTime") or event.get(
            "start", {}
        ).get("date", "")
        end_time = event.get("end", {}).get("dateTime") or event.get("end", {}).get(
            "date", ""
        )
        organizer_email = event.get("organizer", {}).get("email", "")
        event_id = str(event["id"])  # Ensure string type

        return bool(
            cached_doc.summary == summary
            and cached_doc.start_time == start_time
            and cached_doc.end_time == end_time
            and cached_doc.organizer_email == organizer_email
            and cached_doc.event_id == event_id
        )

    def _get_events_paginated(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        q: Optional[str] = None,
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Get calendar events with pagination support using Calendar API cursors.

        Returns:
            Tuple of (events, next_page_token)
        """
        try:
            print(
                f"Calendar search query: '{q}', page_token: {page_token}"
            )  # Debug output

            # Search for events with pagination
            list_params = {
                "calendarId": calendar_id,
                "maxResults": page_size,
                "singleEvents": True,
                "orderBy": "startTime",
            }

            if time_min:
                list_params["timeMin"] = time_min
            if time_max:
                list_params["timeMax"] = time_max
            if q:
                list_params["q"] = q
            if page_token:
                list_params["pageToken"] = page_token

            events_result = self.service.events().list(**list_params).execute()

            events: List[Dict[str, Any]] = events_result.get("items", [])
            next_page_token = events_result.get("nextPageToken")

            print(
                f"Calendar API returned {len(events)} events, next_token: {bool(next_page_token)}"
            )  # Debug output

            # Filter out cancelled events and events where user declined
            filtered_events = self._filter_accepted_events(events)

            return filtered_events, next_page_token

        except Exception as e:
            print(f"Error retrieving calendar events: {e}")
            return [], None

    def _filter_accepted_events(
        self, events: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter out cancelled events and events where the user has declined."""
        filtered_events = []

        for event in events:
            # Skip cancelled events
            if event.get("status") == "cancelled":
                continue

            # Check if the current user has declined this event
            attendees = event.get("attendees", [])
            user_declined = False

            for attendee in attendees:
                # Check if this is the current user (organizer email or self)
                if attendee.get("self") or attendee.get("organizer"):
                    if attendee.get("responseStatus") == "declined":
                        user_declined = True
                        break

            if not user_declined:
                filtered_events.append(event)

        return filtered_events

    def _search_events_paginated_response(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        q: Optional[str] = None,
        page: int = 0,
        page_size: int = 10,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Search calendar events and return a paginated response.

        Args:
            calendar_id: Calendar ID (default: 'primary')
            time_min: Minimum time for events
            time_max: Maximum time for events
            q: Search query
            page: Page number (0-based)
            page_size: Number of events per page

        Returns:
            PaginatedResponse with calendar event documents
        """
        try:
            print(f"Calendar search - page: {page}, query: '{q}'")  # Debug output

            # Calculate page token - for now, we'll use a simple approach
            # In a real implementation, you'd want to cache page tokens
            page_token = None

            # If not the first page, we need to get to the right page
            # This is a simplified approach - in production you'd cache tokens
            if page > 0:
                # Skip to the desired page by fetching previous pages
                current_token = None
                for _ in range(page):
                    _, current_token = self._get_events_paginated(
                        calendar_id, time_min, time_max, q, current_token, page_size
                    )
                    if not current_token:
                        # No more pages available
                        return PaginatedResponse(
                            results=[],
                            page_number=page,
                            has_next_page=False,
                            total_results=0,
                            token_count=0,
                        )
                page_token = current_token

            # Get the actual page data
            events, next_page_token = self._get_events_paginated(
                calendar_id, time_min, time_max, q, page_token, page_size
            )
            uris = [
                self.context.get_page_uri(event["id"], CalendarEventPage)
                for event in events
            ]
            pages = [self.context.get_page(uri) for uri in uris]

            # Calculate token count
            total_tokens = sum(doc.metadata.token_count or 0 for doc in pages)

            return PaginatedResponse(
                results=pages,
                page_number=page,
                has_next_page=bool(next_page_token),
                total_results=None,  # Calendar API doesn't provide total count
                token_count=total_tokens,
            )

        except Exception as e:
            print(f"Error in paginated calendar search: {e}")
            return PaginatedResponse(
                results=[],
                page_number=page,
                has_next_page=False,
                total_results=0,
                token_count=0,
            )

    def get_calendar_entries_by_date_range(
        self,
        start_date: str,
        end_date: str,
        calendar_id: str = "primary",
        page: int = 0,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format or ISO datetime
            end_date: End date in YYYY-MM-DD format or ISO datetime
            calendar_id: Calendar ID (default: 'primary')
            page: Page number for pagination (0-based)
        """
        # Convert to ISO format if needed
        if "T" not in start_date:
            start_date += "T00:00:00Z"
        elif not start_date.endswith("Z"):
            start_date += "Z"

        if "T" not in end_date:
            end_date += "T23:59:59Z"
        elif not end_date.endswith("Z"):
            end_date += "Z"

        return self._search_events_paginated_response(
            calendar_id=calendar_id,
            time_min=start_date,
            time_max=end_date,
            page=page,
        )

    def get_calendar_entries_by_attendee(
        self,
        attendee: str,
        days_ahead: int = 30,
        calendar_id: str = "primary",
        page: int = 0,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events where a specific person is an attendee.

        Args:
            attendee: Email address or name of the attendee to search for
            days_ahead: Number of days ahead to search (default: 30)
            calendar_id: Calendar ID (default: 'primary')
            page: Page number for pagination (0-based)
        """
        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        # Use Google Calendar's built-in search with attendee query
        # The "who:" prefix tells Google Calendar to search attendees
        search_query = f"who:{attendee}"

        return self._search_events_paginated_response(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            q=search_query,
            page=page,
        )

    def get_calendar_entries_by_organizer(
        self,
        organizer: str,
        days_ahead: int = 30,
        calendar_id: str = "primary",
        page: int = 0,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events organized by a specific person.

        Args:
            organizer: Email address or name of the organizer to search for
            days_ahead: Number of days ahead to search (default: 30)
            calendar_id: Calendar ID (default: 'primary')
            page: Page number for pagination (0-based)
        """
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        return self._search_events_paginated_response(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            q=f"{organizer}",
            page=page,
        )

    def get_calendar_entries_by_topic(
        self,
        topic: str,
        days_ahead: int = 30,
        calendar_id: str = "primary",
        page: int = 0,
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get calendar events containing a topic keyword in subject or description.

        Args:
            topic: Topic keyword to search for
            days_ahead: Number of days ahead to search (default: 30)
            calendar_id: Calendar ID (default: 'primary')
            page: Page number for pagination (0-based)
        """
        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        return self._search_events_paginated_response(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            q=f"{topic}",
            page=page,
        )

    def get_todays_events(self, page: int = 0) -> PaginatedResponse[CalendarEventPage]:
        """Get today's calendar events.

        Args:
            page: Page number for pagination (0-based)
        """
        today = datetime.now().strftime("%Y-%m-%d")
        return self.get_calendar_entries_by_date_range(today, today, page=page)

    def get_upcoming_events(
        self, days: int = 7, page: int = 0
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get upcoming calendar events for the next N days.

        Args:
        days: Number of days to look ahead
        page: Page number for pagination (0-based)
        """
        today = datetime.now()
        end_date = today + timedelta(days=days)

        start_str = today.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        return self.get_calendar_entries_by_date_range(start_str, end_str, page=page)

    def get_meetings_this_week(
        self, page: int = 0
    ) -> PaginatedResponse[CalendarEventPage]:
        """Get all meetings for the current week.

        Args:
        page: Page number for pagination (0-based)
        """
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)

        start_str = start_of_week.strftime("%Y-%m-%d")
        end_str = end_of_week.strftime("%Y-%m-%d")

        response = self.get_calendar_entries_by_date_range(
            start_str, end_str, page=page
        )
        meetings = [event for event in response if len(event.attendee_emails) > 1]

        return PaginatedResponse(
            results=meetings,
            page_number=response.page_number,
            has_next_page=response.has_next_page,
            total_results=None,
            token_count=0,
        )
