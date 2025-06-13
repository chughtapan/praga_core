"""Gmail toolkit for retrieving and searching emails."""

import base64
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from google_base_toolkit import GoogleBaseToolkit
from pydantic import Field

from praga_core.types import Document


class EmailDocument(Document):
    """A document representing an email with all email-specific fields."""

    message_id: str = Field(description="Gmail message ID")
    thread_id: str = Field(description="Gmail thread ID")
    subject: str = Field(description="Email subject")
    sender: str = Field(description="Email sender")
    recipients: List[str] = Field(description="List of email recipients")
    cc_list: List[str] = Field(
        default_factory=list, description="List of CC recipients"
    )
    body: str = Field(description="Email body content")
    time: datetime = Field(description="Email timestamp")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self.metadata.token_count = len(self.body) // 4  # Rough token count estimation


class GmailToolkit(GoogleBaseToolkit):
    """Toolkit for retrieving emails from Gmail using Google API."""

    def __init__(self, secrets_dir: Optional[str] = None):
        """Initialize the Gmail toolkit with authentication."""
        super().__init__(secrets_dir)
        self._service = None

        # Register all Gmail tools with caching and pagination
        self.register_tool(
            self.get_emails_by_sender,
            "get_emails_by_sender",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_emails_by_recipient,
            "get_emails_by_recipient",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_emails_by_cc_participant,
            "get_emails_by_cc_participant",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_emails_by_date_range,
            "get_emails_by_date_range",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

        self.register_tool(
            self.get_emails_with_body_keyword,
            "get_emails_with_body_keyword",
            cache=True,
            ttl=timedelta(minutes=15),
            paginate=True,
            max_docs=20,
            max_tokens=8192,
        )

    @property
    def service(self):
        """Lazy initialization of Gmail service."""
        if self._service is None:
            self._service = self.auth_manager.get_gmail_service()
        return self._service

    def _search_emails(self, query: str, max_results: int = 100) -> List[Dict]:
        """Search emails with the given query and return message details."""
        try:
            print(f"Gmail search query: '{query}'")  # Debug output

            # Search for messages
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])
            print(f"Gmail API returned {len(messages)} message IDs")  # Debug output

            # Get full message details for each message
            full_messages = []
            if messages:
                for message in messages:
                    full_msg = (
                        self.service.users()
                        .messages()
                        .get(userId="me", id=message["id"], format="full")
                        .execute()
                    )
                    full_messages.append(full_msg)

            return full_messages

        except Exception as e:
            print(f"Error searching emails: {e}")
            return []

    def _extract_email_content(self, message: dict) -> str:
        """Extract text content from a Gmail message."""
        payload = message.get("payload", {})

        def get_text_from_payload(payload):
            """Recursively extract text from message payload."""
            body = ""

            if "parts" in payload:
                for part in payload["parts"]:
                    body += get_text_from_payload(part)
            else:
                if payload.get("mimeType") == "text/plain":
                    data = payload.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="ignore"
                        )
                elif payload.get("mimeType") == "text/html":
                    # For HTML, we'd ideally parse it, but for now just decode
                    data = payload.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="ignore"
                        )

            return body

        return get_text_from_payload(payload)

    def _message_to_document(self, message: dict) -> EmailDocument:
        """Convert a Gmail message to an EmailDocument."""
        headers = {h["name"]: h["value"] for h in message["payload"].get("headers", [])}

        subject = headers.get("Subject", "(No Subject)")
        sender = headers.get("From", "Unknown Sender")
        date_str = headers.get("Date", "")

        # Parse recipients
        to_field = headers.get("To", "")
        recipients = (
            [addr.strip() for addr in to_field.split(",") if addr.strip()]
            if to_field
            else []
        )

        # Parse CC list
        cc_field = headers.get("Cc", "")
        cc_list = (
            [addr.strip() for addr in cc_field.split(",") if addr.strip()]
            if cc_field
            else []
        )

        # Extract email content
        body = self._extract_email_content(message)

        # Parse timestamp - try to convert date string to datetime
        try:
            # Gmail date format is typically RFC 2822
            from email.utils import parsedate_to_datetime

            email_time = parsedate_to_datetime(date_str) if date_str else datetime.now()
        except (ValueError, TypeError):
            email_time = datetime.now()

        return EmailDocument(
            id=message["id"],
            message_id=message["id"],
            thread_id=message.get("threadId", ""),
            subject=subject,
            sender=sender,
            recipients=recipients,
            cc_list=cc_list,
            body=body,
            time=email_time,
        )

    def get_emails_by_sender(
        self, sender: str, max_results: int = 50
    ) -> List[EmailDocument]:
        """Get emails from a specific sender.

        Args:
            sender: Either an email address or person's name
            max_results: Maximum number of emails to return
        """
        sender_email = self._resolve_person_to_email(sender)
        query = f"from:{sender_email}"
        messages = self._search_emails(query, max_results)
        return [self._message_to_document(msg) for msg in messages]

    def get_emails_by_recipient(
        self, recipient: str, max_results: int = 50
    ) -> List[EmailDocument]:
        """Get emails sent to a specific recipient.

        Args:
            recipient: Either an email address or person's name
            max_results: Maximum number of emails to return
        """
        recipient_email = self._resolve_person_to_email(recipient)
        query = f"to:{recipient_email}"
        messages = self._search_emails(query, max_results)
        return [self._message_to_document(msg) for msg in messages]

    def get_emails_by_cc_participant(
        self, cc_participant: str, max_results: int = 50
    ) -> List[EmailDocument]:
        """Get emails where a specific person was CC'd.

        Args:
            cc_participant: Either an email address or person's name
            max_results: Maximum number of emails to return
        """
        cc_email = self._resolve_person_to_email(cc_participant)
        query = f"cc:{cc_email}"
        messages = self._search_emails(query, max_results)
        return [self._message_to_document(msg) for msg in messages]

    def get_emails_by_date_range(
        self, start_date: str, end_date: str, max_results: int = 50
    ) -> List[EmailDocument]:
        """Get emails within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            max_results: Maximum number of emails to return
        """
        # Gmail uses YYYY/MM/DD format for date queries
        start_formatted = start_date.replace("-", "/")
        end_formatted = end_date.replace("-", "/")

        query = f"after:{start_formatted} before:{end_formatted}"
        messages = self._search_emails(query, max_results)
        return [self._message_to_document(msg) for msg in messages]

    def get_emails_with_body_keyword(
        self, keyword: str, max_results: int = 50
    ) -> List[EmailDocument]:
        """Get emails containing a specific keyword in the body or subject."""
        # Use Gmail's search syntax to search in body and subject
        if keyword.strip():
            query = f'"{keyword}"'
        else:
            # If empty keyword, just get all emails
            query = ""
        messages = self._search_emails(query, max_results)
        return [self._message_to_document(msg) for msg in messages]


