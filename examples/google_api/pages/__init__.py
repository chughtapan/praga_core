"""Pages package for Google API integration."""

from .calendar import CalendarEventPage
from .gmail import EmailPage

__all__ = ["EmailPage", "CalendarEventPage"]
