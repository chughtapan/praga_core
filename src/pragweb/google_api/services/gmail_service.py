"""Gmail service for handling Gmail API interactions and page creation."""

import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple

from praga_core.context import ServerContext
from praga_core.types import PageURI

from ..auth import GoogleAuthManager
from ..pages.gmail import EmailPage
from ..pages.utils import GmailParser

logger = logging.getLogger(__name__)


class GmailService:
    """Service for Gmail API interactions and EmailPage creation."""

    def __init__(self, context: ServerContext):
        self.context = context
        self.root = context.root
        self.auth_manager = GoogleAuthManager()
        self.service = self.auth_manager.get_gmail_service()
        self.parser = GmailParser()

        # Register handler with context
        self.context.register_handler(self.name, self.create_page)
        logger.info("Gmail service initialized and handler registered")

    def create_page(self, email_id: str) -> EmailPage:
        """Create an EmailPage from a Gmail message ID - matches old EmailHandler.handle_email logic exactly."""
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

        # 3. Extract body content using parser (exact same as old handler)
        body = self.parser.extract_body(message.get("payload", {}))

        # 4. Parse date (exact same as old handler)
        date_str = headers.get("Date", "")
        email_time = parsedate_to_datetime(date_str) if date_str else datetime.now()

        # 5. Create permalink (exact same as old handler)
        thread_id = message.get("threadId", email_id)
        permalink = f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"

        # 6. Create URI and return complete document
        uri = PageURI(root=self.root, type="email", id=email_id, version=1)
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
            # Add in:inbox by default if not already present
            if "in:inbox" not in query.lower() and "in:" not in query.lower():
                query = f"{query} in:inbox" if query.strip() else "in:inbox"

            logger.debug(f"Gmail search query: '{query}', page_token: {page_token}")

            # Search for messages with pagination
            list_params = {"userId": "me", "q": query, "maxResults": page_size}
            if page_token:
                list_params["pageToken"] = page_token

            results = self.service.users().messages().list(**list_params).execute()
            messages = results.get("messages", [])
            next_page_token = results.get("nextPageToken")

            logger.debug(
                f"Gmail API returned {len(messages)} message IDs, next_token: {bool(next_page_token)}"
            )

            # Convert to PageURIs
            uris = [
                PageURI(root=self.root, type=self.name, id=msg["id"])
                for msg in messages
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching emails: {e}")
            raise

    @property
    def name(self) -> str:
        return "email"
