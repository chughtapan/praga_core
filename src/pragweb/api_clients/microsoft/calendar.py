"""Microsoft Outlook-specific calendar client implementation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BaseCalendarClient
from pragweb.pages import CalendarEventPage

from .auth import MicrosoftAuthManager
from .client import MicrosoftGraphClient


class OutlookCalendarClient(BaseCalendarClient):
    """Microsoft Outlook-specific calendar client implementation."""

    def __init__(self, auth_manager: MicrosoftAuthManager):
        self.auth_manager = auth_manager
        self.graph_client = MicrosoftGraphClient(auth_manager)

    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Get an Outlook calendar event by ID."""
        return await self.graph_client.get_event(event_id)

    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List Outlook calendar events."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        # Build filter for time range
        filter_parts = []
        if time_min:
            filter_parts.append(f"start/dateTime ge '{time_min.isoformat()}'")
        if time_max:
            filter_parts.append(f"end/dateTime le '{time_max.isoformat()}'")

        filter_query = " and ".join(filter_parts) if filter_parts else None

        return await self.graph_client.list_events(
            top=max_results,
            skip=skip,
            filter_query=filter_query,
            order_by="start/dateTime",
        )

    async def search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search Outlook calendar events."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        return await self.graph_client.list_events(
            top=max_results, skip=skip, search=query, order_by="start/dateTime"
        )

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
        """Create an Outlook calendar event."""
        # Build event data
        event_data: Dict[str, Any] = {
            "subject": title,
            "start": {"dateTime": start_time.isoformat(), "timeZone": "UTC"},
            "end": {"dateTime": end_time.isoformat(), "timeZone": "UTC"},
        }

        if description:
            event_data["body"] = {"contentType": "text", "content": description}

        if location:
            event_data["location"] = {"displayName": location}

        if attendees:
            attendee_list: List[Dict[str, Any]] = [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in attendees
            ]
            event_data["attendees"] = attendee_list

        return await self.graph_client.create_event(event_data)

    async def update_event(
        self, event_id: str, calendar_id: str = "primary", **updates: Any
    ) -> Dict[str, Any]:
        """Update an Outlook calendar event."""
        event_data = {}

        if "title" in updates:
            event_data["subject"] = updates["title"]

        if "description" in updates:
            event_data["body"] = {
                "contentType": "text",
                "content": updates["description"],
            }

        if "location" in updates:
            event_data["location"] = {"displayName": updates["location"]}

        if "start_time" in updates:
            event_data["start"] = {
                "dateTime": updates["start_time"].isoformat(),
                "timeZone": "UTC",
            }

        if "end_time" in updates:
            event_data["end"] = {
                "dateTime": updates["end_time"].isoformat(),
                "timeZone": "UTC",
            }

        if "attendees" in updates:
            event_data["attendees"] = [
                {"emailAddress": {"address": email}, "type": "required"}
                for email in updates["attendees"]
            ]

        return await self.graph_client.update_event(event_id, event_data)

    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete an Outlook calendar event."""
        await self.graph_client.delete_event(event_id)
        return True

    def parse_event_to_calendar_page(
        self, event_data: Dict[str, Any], page_uri: PageURI
    ) -> CalendarEventPage:
        """Parse Outlook event data to CalendarEventPage."""
        # Parse start and end times
        start_data = event_data.get("start", {})
        end_data = event_data.get("end", {})

        start_time = datetime.fromisoformat(start_data.get("dateTime", ""))
        end_time = datetime.fromisoformat(end_data.get("dateTime", ""))

        # Check if all-day event
        event_data.get("isAllDay", False)

        # Parse attendees - simple email list
        attendees = []
        for attendee_data in event_data.get("attendees", []):
            email_address = attendee_data.get("emailAddress", {}).get("address", "")
            if email_address:
                attendees.append(email_address)

        # Parse organizer
        organizer_data = event_data.get("organizer", {}).get("emailAddress", {})
        organizer = organizer_data.get("address", "")
        organizer_data.get("name")

        # Parse body/description
        body_data = event_data.get("body", {})
        description = body_data.get("content")

        # Parse location
        location_data = event_data.get("location", {})
        location = location_data.get("displayName")

        # Parse recurrence
        is_recurring = "recurrence" in event_data
        if is_recurring:
            recurrence_data = event_data.get("recurrence", {})
            # Microsoft Graph uses a different recurrence format than RFC 5545
            # For now, just store it as JSON
            str(recurrence_data)

        # Parse basic status info (removed complex status mapping)

        # Parse sensitivity/visibility
        event_data.get("sensitivity", "normal")

        # Parse categories
        event_data.get("categories", [])

        # Parse meeting URL
        online_meeting = event_data.get("onlineMeeting")
        if online_meeting:
            online_meeting.get("joinUrl")

        # Parse timestamps

        return CalendarEventPage(
            uri=page_uri,
            provider_event_id=event_data.get("id", ""),
            calendar_id="primary",  # Microsoft Graph doesn't expose calendar ID in event data
            summary=event_data.get("subject", ""),
            description=description,
            location=location,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            organizer=organizer,
            permalink=event_data.get("webLink", ""),
        )
