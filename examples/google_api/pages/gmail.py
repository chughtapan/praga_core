"""Complete email handlers that handle the entire pipeline from ID to document."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime

from pydantic import Field

from praga_core.types import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import GoogleAuthManager  # noqa: E402
from pages.utils import GmailParser  # noqa: E402


class EmailPage(Page):
    """A document representing an email with all email-specific fields."""

    message_id: str = Field(description="Gmail message ID", exclude=True)
    thread_id: str = Field(description="Gmail thread ID", exclude=True)
    subject: str = Field(description="Email subject")
    sender: str = Field(description="Email sender")
    recipients: list[str] = Field(description="List of email recipients")
    cc_list: list[str] = Field(
        default_factory=list, description="List of CC recipients"
    )
    body: str = Field(description="Email body content")
    time: datetime = Field(description="Email timestamp")
    permalink: str = Field(description="Gmail permalink URL")


class EmailHandler:
    """Complete email handler that fetches and parses Gmail messages."""

    def __init__(self, secrets_dir: str = "") -> None:
        """Initialize with Google API credentials."""
        self.auth_manager = GoogleAuthManager(secrets_dir)
        self.service = self.auth_manager.get_gmail_service()
        self._parser = GmailParser()

    def handle_email(self, email_id: str) -> EmailPage:
        """
        Complete email handler: takes email ID, fetches from Gmail API, parses, returns document.
        """
        # 1. Fetch message from Gmail API
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=email_id, format="full")
                .execute()
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch email {email_id}: {e}")

        # 2. Extract headers
        headers = {
            h["name"]: h["value"] for h in message.get("payload", {}).get("headers", [])
        }

        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        recipients = headers.get("To", "").split(",") if headers.get("To") else []
        cc_list = headers.get("Cc", "").split(",") if headers.get("Cc") else []

        recipients = [r.strip() for r in recipients if r.strip()]
        cc_list = [cc.strip() for cc in cc_list if cc.strip()]

        # 3. Extract body content using parser
        body = self._parser.extract_body(message.get("payload", {}))

        # 4. Parse date
        date_str = headers.get("Date", "")
        email_time = parsedate_to_datetime(date_str) if date_str else datetime.now()

        # 5. Create permalink
        thread_id = message.get("threadId", email_id)
        permalink = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        # 6. Return complete document
        return EmailPage(
            id=email_id,
            message_id=email_id,
            thread_id=thread_id,
            subject=subject,
            sender=sender,
            recipients=recipients,
            cc_list=cc_list,
            body=body,
            time=email_time,
            permalink=permalink,
        )


# Create a singleton instance for use in decorators
_email_handler = EmailHandler()


def create_email_document(email_id: str) -> EmailPage:
    """Standalone function for creating email documents."""
    return _email_handler.handle_email(email_id)
