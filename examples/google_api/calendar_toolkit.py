"""Google Calendar toolkit for retrieving and searching calendar events."""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from google_base_toolkit import GoogleBaseToolkit
from pydantic import Field

from praga_core.types import Document


class CalendarEventDocument(Document):
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

    def __init__(self, **data):
        super().__init__(**data)
        # Calculate token count based on summary and description
        content_length = len(self.summary) + len(self.description)
        self.metadata.token_count = content_length // 4


class CalendarToolkit(GoogleBaseToolkit):
    """Toolkit for retrieving calendar events from Google Calendar using Google API."""

    def __init__(self, secrets_dir: Optional[str] = None):
        """Initialize the Calendar toolkit with authentication."""
        super().__init__(secrets_dir)
        self._service = None

        # Register all Calendar tools with caching and pagination
        self.register_tool(
            self.get_calendar_entries_by_date_range,
            "get_calendar_entries_by_date_range",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_calendar_entries_by_attendee,
            "get_calendar_entries_by_attendee",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_calendar_entries_by_organizer,
            "get_calendar_entries_by_organizer",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_calendar_entries_by_topic,
            "get_calendar_entries_by_topic",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

    @property
    def service(self):
        """Lazy initialization of Calendar service."""
        if self._service is None:
            self._service = self.auth_manager.get_calendar_service()
        return self._service

    def _get_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        q: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Dict]:
        """Get calendar events with optional filters."""
        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=max_results,
                    singleEvents=True,
                    orderBy="startTime",
                    q=q,
                )
                .execute()
            )

            events = events_result.get("items", [])
            print(f"Retrieved {len(events)} calendar events")  # Debug output

            return events

        except Exception as e:
            print(f"Error retrieving calendar events: {e}")
            return []

    def _event_to_document(self, event: Dict) -> CalendarEventDocument:
        """Convert a Calendar event to a CalendarEventDocument."""
        event_id = event.get("id", "unknown")
        summary = event.get("summary", "(No Title)")
        description = event.get("description", "")

        # Handle start and end times
        start = event.get("start", {})
        end = event.get("end", {})

        start_time = start.get("dateTime", start.get("date", ""))
        end_time = end.get("dateTime", end.get("date", ""))

        # Get organizer information
        organizer = event.get("organizer", {})
        organizer_email = organizer.get("email", "")
        organizer_name = organizer.get("displayName", organizer_email)

        # Get attendees information
        attendees = event.get("attendees", [])
        attendee_emails = [
            att.get("email", "") for att in attendees if att.get("email")
        ]
        attendee_names = [
            att.get("displayName", att.get("email", "")) for att in attendees
        ]

        # Get location
        location = event.get("location", "")

        return CalendarEventDocument(
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
        )

    def get_calendar_entries_by_date_range(
        self,
        start_date: str,
        end_date: str,
        calendar_id: str = "primary",
        max_results: int = 100,
    ) -> List[CalendarEventDocument]:
        """Get calendar events within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format or ISO datetime
            end_date: End date in YYYY-MM-DD format or ISO datetime
            calendar_id: Calendar ID (default: 'primary')
            max_results: Maximum number of events to return
        """
        # Convert to ISO format if needed
        if "T" not in start_date:
            start_date += "T00:00:00Z"
        if "T" not in end_date:
            end_date += "T23:59:59Z"

        events = self._get_events(
            calendar_id=calendar_id,
            time_min=start_date,
            time_max=end_date,
            max_results=max_results,
        )

        if events:
            return [self._event_to_document(event) for event in events]
        else:
            return []

    def get_calendar_entries_by_attendee(
        self,
        attendee: str,
        days_ahead: int = 30,
        calendar_id: str = "primary",
        max_results: int = 100,
    ) -> List[CalendarEventDocument]:
        """Get calendar events where a specific person is an attendee.

        Args:
            attendee: Email address or name of the attendee to search for
            days_ahead: Number of days ahead to search (default: 30)
            calendar_id: Calendar ID (default: 'primary')
            max_results: Maximum number of events to return
        """
        attendee_email = self._resolve_person_to_email(attendee)
        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        events = self._get_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )

        # Filter events by attendee
        filtered_events = []
        if events:
            for event in events:
                attendees = event.get("attendees", [])
                attendee_emails = [att.get("email", "") for att in attendees]
                if attendee_email in attendee_emails:
                    filtered_events.append(event)

        if filtered_events:
            return [self._event_to_document(event) for event in filtered_events]
        else:
            return []

    def get_calendar_entries_by_organizer(
        self,
        organizer: str,
        days_ahead: int = 30,
        calendar_id: str = "primary",
        max_results: int = 100,
    ) -> List[CalendarEventDocument]:
        """Get calendar events organized by a specific person.

        Args:
            organizer: Email address or name of the organizer to search for
            days_ahead: Number of days ahead to search (default: 30)
            calendar_id: Calendar ID (default: 'primary')
            max_results: Maximum number of events to return
        """
        organizer_email = self._resolve_person_to_email(organizer)
        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        events = self._get_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
        )

        # Filter events by organizer
        filtered_events = []
        if events:
            for event in events:
                organizer = event.get("organizer", {})
                if organizer.get("email", "") == organizer_email:
                    filtered_events.append(event)

        if filtered_events:
            return [self._event_to_document(event) for event in filtered_events]
        else:
            return []

    def get_calendar_entries_by_topic(
        self,
        topic: str,
        days_ahead: int = 30,
        calendar_id: str = "primary",
        max_results: int = 100,
    ) -> List[CalendarEventDocument]:
        """Get calendar events containing a topic keyword in subject or description.

        Args:
            topic: Topic keyword to search for
            days_ahead: Number of days ahead to search (default: 30)
            calendar_id: Calendar ID (default: 'primary')
            max_results: Maximum number of events to return
        """
        # Calculate time range
        now = datetime.utcnow()
        time_min = now.isoformat() + "Z"
        time_max = (now + timedelta(days=days_ahead)).isoformat() + "Z"

        # First try using Google's search functionality
        events = self._get_events(
            calendar_id=calendar_id,
            time_min=time_min,
            time_max=time_max,
            q=topic,
            max_results=max_results,
        )

        # If search doesn't work well, do manual filtering
        if not events:
            all_events = self._get_events(
                calendar_id=calendar_id,
                time_min=time_min,
                time_max=time_max,
                max_results=max_results,
            )

            topic_lower = topic.lower()
            events = []
            if all_events:
                for event in all_events:
                    summary = event.get("summary", "").lower()
                    description = event.get("description", "").lower()

                    if topic_lower in summary or topic_lower in description:
                        events.append(event)

        if events:
            return [self._event_to_document(event) for event in events]
        else:
            return []

    def get_document_by_id(self, document_id: str) -> Optional[CalendarEventDocument]:
        """Get a calendar event document by its event ID.

        Args:
            document_id: Google Calendar event ID

        Returns:
            CalendarEventDocument if found, None otherwise
        """
        try:
            # Get the event by ID
            event = (
                self.service.events()
                .get(calendarId="primary", eventId=document_id)
                .execute()
            )
            return self._event_to_document(event)
        except Exception as e:
            print(f"Error retrieving calendar event with ID {document_id}: {e}")
            return None


