"""Complete calendar handlers that handle the entire pipeline from ID to document."""

import os
import sys
from typing import List

from pydantic import Field

from praga_core.types import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import GoogleAuthManager  # noqa: E402


class CalendarEventPage(Page):
    """A document representing a calendar event with all event-specific fields."""

    event_id: str = Field(description="Google Calendar event ID")
    summary: str = Field(description="Event title/summary")
    description: str = Field(default="", description="Event description")
    start_time: str = Field(description="Event start time")
    end_time: str = Field(description="Event end time")
    location: str = Field(default="", description="Event location")
    organizer_email: str = Field(description="Organizer email address")
    organizer_name: str = Field(description="Organizer display name")
    attendee_emails: List[str] = Field(
        default_factory=list, description="List of attendee emails"
    )
    attendee_names: List[str] = Field(
        default_factory=list, description="List of attendee names"
    )
    status: str = Field(default="", description="Event status")
    created: str = Field(default="", description="Event creation timestamp")
    updated: str = Field(default="", description="Event last updated timestamp")
    permalink: str = Field(description="Google Calendar permalink URL")


class CalendarHandler:
    """Complete calendar handler that fetches and parses Google Calendar events."""

    def __init__(self, secrets_dir: str = "") -> None:
        """Initialize with Google API credentials."""
        self.auth_manager = GoogleAuthManager(secrets_dir)
        self.service = self.auth_manager.get_calendar_service()

    def handle_calendar_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> CalendarEventPage:
        """
        Complete calendar handler: takes event ID, fetches from Calendar API, parses, returns document.

        Args:
            event_id: Google Calendar event ID
            calendar_id: Calendar ID (default: 'primary')

        Returns:
            Complete CalendarEventDocument with all fields populated
        """
        # 1. Fetch event from Calendar API
        try:
            event = (
                self.service.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch calendar event {event_id}: {e}")

        # 2. Extract basic event info
        summary = event.get("summary", "")
        description = event.get("description", "")
        location = event.get("location", "")

        # 3. Parse start and end times
        start_time = event.get("start", {}).get("dateTime") or event.get(
            "start", {}
        ).get("date", "")
        end_time = event.get("end", {}).get("dateTime") or event.get("end", {}).get(
            "date", ""
        )

        # 4. Extract organizer info
        organizer = event.get("organizer", {})
        organizer_email = organizer.get("email", "")
        organizer_name = organizer.get("displayName", organizer_email)

        # 5. Extract attendee info
        attendees = event.get("attendees", [])
        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]
        attendee_names = [a.get("displayName", a.get("email", "")) for a in attendees]

        # 6. Get permalink
        permalink = event.get("htmlLink", "")
        if not permalink:
            permalink = f"https://calendar.google.com/calendar/event?eid={event_id}"

        # 8. Return complete document
        return CalendarEventPage(
            id=event_id,
            event_id=event_id,
            summary=summary,
            description=description,
            start_time=start_time,
            end_time=end_time,
            location=location,
            organizer_email=organizer_email,
            organizer_name=organizer_name,
            attendee_emails=attendee_emails,
            attendee_names=attendee_names,
            status=event.get("status", ""),
            created=event.get("created", ""),
            updated=event.get("updated", ""),
            permalink=permalink,
        )


# Create a singleton instance for use in decorators
_calendar_handler = CalendarHandler()


def create_calendar_document(
    event_id: str, calendar_id: str = "primary"
) -> CalendarEventPage:
    """Standalone function for creating calendar documents."""
    return _calendar_handler.handle_calendar_event(event_id, calendar_id)
