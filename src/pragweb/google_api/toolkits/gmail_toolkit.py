"""Gmail toolkit for retrieving and searching emails."""

import logging
from typing import List, Optional

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool

from ..pages.gmail import EmailPage
from ..services.gmail_service import GmailService
from .utils import resolve_person_to_email

logger = logging.getLogger(__name__)


class GmailToolkit(RetrieverToolkit):
    """Toolkit for retrieving emails from Gmail using Gmail service."""

    def __init__(self, gmail_service: GmailService):
        super().__init__()
        self.gmail_service = gmail_service

        logger.info("Gmail toolkit initialized")

    @property
    def name(self) -> str:
        return "GmailToolkit"

    def _search_emails_paginated_response(
        self, query: str, cursor: Optional[str] = None, page_size: int = 10
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
    def get_emails_by_sender(
        self, sender: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get emails from a specific sender.

        Args:
            sender: Email address or name of the sender
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(sender)
        if not email:
            logger.warning(f"Could not resolve sender '{sender}' to email address")
            return PaginatedResponse(results=[], next_cursor=None)

        query = f"from:{email}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_emails_by_recipient(
        self, recipient: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get emails sent to a specific recipient.

        Args:
            recipient: Email address or name of the recipient
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(recipient)
        if not email:
            logger.warning(
                f"Could not resolve recipient '{recipient}' to email address"
            )
            return PaginatedResponse(results=[], next_cursor=None)

        query = f"to:{email}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_emails_by_cc_participant(
        self, cc_participant: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get emails where a specific person was CC'd.

        Args:
            cc_participant: Email address or name of the CC participant
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(cc_participant)
        if not email:
            logger.warning(
                f"Could not resolve CC participant '{cc_participant}' to email address"
            )
            return PaginatedResponse(results=[], next_cursor=None)

        query = f"cc:{email}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_emails_by_date_range(
        self, start_date: str, end_date: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get emails within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            cursor: Cursor token for pagination (optional)
        """
        # Gmail uses YYYY/MM/DD format for date queries
        start_formatted = start_date.replace("-", "/")
        end_formatted = end_date.replace("-", "/")
        query = f"after:{start_formatted} before:{end_formatted}"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_emails_with_body_keyword(
        self, keyword: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get emails containing a specific keyword in the body or subject.

        Args:
            keyword: Keyword to search for
            cursor: Cursor token for pagination (optional)
        """
        query = keyword if keyword.strip() else ""
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_recent_emails(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get recent emails from the last N days.

        Args:
            days: Number of days to look back
            cursor: Cursor token for pagination (optional)
        """
        query = f"newer_than:{days}d"
        return self._search_emails_paginated_response(query, cursor)

    @tool()
    def get_unread_emails(
        self, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Get all unread emails.

        Args:
            cursor: Cursor token for pagination (optional)
        """
        query = "is:unread"
        return self._search_emails_paginated_response(query, cursor)
