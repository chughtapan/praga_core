"""Microsoft Outlook-specific email client implementation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BaseEmailClient
from pragweb.pages import EmailPage, EmailSummary, EmailThreadPage

from .auth import MicrosoftAuthManager
from .client import MicrosoftGraphClient


class OutlookEmailClient(BaseEmailClient):
    """Microsoft Outlook-specific email client implementation."""

    def __init__(self, auth_manager: MicrosoftAuthManager):
        self.auth_manager = auth_manager
        self.graph_client = MicrosoftGraphClient(auth_manager)

    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a single Outlook message by ID."""
        return await self.graph_client.get_message(message_id)

    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get an Outlook thread by ID."""
        # Microsoft Graph doesn't have the same thread concept as Gmail
        # Instead, we'll search for messages with the same conversation ID
        filter_query = f"conversationId eq '{thread_id}'"
        response = await self.graph_client.list_messages(
            folder="inbox",
            top=50,
            filter_query=filter_query,
            order_by="receivedDateTime desc",
        )

        # Create a thread-like structure
        messages = response.get("value", [])
        if not messages:
            raise ValueError(f"No messages found for thread {thread_id}")

        # Use the first message's subject as thread subject
        thread_subject = messages[0].get("subject", "")

        return {
            "id": thread_id,
            "subject": thread_subject,
            "messages": messages,
            "messageCount": len(messages),
        }

    async def search_messages(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for Outlook messages."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        if query:
            # Use Microsoft Graph search
            return await self.graph_client.list_messages(
                folder="inbox",
                top=max_results,
                skip=skip,
                search=query,
                order_by="receivedDateTime desc",
            )
        else:
            # List recent messages
            return await self.graph_client.list_messages(
                folder="inbox",
                top=max_results,
                skip=skip,
                order_by="receivedDateTime desc",
            )

    async def send_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an Outlook message."""
        # Build recipients
        to_recipients = [{"emailAddress": {"address": email}} for email in to]
        cc_recipients = [{"emailAddress": {"address": email}} for email in (cc or [])]
        bcc_recipients = [{"emailAddress": {"address": email}} for email in (bcc or [])]

        # Build message
        message_data = {
            "message": {
                "subject": subject,
                "body": {"contentType": "text", "content": body},
                "toRecipients": to_recipients,
                "ccRecipients": cc_recipients,
                "bccRecipients": bcc_recipients,
            }
        }

        # If replying to a thread, set the conversation ID
        if thread_id:
            message_data["message"]["conversationId"] = thread_id

        return await self.graph_client.send_message(message_data)

    async def reply_to_message(
        self, message_id: str, body: str, reply_all: bool = False
    ) -> Dict[str, Any]:
        """Reply to an Outlook message."""
        reply_data = {"message": {"body": {"contentType": "text", "content": body}}}

        if reply_all:
            # Use replyAll endpoint
            return await self.graph_client.post(
                f"me/messages/{message_id}/replyAll", data=reply_data
            )
        else:
            # Use reply endpoint
            return await self.graph_client.reply_to_message(message_id, reply_data)

    async def mark_as_read(self, message_id: str) -> bool:
        """Mark an Outlook message as read."""
        try:
            await self.graph_client.mark_message_as_read(message_id)
            return True
        except Exception:
            return False

    async def mark_as_unread(self, message_id: str) -> bool:
        """Mark an Outlook message as unread."""
        try:
            await self.graph_client.mark_message_as_unread(message_id)
            return True
        except Exception:
            return False

    def parse_message_to_email_page(
        self, message_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailPage:
        """Parse Outlook message data to EmailPage."""
        # Parse timestamps
        received_time = message_data.get("receivedDateTime", "")
        if received_time:
            time = datetime.fromisoformat(received_time.replace("Z", "+00:00"))
        else:
            time = datetime.now()

        # Parse sender
        sender_data = message_data.get("sender", {}).get("emailAddress", {})
        sender = sender_data.get("address", "")

        # Parse recipients
        recipients = []
        for recipient in message_data.get("toRecipients", []):
            email_address = recipient.get("emailAddress", {}).get("address", "")
            if email_address:
                recipients.append(email_address)

        # Parse CC recipients
        cc_list = []
        for cc_recipient in message_data.get("ccRecipients", []):
            email_address = cc_recipient.get("emailAddress", {}).get("address", "")
            if email_address:
                cc_list.append(email_address)

        # Parse BCC recipients
        bcc_list = []
        for bcc_recipient in message_data.get("bccRecipients", []):
            email_address = bcc_recipient.get("emailAddress", {}).get("address", "")
            if email_address:
                bcc_list.append(email_address)

        # Parse body
        body_data = message_data.get("body", {})
        body = body_data.get("content", "")

        # Parse labels/categories
        message_data.get("categories", [])

        # Parse importance
        message_data.get("importance", "normal")

        # Parse attachments
        if message_data.get("hasAttachments"):
            # Note: We'd need to make additional API calls to get attachment details
            pass

        return EmailPage(
            uri=page_uri,
            thread_id=message_data.get("conversationId", ""),
            subject=message_data.get("subject", ""),
            sender=sender,
            recipients=recipients,
            cc_list=cc_list,
            body=body,
            time=time,
            permalink=message_data.get("webLink", ""),
        )

    def parse_thread_to_thread_page(
        self, thread_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailThreadPage:
        """Parse Outlook thread data to EmailThreadPage."""
        messages = thread_data.get("messages", [])

        # Create email summaries
        email_summaries = []
        participants = set()

        for message in messages:
            # Parse sender
            sender_data = message.get("sender", {}).get("emailAddress", {})
            sender = sender_data.get("address", "")
            participants.add(sender)

            # Parse recipients
            recipients = []
            for recipient in message.get("toRecipients", []):
                email_address = recipient.get("emailAddress", {}).get("address", "")
                if email_address:
                    recipients.append(email_address)
                    participants.add(email_address)

            # Parse CC recipients
            cc_list = []
            for cc_recipient in message.get("ccRecipients", []):
                email_address = cc_recipient.get("emailAddress", {}).get("address", "")
                if email_address:
                    cc_list.append(email_address)
                    participants.add(email_address)

            # Parse timestamp
            received_time = message.get("receivedDateTime", "")
            if received_time:
                time = datetime.fromisoformat(received_time.replace("Z", "+00:00"))
            else:
                time = datetime.now()

            # Parse body
            body_data = message.get("body", {})
            body = body_data.get("content", "")

            email_summaries.append(
                EmailSummary(
                    uri=PageURI(
                        root=page_uri.root,
                        type="email",
                        id=f"microsoft:{message.get('id', '')}",
                        version=page_uri.version,
                    ),
                    sender=sender,
                    recipients=recipients,
                    cc_list=cc_list,
                    body=body,
                    time=time,
                )
            )

        # Find the latest message time
        latest_time = datetime.min
        for summary in email_summaries:
            if summary.time > latest_time:
                latest_time = summary.time

        # Parse labels from the first message
        if messages:
            messages[0].get("categories", [])

        return EmailThreadPage(
            uri=page_uri,
            thread_id=thread_data.get("id", ""),
            subject=thread_data.get("subject", ""),
            emails=email_summaries,
            permalink="",  # Microsoft doesn't provide thread permalinks
        )
