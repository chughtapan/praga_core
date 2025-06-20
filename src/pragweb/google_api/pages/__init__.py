"""Pages package for Google API integration."""

from .calendar import CalendarEventPage
from .gmail import EmailPage
from .person import PersonPage

__all__ = ["EmailPage", "CalendarEventPage", "PersonPage"]
