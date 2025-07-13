"""Google-specific calendar client implementation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BaseCalendarClient
from pragweb.pages import CalendarEventPage

from .auth import GoogleAuthManager


class GoogleCalendarClient(BaseCalendarClient):
    """Google-specific calendar client implementation."""

    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self._executor = ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="google-calendar-client"
        )

    @property
    def _calendar(self) -> Any:
        """Get Calendar service instance."""
        return self.auth_manager.get_calendar_service()

    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Get a Google Calendar event by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._calendar.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            ),
        )
        return dict(result)

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List Google Calendar events."""
        kwargs = {
            "calendarId": calendar_id,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if time_min:
            # Ensure timezone-aware datetime for Google Calendar API
            if time_min.tzinfo is None:
                time_min = time_min.replace(tzinfo=timezone.utc)
            kwargs["timeMin"] = time_min.isoformat()
        if time_max:
            # Ensure timezone-aware datetime for Google Calendar API
            if time_max.tzinfo is None:
                time_max = time_max.replace(tzinfo=timezone.utc)
            kwargs["timeMax"] = time_max.isoformat()
        if page_token:
            kwargs["pageToken"] = page_token

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._calendar.events().list(**kwargs).execute(),
        )
        return dict(result)

    async def search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search Google Calendar events."""
        kwargs = {
            "calendarId": calendar_id,
            "q": query,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }

        if page_token:
            kwargs["pageToken"] = page_token

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._calendar.events().list(**kwargs).execute(),
        )
        return dict(result)

    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a Google Calendar event."""
        # Ensure timezone-aware datetimes
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        event_body = {
            "summary": title,
            "start": {
                "dateTime": start_time.isoformat(),
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": end_time.isoformat(),
                "timeZone": "UTC",
            },
        }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]  # type: ignore[misc]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._calendar.events()
                .insert(calendarId=calendar_id, body=event_body)
                .execute()
            ),
        )
        return dict(result)

    async def update_event(
        self, event_id: str, calendar_id: str = "primary", **updates: Any
    ) -> Dict[str, Any]:
        """Update a Google Calendar event."""
        # First get the current event
        current_event = await self.get_event(event_id, calendar_id)

        # Apply updates
        for key, value in updates.items():
            if key == "title":
                current_event["summary"] = value
            elif key == "description":
                current_event["description"] = value
            elif key == "location":
                current_event["location"] = value
            elif key == "start_time":
                # Ensure timezone-aware datetime
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                current_event["start"] = {
                    "dateTime": value.isoformat(),
                    "timeZone": "UTC",
                }
            elif key == "end_time":
                # Ensure timezone-aware datetime
                if value.tzinfo is None:
                    value = value.replace(tzinfo=timezone.utc)
                current_event["end"] = {
                    "dateTime": value.isoformat(),
                    "timeZone": "UTC",
                }
            elif key == "attendees":
                current_event["attendees"] = [{"email": email} for email in value]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._calendar.events()
                .update(calendarId=calendar_id, eventId=event_id, body=current_event)
                .execute()
            ),
        )
        return dict(result)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete a Google Calendar event."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: (
                self._calendar.events()
                .delete(calendarId=calendar_id, eventId=event_id)
                .execute()
            ),
        )
        return True

    def parse_event_to_calendar_page(
        self, event_data: Dict[str, Any], page_uri: PageURI
    ) -> CalendarEventPage:
        """Parse Google Calendar event data to CalendarEventPage."""
        # Parse start and end times
        start_data = event_data.get("start", {})
        end_data = event_data.get("end", {})

        # Handle both dateTime and date formats
        if "dateTime" in start_data:
            # Parse ISO 8601 datetime with timezone
            start_time_str = start_data["dateTime"]
            if start_time_str.endswith("Z"):
                # Handle Zulu time format
                start_time = datetime.fromisoformat(
                    start_time_str.replace("Z", "+00:00")
                )
            else:
                # Handle ISO 8601 with timezone offset
                start_time = datetime.fromisoformat(start_time_str)
        else:
            # All-day event - just date
            start_time = datetime.fromisoformat(start_data["date"])

        if "dateTime" in end_data:
            # Parse ISO 8601 datetime with timezone
            end_time_str = end_data["dateTime"]
            if end_time_str.endswith("Z"):
                # Handle Zulu time format
                end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
            else:
                # Handle ISO 8601 with timezone offset
                end_time = datetime.fromisoformat(end_time_str)
        else:
            # All-day event - just date
            end_time = datetime.fromisoformat(end_data["date"])

        # Parse attendees - simple email list
        attendees = []
        for attendee_data in event_data.get("attendees", []):
            attendees.append(attendee_data["email"])

        # Parse organizer
        organizer_data = event_data.get("organizer", {})
        organizer = organizer_data.get("email", "")

        return CalendarEventPage(
            uri=page_uri,
            provider_event_id=event_data["id"],
            calendar_id=event_data.get("calendarId", "primary"),
            summary=event_data.get("summary", ""),
            description=event_data.get("description"),
            location=event_data.get("location"),
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            organizer=organizer,
            permalink=event_data.get("htmlLink", ""),
        )
