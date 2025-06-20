"""Gmail toolkit for retrieving and searching emails."""

import logging
from typing import List

from praga_core.agents import PaginatedResponse, RetrieverToolkit
from praga_core.context import ServerContext

from ..pages.gmail import EmailPage
from ..services.gmail_service import GmailService
from .utils import resolve_person_to_email

logger = logging.getLogger(__name__)


class GmailToolkit(RetrieverToolkit):
    """Toolkit for retrieving emails from Gmail using Gmail service."""

    def __init__(self, context: ServerContext, gmail_service: GmailService):
        super().__init__(context)
        self.gmail_service = gmail_service

        # Register all email search tools
        self.register_tool(self.get_emails_by_sender)
        self.register_tool(self.get_emails_by_recipient)
        self.register_tool(self.get_emails_by_cc_participant)
        self.register_tool(self.get_emails_by_date_range)
        self.register_tool(self.get_emails_with_body_keyword)
        self.register_tool(self.get_recent_emails)
        self.register_tool(self.get_unread_emails)

        logger.info("Gmail toolkit initialized")

    @property
    def name(self) -> str:
        return "GmailToolkit"

    def _search_emails_paginated_response(
        self, query: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[EmailPage]:
        """Search emails and return a paginated response."""
        # Calculate page token by iterating through pages
        page_token = None
        if page > 0:
            current_token = None
            for _ in range(page):
                _, current_token = self.gmail_service.search_emails(
                    query, current_token, page_size
                )
                if not current_token:
                    # No more pages available
                    logger.debug(f"No more pages available at page {page}")
                    return PaginatedResponse(
                        results=[],
                        page_number=page,
                        has_next_page=False,
                    )
            page_token = current_token

        # Get the actual page data
        uris, next_page_token = self.gmail_service.search_emails(
            query, page_token, page_size
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
            page_number=page,
            has_next_page=bool(next_page_token),
        )

    def get_emails_by_sender(
        self, sender: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails from a specific sender.

        Args:
            sender: Email address or name of the sender
            page: Page number for pagination (0-based)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(sender, self.context)
        if not email:
            logger.warning(f"Could not resolve sender '{sender}' to email address")
            return PaginatedResponse(results=[], page_number=page, has_next_page=False)

        query = f"from:{email}"
        return self._search_emails_paginated_response(query, page)

    def get_emails_by_recipient(
        self, recipient: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails sent to a specific recipient.

        Args:
            recipient: Email address or name of the recipient
            page: Page number for pagination (0-based)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(recipient, self.context)
        if not email:
            logger.warning(
                f"Could not resolve recipient '{recipient}' to email address"
            )
            return PaginatedResponse(results=[], page_number=page, has_next_page=False)

        query = f"to:{email}"
        return self._search_emails_paginated_response(query, page)

    def get_emails_by_cc_participant(
        self, cc_participant: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails where a specific person was CC'd.

        Args:
            cc_participant: Email address or name of the CC participant
            page: Page number for pagination (0-based)
        """
        # Resolve person identifier to email address if needed
        email = resolve_person_to_email(cc_participant, self.context)
        if not email:
            logger.warning(
                f"Could not resolve CC participant '{cc_participant}' to email address"
            )
            return PaginatedResponse(results=[], page_number=page, has_next_page=False)

        query = f"cc:{email}"
        return self._search_emails_paginated_response(query, page)

    def get_emails_by_date_range(
        self, start_date: str, end_date: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails within a date range.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            page: Page number for pagination (0-based)
        """
        # Gmail uses YYYY/MM/DD format for date queries
        start_formatted = start_date.replace("-", "/")
        end_formatted = end_date.replace("-", "/")
        query = f"after:{start_formatted} before:{end_formatted}"
        return self._search_emails_paginated_response(query, page)

    def get_emails_with_body_keyword(
        self, keyword: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails containing a specific keyword in the body or subject.

        Args:
            keyword: Keyword to search for
            page: Page number for pagination (0-based)
        """
        query = keyword if keyword.strip() else ""
        return self._search_emails_paginated_response(query, page)

    def get_recent_emails(
        self, days: int = 7, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get recent emails from the last N days.

        Args:
            days: Number of days to look back
            page: Page number for pagination (0-based)
        """
        query = f"newer_than:{days}d"
        return self._search_emails_paginated_response(query, page)

    def get_unread_emails(self, page: int = 0) -> PaginatedResponse[EmailPage]:
        """Get all unread emails.

        Args:
            page: Page number for pagination (0-based)
        """
        query = "is:unread"
        return self._search_emails_paginated_response(query, page)
