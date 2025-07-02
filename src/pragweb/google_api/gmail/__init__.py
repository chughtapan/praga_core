"""Gmail service module."""

from .page import EmailPage, EmailSummary, EmailThreadPage
from .service import GmailService

__all__ = [
    "EmailPage",
    "EmailSummary",
    "EmailThreadPage",
    "GmailService",
]
