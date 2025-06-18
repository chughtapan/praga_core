"""Gmail page definition."""

from datetime import datetime
from typing import List

from pydantic import Field

from praga_core.types import Page


class EmailPage(Page):
    """A page representing an email with all email-specific fields."""

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
