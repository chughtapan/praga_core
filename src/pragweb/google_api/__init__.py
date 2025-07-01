"""Google API integration modules."""

from .calendar import CalendarService
from .client import GoogleAPIClient
from .docs import GoogleDocsService
from .gmail import GmailService
from .people import PeopleService

__all__ = [
    "GoogleAPIClient",
    "CalendarService",
    "GmailService",
    "PeopleService",
    "GoogleDocsService",
]