# Stateless tools using decorator
@GmailToolkit.tool(cache=True, ttl=timedelta(hours=1))
def get_recent_emails(days: int = 7) -> List[EmailDocument]:
    """Get recent emails from the last N days."""
    toolkit = GmailToolkit()

    # Use Gmail's newer_than syntax which is more reliable
    query = f"newer_than:{days}d"

    try:
        print(f"Recent emails query: '{query}'")  # Debug output

        results = (
            toolkit.service.users()
            .messages()
            .list(userId="me", q=query, maxResults=50)
            .execute()
        )

        messages = results.get("messages", [])
        print(f"Recent emails API returned {len(messages)} message IDs")  # Debug output

        # Get full message details
        documents = []
        if messages:
            for message in messages:
                full_msg = (
                    toolkit.service.users()
                    .messages()
                    .get(userId="me", id=message["id"], format="full")
                    .execute()
                )
                documents.append(toolkit._message_to_document(full_msg))

        return documents

    except Exception as e:
        print(f"Error getting recent emails: {e}")
        # Fallback to date range method
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        return toolkit.get_emails_by_date_range(start_str, end_str)


@GmailToolkit.tool(cache=True, ttl=timedelta(minutes=30))
def get_unread_emails() -> List[EmailDocument]:
    """Get all unread emails."""
    toolkit = GmailToolkit()

    try:
        # Search for unread emails
        results = (
            toolkit.service.users()
            .messages()
            .list(userId="me", q="is:unread", maxResults=100)
            .execute()
        )

        messages = results.get("messages", [])

        # Get full message details
        documents = []
        if messages:
            for message in messages:
                full_msg = (
                    toolkit.service.users()
                    .messages()
                    .get(userId="me", id=message["id"], format="full")
                    .execute()
                )
                documents.append(toolkit._message_to_document(full_msg))

        return documents

    except Exception as e:
        print(f"Error getting unread emails: {e}")
        return []
