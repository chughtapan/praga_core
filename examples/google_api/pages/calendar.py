"""Calendar page definition."""

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from praga_core.types import Page


class CalendarEventPage(Page):
    """A page representing a calendar event with all event-specific fields."""

    event_id: str = Field(description="Calendar event ID")
    calendar_id: str = Field(description="Calendar ID")
    summary: str = Field(description="Event summary/title")
    description: Optional[str] = Field(None, description="Event description")
    location: Optional[str] = Field(None, description="Event location")
    start_time: datetime = Field(description="Event start time")
    end_time: datetime = Field(description="Event end time")
    attendees: List[str] = Field(
        default_factory=list, description="List of event attendees"
    )
    organizer: str = Field(description="Event organizer")
    permalink: str = Field(description="Google Calendar permalink URL")
