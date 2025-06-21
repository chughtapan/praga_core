"""Calendar service for handling Calendar API interactions and page creation."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from praga_core.global_context import ContextMixin
from praga_core.types import PageURI

from ..auth import GoogleAuthManager
from ..pages.calendar import CalendarEventPage

logger = logging.getLogger(__name__)


class CalendarService(ContextMixin):
    """Service for Calendar API interactions and CalendarEventPage creation."""

    def __init__(self) -> None:
        self.auth_manager = GoogleAuthManager()
        self.service = self.auth_manager.get_calendar_service()

        # Register handler with context (accessed via ContextMixin)
        self.context.register_handler(self.name, self.create_page)
        logger.info("Calendar service initialized and handler registered")

    @property
    def root(self) -> str:
        """Get root from global context."""
        return self.context.root

    def create_page(
        self, event_id: str, calendar_id: str = "primary"
    ) -> CalendarEventPage:
        """Create a CalendarEventPage from a Calendar event ID - matches old CalendarEventHandler.handle_event logic exactly."""
        # 1. Fetch event from Calendar API
        try:
            event = (
                self.service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
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
        uri = PageURI(root=self.root, type=self.name, id=event_id)
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
            # Add pagination parameters
            query_params["maxResults"] = page_size
            if page_token:
                query_params["pageToken"] = page_token

            logger.debug(f"Calendar search params: {query_params}")

            # Execute search
            results = self.service.events().list(**query_params).execute()
            events = results.get("items", [])
            next_page_token = results.get("nextPageToken")

            logger.debug(
                f"Calendar API returned {len(events)} events, next_token: {bool(next_page_token)}"
            )

            # Convert to PageURIs
            uris = [
                PageURI(root=self.root, type=self.name, id=event["id"])
                for event in events
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching events: {e}")
            raise

    @property
    def name(self) -> str:
        return "calendar_event"
