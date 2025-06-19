"""Pages package for Google API integration."""

from .calendar import CalendarEventPage
from .gmail import EmailPage
from .google_docs import GDocChunk, GDocHeader
from .person import PersonPage

__all__ = ["EmailPage", "CalendarEventPage", "PersonPage", "GDocHeader", "GDocChunk"]