# Stateless tools using decorator
@CalendarToolkit.tool(cache=True, ttl=timedelta(hours=1))
def get_todays_events() -> List[CalendarEventDocument]:
    """Get today's calendar events."""
    toolkit = CalendarToolkit()

    today = datetime.now().strftime("%Y-%m-%d")
    return toolkit.get_calendar_entries_by_date_range(today, today)


@CalendarToolkit.tool(cache=True, ttl=timedelta(minutes=30))
def get_upcoming_events(days: int = 7) -> List[CalendarEventDocument]:
    """Get upcoming calendar events for the next N days."""
    toolkit = CalendarToolkit()

    today = datetime.now()
    end_date = today + timedelta(days=days)

    start_str = today.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    return toolkit.get_calendar_entries_by_date_range(start_str, end_str)


@CalendarToolkit.tool(cache=True, ttl=timedelta(hours=2))
def get_meetings_this_week() -> List[CalendarEventDocument]:
    """Get all meetings for the current week."""
    toolkit = CalendarToolkit()

    today = datetime.now()
    # Calculate start of week (Monday)
    start_of_week = today - timedelta(days=today.weekday())
    # Calculate end of week (Sunday)
    end_of_week = start_of_week + timedelta(days=6)

    start_str = start_of_week.strftime("%Y-%m-%d")
    end_str = end_of_week.strftime("%Y-%m-%d")

    events = toolkit.get_calendar_entries_by_date_range(start_str, end_str)

    # Filter for events that look like meetings (have attendees)
    meetings = []
    for event in events:
        if len(event.attendee_emails) > 1:  # More than just the organizer
            meetings.append(event)

    return meetings
