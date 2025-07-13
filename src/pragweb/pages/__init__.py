"""Provider-agnostic page types for pragweb."""

from .calendar import CalendarEventPage
from .documents import (
    DocumentChunk,
    DocumentComment,
    DocumentHeader,
    DocumentPermission,
    DocumentType,
)
from .email import EmailPage, EmailSummary, EmailThreadPage
from .people import ContactGroupPage, PersonPage

__all__ = [
    # Email pages
    "EmailPage",
    "EmailSummary",
    "EmailThreadPage",
    # Calendar pages
    "CalendarEventPage",
    # People pages
    "PersonPage",
    "ContactGroupPage",
    # Document pages
    "DocumentHeader",
    "DocumentChunk",
    "DocumentComment",
    "DocumentType",
    "DocumentPermission",
]
