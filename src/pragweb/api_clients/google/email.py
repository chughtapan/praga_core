"""Google-specific email client implementation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BaseEmailClient
from pragweb.pages import EmailPage, EmailSummary, EmailThreadPage

from .auth import GoogleAuthManager
from .gmail_utils import GmailParser


class GoogleEmailClient(BaseEmailClient):
    """Google-specific email client implementation."""

    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self.parser = GmailParser()
        self._executor = ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="google-email-client"
        )

    @property
    def _gmail(self) -> Any:
        """Get Gmail service instance."""
        return self.auth_manager.get_gmail_service()

    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a single Gmail message by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            ),
        )
        return dict(result)

    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get a Gmail thread by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            ),
        )
        return dict(result)

    async def search_messages(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for Gmail messages."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=max_results,
                    pageToken=page_token,
                )
                .execute()
            ),
        )
        return dict(result)

    async def send_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a Gmail message."""
        # Build the message
        message = self.parser.build_message(
            to=to, subject=subject, body=body, cc=cc, bcc=bcc, thread_id=thread_id
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users().messages().send(userId="me", body=message).execute()
            ),
        )
        return dict(result)

    async def reply_to_message(
        self, message_id: str, body: str, reply_all: bool = False
    ) -> Dict[str, Any]:
        """Reply to a Gmail message."""
        # Get original message to extract thread_id and recipients
        original_message = await self.get_message(message_id)

        # Extract recipients from original message
        headers = original_message.get("payload", {}).get("headers", [])
        reply_to = []
        cc = []

        for header in headers:
            if header["name"] == "From":
                reply_to.append(header["value"])
            elif header["name"] == "Cc" and reply_all:
                cc.append(header["value"])

        # Create reply message
        reply_message = self.parser.build_reply_message(
            original_message=original_message, reply_body=body, reply_all=reply_all
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .send(userId="me", body=reply_message)
                .execute()
            ),
        )
        return dict(result)

    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a Gmail message as read."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .modify(userId="me", id=message_id, body={"removeLabelIds": ["UNREAD"]})
                .execute()
            ),
        )
        return True

    async def mark_as_unread(self, message_id: str) -> bool:
        """Mark a Gmail message as unread."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .modify(userId="me", id=message_id, body={"addLabelIds": ["UNREAD"]})
                .execute()
            ),
        )
        return True

    def parse_message_to_email_page(
        self, message_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailPage:
        """Parse Gmail message data to EmailPage."""
        parsed_data = self.parser.parse_message(message_data)

        return EmailPage(
            uri=page_uri,
            thread_id=parsed_data["thread_id"],
            subject=parsed_data["subject"],
            sender=parsed_data["sender"],
            recipients=parsed_data["recipients"],
            cc_list=parsed_data.get("cc", []),
            body=parsed_data["body"],
            time=parsed_data["time"],
            permalink=parsed_data["permalink"],
        )

    def parse_thread_to_thread_page(
        self, thread_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailThreadPage:
        """Parse Gmail thread data to EmailThreadPage."""
        parsed_data = self.parser.parse_thread(thread_data)

        # Convert message summaries
        email_summaries = []
        for msg_summary in parsed_data["messages"]:
            email_summaries.append(
                EmailSummary(
                    uri=PageURI(
                        root=page_uri.root,
                        type="email",
                        id=msg_summary["id"],
                        version=page_uri.version,
                    ),
                    sender=msg_summary["sender"],
                    recipients=msg_summary["recipients"],
                    cc_list=msg_summary.get("cc", []),
                    body=msg_summary["body"],
                    time=msg_summary["time"],
                )
            )

        return EmailThreadPage(
            uri=page_uri,
            thread_id=parsed_data["id"],
            subject=parsed_data["subject"],
            emails=email_summaries,
            permalink=parsed_data["permalink"],
        )
