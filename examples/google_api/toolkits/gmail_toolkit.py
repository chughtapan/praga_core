"""Gmail toolkit for retrieving and searching emails."""

import os
import sys
from typing import Any, Dict, List, Optional

from praga_core.agents.tool import PaginatedResponse
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.gmail import EmailPage  # noqa: E402
from toolkits.google_base_toolkit import GoogleBaseToolkit  # noqa: E402


class GmailToolkit(GoogleBaseToolkit):
    """Toolkit for retrieving emails from Gmail using Google API."""

    def __init__(
        self, context: ServerContext, secrets_dir: Optional[str] = None
    ) -> None:
        """Initialize the Gmail toolkit with authentication."""
        super().__init__(context, secrets_dir)
        self._service = None
        self.register_tool(self.get_emails_by_sender)
        self.register_tool(self.get_emails_by_recipient)
        self.register_tool(self.get_emails_by_cc_participant)
        self.register_tool(self.get_emails_by_date_range)
        self.register_tool(self.get_emails_with_body_keyword)
        self.register_tool(self.get_recent_emails)
        self.register_tool(self.get_unread_emails)

    @property
    def name(self) -> str:
        return "GmailToolkit"

    @property
    def service(self) -> Any:
        """Lazy initialization of Gmail service."""
        if self._service is None:
            self._service = self.auth_manager.get_gmail_service()
        return self._service

    def _search_emails_paginated(
        self, query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Search emails with pagination support using Gmail API cursors.

        Returns:
            Tuple of (messages, next_page_token)
        """
        try:
            print(
                f"Gmail search query: '{query}', page_token: {page_token}"
            )  # Debug output

            # Search for messages with pagination
            list_params = {"userId": "me", "q": query, "maxResults": page_size}
            if page_token:
                list_params["pageToken"] = page_token

            results = self.service.users().messages().list(**list_params).execute()

            messages = results.get("messages", [])
            next_page_token = results.get("nextPageToken")
            print(
                f"Gmail API returned {len(messages)} message IDs, next_token: {bool(next_page_token)}"
            )  # Debug output

            # Get full message details for each message
            full_messages: List[Dict[str, Any]] = []
            if messages:
                for message in messages:
                    full_msg = (
                        self.service.users()
                        .messages()
                        .get(userId="me", id=message["id"], format="full")
                        .execute()
                    )
                    full_messages.append(full_msg)

            return full_messages, next_page_token

        except Exception as e:
            print(f"Error searching emails: {e}")
            return [], None

    def _search_emails_paginated_response(
        self, query: str, page: int = 0, page_size: int = 10
    ) -> PaginatedResponse[EmailPage]:
        """Search elogger = logging.getLogger(__name__)
        mails and return a paginated response.

                Args:
                    query: Gmail search query
                    page: Page number (0-based)
                    page_size: Number of emails per page

                Returns:
                    PaginatedResponse with email documents
        """
        try:
            # Add in:inbox by default if not already present to exclude archived/spam emails
            if "in:inbox" not in query.lower() and "in:" not in query.lower():
                query = f"{query} in:inbox" if query.strip() else "in:inbox"

            print(f"Gmail search query: '{query}', page: {page}")  # Debug output

            # Calculate page token - for now, we'll use a simple approach
            # In a real implementation, you'd want to cache page tokens
            page_token = None

            # If not the first page, we need to get to the right page
            # This is a simplified approach - in production you'd cache tokens
            if page > 0:
                # Skip to the desired page by fetching previous pages
                current_token = None
                for _ in range(page):
                    _, current_token = self._search_emails_paginated(
                        query, current_token, page_size
                    )
                    if not current_token:
                        # No more pages available
                        return PaginatedResponse(
                            results=[],
                            page_number=page,
                            has_next_page=False,
                            total_results=0,
                            token_count=0,
                        )
                page_token = current_token

            # Get the actual page data
            messages, next_page_token = self._search_emails_paginated(
                query, page_token, page_size
            )
            uris = [self.context.get_page_uri(msg["id"], EmailPage) for msg in messages]
            emails = list(map(self.context.get_page, uris))
            # Calculate token count
            total_tokens = sum(doc.metadata.token_count or 0 for doc in emails)

            return PaginatedResponse(
                results=emails,
                page_number=page,
                has_next_page=bool(next_page_token),
                total_results=None,
                token_count=total_tokens,
            )

        except Exception as e:
            print(f"Error in paginated email search: {e}")
            return PaginatedResponse(
                results=[],
                page_number=page,
                has_next_page=False,
                total_results=0,
                token_count=0,
            )

    def get_emails_by_sender(
        self, sender: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails from a specific sender.

        Args:
            sender: Either an email address or person's name
            page: Page number for pagination (0-based)
        """
        query = f"from:{sender}"
        return self._search_emails_paginated_response(query, page)

    def get_emails_by_recipient(
        self, recipient: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails sent to a specific recipient.

        Args:
            recipient: Either an email address or person's name
            page: Page number for pagination (0-based)
        """
        query = f"to:{recipient}"
        return self._search_emails_paginated_response(query, page)

    def get_emails_by_cc_participant(
        self, cc_participant: str, page: int = 0
    ) -> PaginatedResponse[EmailPage]:
        """Get emails where a specific person was CC'd.

        Args:
            cc_participant: Either an email address or person's name
            page: Page number for pagination (0-based)
        """
        query = f"cc:{cc_participant}"
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
        if keyword.strip():
            query = f"{keyword}"
        else:
            query = ""
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
