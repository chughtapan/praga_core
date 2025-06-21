"""Gmail service for handling Gmail API interactions and page creation."""

import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from .page import EmailPage
from .utils import GmailParser

logger = logging.getLogger(__name__)


class GmailService(ToolkitService):
    """Service for Gmail API interactions and EmailPage creation."""

    def __init__(self, api_client: GoogleAPIClient) -> None:
        super().__init__()
        self.api_client = api_client
        self.parser = GmailParser()

        # Register handlers using decorators
        self._register_handlers()
        logger.info("Gmail service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        @self.context.handler(self.name)
        def handle_email(email_id: str) -> EmailPage:
            return self.create_page(email_id)

    def create_page(self, email_id: str) -> EmailPage:
        """Create an EmailPage from a Gmail message ID - matches old EmailHandler.handle_email logic exactly."""
        # 1. Fetch message from Gmail API using shared client
        try:
            message = self.api_client.get_message(email_id)
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

        # 3. Extract body content using parser (exact same as old handler)
        body = self.parser.extract_body(message.get("payload", {}))

        # 4. Parse date (exact same as old handler)
        date_str = headers.get("Date", "")
        email_time = parsedate_to_datetime(date_str) if date_str else datetime.now()

        # 5. Create permalink (exact same as old handler)
        thread_id = message.get("threadId", email_id)
        permalink = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        # 6. Create URI and return complete document
        uri = PageURI(root=self.context.root, type="email", id=email_id, version=1)
        return EmailPage(
            uri=uri,
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

    def search_emails(
        self, query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search emails and return list of PageURIs and next page token."""
        try:
            messages, next_page_token = self.api_client.search_messages(
                query, page_token=page_token, page_size=page_size
            )

            logger.debug(
                f"Gmail API returned {len(messages)} message IDs, next_token: {bool(next_page_token)}"
            )

            # Convert to PageURIs
            uris = [
                PageURI(root=self.context.root, type=self.name, id=msg["id"])
                for msg in messages
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            raise

    @property
    def toolkit(self) -> "GmailToolkit":
        """Get the Gmail toolkit for this service."""
        return GmailToolkit(gmail_service=self)

    @property
    def name(self) -> str:
        return "email"


class GmailToolkit(RetrieverToolkit):
    """Toolkit for retrieving emails using Gmail service."""

    def __init__(self, gmail_service: GmailService):
        super().__init__()  # No explicit context - will use global context
        self.gmail_service = gmail_service

        logger.info("Gmail toolkit initialized")

    @property
    def name(self) -> str:
        return "GmailToolkit"

    def _search_emails_paginated_response(
        self,
        query: str,
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> PaginatedResponse[EmailPage]:
        """Search emails and return a paginated response."""
        # Get the page data using the cursor directly
        uris, next_page_token = self.gmail_service.search_emails(
            query, cursor, page_size
        )

        # Resolve URIs to pages using context - throw errors, don't fail silently
        pages: List[EmailPage] = []
        for uri in uris:
            page_obj = self.context.get_page(uri)
            if not isinstance(page_obj, EmailPage):
                raise TypeError(f"Expected EmailPage but got {type(page_obj)}")
            pages.append(page_obj)
        logger.debug(f"Successfully resolved {len(pages)} email pages")

        return PaginatedResponse(
            results=pages,
            next_cursor=next_page_token,
        )

    @tool()
    def search_emails_by_query(
        self, query: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails using Gmail query syntax.

        Args:
            query: Gmail search query (e.g. 'from:john@example.com subject:meeting')
            cursor: Cursor token for pagination (optional)
        """
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def search_emails_from_person(
        self, person: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails from a specific person.

        Args:
            person: Email address or name of the sender
            cursor: Cursor token for pagination (optional)
        """
        # Try to resolve person to email if it's a name
        from ..utils import resolve_person_to_email

        email = resolve_person_to_email(person)
        query = f"from:{email or person}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def search_emails_to_person(
        self, person: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails sent to a specific person.

        Args:
            person: Email address or name of the recipient
            cursor: Cursor token for pagination (optional)
        """
        # Try to resolve person to email if it's a name
        from ..utils import resolve_person_to_email

        email = resolve_person_to_email(person)
        query = f"to:{email or person}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def search_emails_by_subject(
        self, subject: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails by subject line.

        Args:
            subject: Subject text to search for
            cursor: Cursor token for pagination (optional)
        """
        query = f"subject:{subject}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_recent_emails(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get recent emails from the last N days.

        Args:
            days: Number of days to look back (default: 7)
            cursor: Cursor token for pagination (optional)
        """
        query = f"newer_than:{days}d"
        return self._search_emails_paginated_response(query, cursor)
