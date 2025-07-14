"""Provider-agnostic email page definitions."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, computed_field

from praga_core.types import Page, PageURI


class EmailPage(Page):
    """A page representing an email with all email-specific fields."""

    @computed_field
    def thread_uri(self) -> PageURI:
        """URI that links to the thread page containing this email."""
        # Convert email service type to thread service type
        service_type = self.uri.type.replace("_email", "_thread")
        return PageURI(
            root=self.uri.root,
            type=service_type,  # gmail_thread, outlook_thread
            id=self.thread_id,
            version=self.uri.version,
        )

    # Provider-specific metadata (stored as internal fields)
    thread_id: str = Field(description="Thread ID", exclude=True)

    # Core email fields (provider-agnostic)
    subject: str = Field(description="Email subject")
    sender: str = Field(description="Email sender")
    recipients: List[str] = Field(description="List of email recipients")
    cc_list: List[str] = Field(
        default_factory=list, description="List of CC recipients"
    )
    body: str = Field(description="Email body content")
    time: datetime = Field(description="Email timestamp")
    permalink: str = Field(description="Provider-specific permalink URL")


class EmailSummary(BaseModel):
    """A compressed representation of an email for use in thread pages."""

    uri: PageURI = Field(description="URI to the full email page")
    sender: str = Field(description="Email sender")
    recipients: List[str] = Field(description="List of email recipients")
    cc_list: List[str] = Field(
        default_factory=list, description="List of CC recipients"
    )
    body: str = Field(description="Email body content")
    time: datetime = Field(description="Email timestamp")


class EmailThreadPage(Page):
    """A page representing an email thread with all emails in the thread."""

    thread_id: str = Field(description="Thread ID", exclude=True)
    subject: str = Field(description="Thread subject (usually from first email)")
    emails: List[EmailSummary] = Field(
        description="List of compressed email summaries in this thread"
    )
    permalink: str = Field(description="Provider-specific thread permalink URL")
