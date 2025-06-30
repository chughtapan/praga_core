"""Gmail page definition."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, computed_field

from praga_core.types import Page, PageURI


class EmailPage(Page):
    """A page representing an email with all email-specific fields."""

    @computed_field
    def thread_uri(self) -> PageURI:
        """URI that links to the thread page containing this email."""
        return PageURI(
            root=self.uri.root,
            type="email_thread",
            id=self.thread_id,
            version=self.uri.version,
        )

    message_id: str = Field(description="Gmail message ID", exclude=True)
    thread_id: str = Field(description="Gmail thread ID", exclude=True)
    subject: str = Field(description="Email subject")
    sender: str = Field(description="Email sender")
    recipients: List[str] = Field(description="List of email recipients")
    cc_list: List[str] = Field(
        default_factory=list, description="List of CC recipients"
    )
    body: str = Field(description="Email body content")
    time: datetime = Field(description="Email timestamp")
    permalink: str = Field(description="Gmail permalink URL")


class EmailSummary(BaseModel):
    """A compressed representation of an email for use in thread pages."""

    uri: PageURI = Field(description="URI to the full email page")
    sender: str = Field(description="Email sender")
    recipients: List[str] = Field(description="List of email recipients")
    cc_list: List[str] = Field(
        default_factory=list, description="List of CC recipients"
    )
    subject: str = Field(description="Email subject (may differ from thread subject)")
    time: datetime = Field(description="Email timestamp")


class EmailThreadPage(Page):
    """A page representing an email thread with all emails in the thread."""

    thread_id: str = Field(description="Gmail thread ID", exclude=True)
    subject: str = Field(description="Thread subject (usually from first email)")
    summary: str = Field(description="LLM-generated summary of the email thread")
    emails: List[EmailSummary] = Field(
        description="List of compressed email summaries in this thread"
    )
    permalink: str = Field(description="Gmail thread permalink URL")
