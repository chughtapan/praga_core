"""Email orchestration service that coordinates between multiple providers."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from praga_core.agents import PaginatedResponse, tool
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import EmailPage, EmailThreadPage, PersonPage
from pragweb.toolkit_service import ToolkitService
from pragweb.utils import resolve_person_identifier

logger = logging.getLogger(__name__)


class EmailService(ToolkitService):
    """Orchestration service for email operations across multiple providers."""

    def __init__(self, providers: Dict[str, BaseProviderClient]):
        if not providers:
            raise ValueError("EmailService requires at least one provider")
        if len(providers) != 1:
            raise ValueError("EmailService requires exactly one provider")

        self.providers = providers
        self.provider_type = list(providers.keys())[0]
        self.provider_client = list(providers.values())[0]
        super().__init__()
        self._register_handlers()
        logger.info("Email service initialized with provider: %s", self.provider_type)

    @property
    def name(self) -> str:
        """Service name used for registration."""
        # Use natural service names based on provider
        provider_to_service = {"google": "gmail", "microsoft": "outlook"}
        return provider_to_service.get(
            self.provider_type, f"{self.provider_type}_email"
        )

    def _register_handlers(self) -> None:
        """Register page routes and actions with context."""
        ctx = self.context

        # Register page route handlers using service name
        service_name = self.name  # "gmail" or "outlook"
        email_type = f"{service_name}_email"
        thread_type = f"{service_name}_thread"

        @ctx.route(email_type, cache=True)
        async def handle_email(page_uri: PageURI) -> EmailPage:
            return await self.create_email_page(page_uri)

        @ctx.route(thread_type, cache=False)
        async def handle_thread(page_uri: PageURI) -> EmailThreadPage:
            return await self.create_thread_page(page_uri)

        # Register email actions
        @ctx.action()
        async def reply_to_email_thread(
            thread: EmailThreadPage,
            email: Optional[EmailPage] = None,
            recipients: Optional[List[PersonPage]] = None,
            cc_list: Optional[List[PersonPage]] = None,
            message: str = "",
        ) -> bool:
            """Reply to an email thread.

            Args:
                thread: The email thread to reply to
                email: Optional specific email in the thread to reply to (defaults to latest)
                recipients: Optional list of recipients (defaults to thread participants)
                cc_list: Optional list of CC recipients
                message: The reply message content

            Returns:
                True if the reply was sent successfully
            """
            try:
                # If no specific email provided, reply to the latest email in thread
                if email is None and thread.emails:
                    # Get the latest email URI from thread
                    latest_email_uri = thread.emails[-1].uri
                    # Fetch the full email page
                    page = await self.context.get_page(latest_email_uri)
                    if not isinstance(page, EmailPage):
                        logger.error(f"Failed to get email page for {latest_email_uri}")
                        return False
                    email = page

                if email is None:
                    logger.error("No email to reply to in thread")
                    return False

                # Determine recipients if not provided
                if recipients is None:
                    # Default to replying to the sender of the email being replied to
                    sender_email = email.sender
                    # Try to find person page for sender
                    try:
                        people_service = self.context.get_service("people")
                        if hasattr(people_service, "search_existing_records"):
                            sender_people = (
                                await people_service.search_existing_records(
                                    sender_email
                                )
                            )
                        else:
                            logger.warning(
                                "People service does not have search_existing_records method"
                            )
                            sender_people = []
                    except Exception as e:
                        logger.warning(f"Could not find people service or sender: {e}")
                        sender_people = []
                    recipients = sender_people[:1] if sender_people else []

                # Convert PersonPage objects to email addresses
                to_emails = [person.email for person in (recipients or [])]
                cc_emails = [person.email for person in (cc_list or [])]

                # Prepare the reply
                subject = email.subject
                if not subject.lower().startswith("re:"):
                    subject = f"Re: {subject}"

                # Send the reply using Gmail API
                await self.provider_client.email_client.send_message(
                    to=to_emails,
                    cc=cc_emails,
                    subject=subject,
                    body=message,
                    thread_id=thread.thread_id,
                )

                logger.info(f"Successfully sent reply to thread {thread.thread_id}")
                return True

            except Exception as e:
                logger.error(f"Failed to reply to thread: {e}")
                return False

        @ctx.action()
        async def send_email(
            person: PersonPage,
            additional_recipients: Optional[List[PersonPage]] = None,
            cc_list: Optional[List[PersonPage]] = None,
            subject: str = "",
            message: str = "",
        ) -> bool:
            """Send a new email.

            Args:
                person: Primary recipient
                additional_recipients: Additional recipients
                cc_list: CC recipients
                subject: Email subject
                message: Email message content

            Returns:
                True if the email was sent successfully
            """
            try:
                # Build recipient lists
                to_emails = [person.email]
                if additional_recipients:
                    to_emails.extend([p.email for p in additional_recipients])

                cc_emails = [p.email for p in (cc_list or [])]

                # Send the email using Gmail API
                await self.provider_client.email_client.send_message(
                    to=to_emails,
                    subject=subject,
                    body=message,
                    cc=cc_emails,
                    bcc=[],
                )

                logger.info(f"Successfully sent email to {', '.join(to_emails)}")
                return True

            except Exception as e:
                logger.error(f"Failed to send email: {e}")
                return False

    async def create_email_page(self, page_uri: PageURI) -> EmailPage:
        """Create an EmailPage from a URI."""
        # Extract message ID from URI
        message_id = page_uri.id

        # Get the first (and only) provider for this service
        provider = list(self.providers.values())[0] if self.providers else None
        if not provider:
            raise ValueError("No provider available for service")

        try:
            # Get message data from provider
            message_data = await provider.email_client.get_message(message_id)

            # Parse to EmailPage
            return provider.email_client.parse_message_to_email_page(
                message_data, page_uri
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch message {message_id}: {e}")

    async def create_thread_page(self, page_uri: PageURI) -> EmailThreadPage:
        """Create an EmailThreadPage from a URI."""
        # Extract thread ID from URI
        thread_id = page_uri.id

        # Get the first (and only) provider for this service
        provider = list(self.providers.values())[0] if self.providers else None
        if not provider:
            raise ValueError("No provider available for service")

        try:
            # Get thread data from provider
            thread_data = await provider.email_client.get_thread(thread_id)

            # Parse to EmailThreadPage
            return provider.email_client.parse_thread_to_thread_page(
                thread_data, page_uri
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch thread {thread_id}: {e}")

    async def _search_emails_gmail(
        self, query: str, cursor: Optional[str] = None, page_size: int = 10
    ) -> tuple[list[PageURI], Optional[str]]:
        """Search emails using Gmail API."""
        # Always add inbox filter for Gmail
        inbox_query = f"in:inbox {query}" if query else "in:inbox"

        search_result = await self.provider_client.email_client.search_messages(
            query=inbox_query, page_token=cursor, max_results=page_size
        )
        messages = search_result.get("messages", [])
        next_token = search_result.get("nextPageToken")

        uris = [
            PageURI(root=self.context.root, type=f"{self.name}_email", id=msg["id"])
            for msg in messages
        ]

        return uris, next_token

    async def _search_emails_microsoft(
        self,
        content_query: Optional[str] = None,
        metadata_query: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> tuple[list[PageURI], Optional[str]]:
        """Search emails using Microsoft Graph API."""
        # Always search in inbox folder only
        search_result = await self.provider_client.email_client.graph_client.list_messages(  # type: ignore
            folder="inbox",
            top=page_size,
            skip=int(cursor) if cursor else 0,
            filter_query=metadata_query,
            search=content_query,
            order_by="receivedDateTime desc",
        )

        messages = search_result.get("value", [])
        next_token = str(int(cursor or 0) + len(messages)) if messages else None

        uris = [
            PageURI(root=self.context.root, type=f"{self.name}_email", id=msg["id"])
            for msg in messages
        ]

        return uris, next_token

    async def _search_emails(
        self,
        content_query: Optional[str] = None,
        metadata_query: Optional[str] = None,
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> PaginatedResponse[EmailPage]:
        """Search emails and return a paginated response."""
        if self.provider_type == "microsoft":
            uris, next_page_token = await self._search_emails_microsoft(
                content_query, metadata_query, cursor, page_size
            )
        else:
            # For Gmail, combine queries
            combined_query = " ".join(filter(None, [metadata_query, content_query]))
            uris, next_page_token = await self._search_emails_gmail(
                combined_query, cursor, page_size
            )

        # Resolve URIs to pages using context async - throw errors, don't fail silently
        pages = await self.context.get_pages(uris)

        # Type check the results
        for page_obj in pages:
            if not isinstance(page_obj, EmailPage):
                raise TypeError(f"Expected EmailPage but got {type(page_obj)}")

        logger.debug(f"Successfully resolved {len(pages)} email pages")

        return PaginatedResponse(
            results=pages,  # type: ignore
            next_cursor=next_page_token,
        )

    @tool()
    async def search_emails_from_person(
        self, person: str, content: Optional[str] = None, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails from a specific person.

        Args:
            person: Email address or name of the sender
            content: Additional content to search for in the email content (optional)
            cursor: Cursor token for pagination (optional)
        """
        # Try to resolve person to email if it's a name
        email_addr = resolve_person_identifier(person)

        if self.provider_type == "microsoft":
            # Microsoft uses OData filter syntax for from
            metadata_query = f"from/emailAddress/address eq '{email_addr}'"
        else:
            # Gmail uses from: syntax
            metadata_query = f'from:"{email_addr}"'

        return await self._search_emails(
            content_query=content, metadata_query=metadata_query, cursor=cursor
        )

    @tool()
    async def search_emails_to_person(
        self, person: str, content: Optional[str] = None, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails sent to a specific person.

        Args:
            person: Email address or name of the recipient
            content: Additional content to search for in the email content (optional)
            cursor: Cursor token for pagination (optional)
        """
        # Try to resolve person to email if it's a name
        email_addr = resolve_person_identifier(person)

        if self.provider_type == "microsoft":
            # Microsoft uses OData filter syntax for recipients
            # Note: This is complex as we need to check both toRecipients and ccRecipients collections
            metadata_query = f"toRecipients/any(r:r/emailAddress/address eq '{email_addr}') or ccRecipients/any(r:r/emailAddress/address eq '{email_addr}')"
        else:
            # Gmail uses to: and cc: syntax
            metadata_query = f'to:"{email_addr}" OR cc:"{email_addr}"'

        return await self._search_emails(
            content_query=content, metadata_query=metadata_query, cursor=cursor
        )

    @tool()
    async def search_emails_by_content(
        self, content: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[EmailPage]:
        """Search emails by content in subject line or body.

        Args:
            content: Text to search for in subject or body
            cursor: Cursor token for pagination (optional)
        """
        # Content search works the same for both providers
        return await self._search_emails(content_query=content, cursor=cursor)

    @tool()
    async def get_recent_emails(
        self,
        days: int = 7,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[EmailPage]:
        """Get recent emails from the last N days.

        Args:
            days: Number of days to look back (default: 7)
            cursor: Cursor token for pagination (optional)
        """
        if self.provider_type == "microsoft":
            # Microsoft uses ISO date format in filter
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            metadata_query = (
                f"receivedDateTime ge {cutoff_date.isoformat().replace('+00:00', 'Z')}"
            )
            return await self._search_emails(
                metadata_query=metadata_query, cursor=cursor
            )
        else:
            # Gmail uses newer_than syntax
            metadata_query = f"newer_than:{days}d"
            return await self._search_emails(
                metadata_query=metadata_query, cursor=cursor
            )

    @tool()
    async def get_unread_emails(
        self,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[EmailPage]:
        """Get unread emails."""
        if self.provider_type == "microsoft":
            # Microsoft uses OData filter syntax
            metadata_query = "isRead eq false"
            return await self._search_emails(
                metadata_query=metadata_query, cursor=cursor
            )
        else:
            # Gmail uses is:unread syntax
            metadata_query = "is:unread"
            return await self._search_emails(
                metadata_query=metadata_query, cursor=cursor
            )
