"""Tests for Email service email actions with new architecture."""

from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import PersonPage
from pragweb.services import EmailService


class MockGmailClient:
    """Mock Gmail client for testing."""

    def __init__(self):
        self.messages = {}
        self.threads = {}

    async def get_message(self, message_id: str):
        """Mock get message."""
        return {
            "id": message_id,
            "threadId": f"thread_{message_id}",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "To", "value": "recipient@example.com"},
                    {"name": "Date", "value": "Thu, 15 Jun 2023 10:30:00 +0000"},
                ]
            },
        }

    async def get_thread(self, thread_id: str):
        """Mock get thread."""
        return {
            "id": thread_id,
            "messages": [
                {
                    "id": f"msg_{thread_id}",
                    "payload": {
                        "headers": [
                            {"name": "Subject", "value": "Test Subject"},
                            {"name": "From", "value": "sender@example.com"},
                            {"name": "To", "value": "recipient@example.com"},
                            {
                                "name": "Date",
                                "value": "Thu, 15 Jun 2023 10:30:00 +0000",
                            },
                        ]
                    },
                }
            ],
        }

    async def send_message(self, **kwargs):
        """Mock send message."""
        return {"id": "sent_msg_id"}

    async def mark_as_read(self, message_id: str) -> bool:
        """Mock mark as read."""
        return True

    async def mark_as_unread(self, message_id: str) -> bool:
        """Mock mark as unread."""
        return True

    def parse_message_to_email_page(self, message_data, page_uri):
        """Mock parse message to email page."""
        from datetime import datetime, timezone

        from pragweb.pages import EmailPage

        headers = {
            h["name"]: h["value"]
            for h in message_data.get("payload", {}).get("headers", [])
        }

        return EmailPage(
            uri=page_uri,
            thread_id=message_data.get("threadId", "test_thread"),
            subject=headers.get("Subject", ""),
            sender=headers.get("From", ""),
            recipients=(
                [email.strip() for email in headers.get("To", "").split(",")]
                if headers.get("To")
                else []
            ),
            body="Test email body content",
            body_html=None,
            time=datetime.now(timezone.utc),
            permalink=f"https://mail.google.com/mail/u/0/#inbox/{message_data.get('threadId', 'test_thread')}",
        )

    def parse_thread_to_thread_page(self, thread_data, page_uri):
        """Mock parse thread to thread page."""
        from datetime import datetime, timezone

        from pragweb.pages import EmailSummary, EmailThreadPage

        messages = thread_data.get("messages", [])
        if not messages:
            raise ValueError(
                f"Thread {thread_data.get('id', 'unknown')} contains no messages"
            )

        # Get subject from first message
        first_message = messages[0]
        headers = {
            h["name"]: h["value"]
            for h in first_message.get("payload", {}).get("headers", [])
        }
        subject = headers.get("Subject", "")

        # Create email summaries
        email_summaries = []
        for msg in messages:
            msg_headers = {
                h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
            }

            email_uri = page_uri.model_copy(
                update={"type": "gmail_email", "id": msg["id"]}
            )

            email_summary = EmailSummary(
                uri=email_uri,
                sender=msg_headers.get("From", ""),
                recipients=(
                    [email.strip() for email in msg_headers.get("To", "").split(",")]
                    if msg_headers.get("To")
                    else []
                ),
                body="Email body content",
                time=datetime.now(timezone.utc),
            )
            email_summaries.append(email_summary)

        return EmailThreadPage(
            uri=page_uri,
            thread_id=thread_data.get("id", "test_thread"),
            subject=subject,
            emails=email_summaries,
            participants=[email.sender for email in email_summaries],
            last_message_time=datetime.now(timezone.utc),
            message_count=len(email_summaries),
            permalink=f"https://mail.google.com/mail/u/0/#inbox/{thread_data.get('id', 'test_thread')}",
        )


class MockGoogleProviderClient(BaseProviderClient):
    """Mock Google provider client."""

    def __init__(self):
        super().__init__(Mock())
        self._email_client = MockGmailClient()

    @property
    def email_client(self):
        return self._email_client

    @property
    def calendar_client(self):
        return Mock()

    @property
    def people_client(self):
        mock_people = Mock()

        # Map person IDs to their data
        person_data_map = {
            "person1": {
                "resourceName": "people/person1",
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}],
            },
            "person2": {
                "resourceName": "people/person2",
                "names": [{"displayName": "Jane Smith"}],
                "emailAddresses": [{"value": "jane@example.com"}],
            },
            "person3": {
                "resourceName": "people/person3",
                "names": [{"displayName": "Bob Wilson"}],
                "emailAddresses": [{"value": "bob@example.com"}],
            },
            "person4": {
                "resourceName": "people/person4",
                "names": [{"displayName": "Alice Brown"}],
                "emailAddresses": [{"value": "alice@example.com"}],
            },
        }

        async def mock_get_contact(person_id):
            return person_data_map.get(
                person_id,
                {
                    "resourceName": f"people/{person_id}",
                    "names": [{"displayName": "Test Person"}],
                    "emailAddresses": [{"value": "test@example.com"}],
                },
            )

        def mock_parse_contact(contact_data, page_uri):
            email = contact_data.get("emailAddresses", [{}])[0].get(
                "value", "test@example.com"
            )
            display_name = contact_data.get("names", [{}])[0].get(
                "displayName", "Test Person"
            )
            name_parts = display_name.split(" ", 1)
            first_name = name_parts[0] if name_parts else "Test"
            last_name = name_parts[1] if len(name_parts) > 1 else "Person"

            return PersonPage(
                uri=page_uri,
                provider_person_id=contact_data.get(
                    "resourceName", "test_person"
                ).replace("people/", ""),
                first_name=first_name,
                last_name=last_name,
                email=email,
            )

        mock_people.get_contact = mock_get_contact
        mock_people.parse_contact_to_person_page = mock_parse_contact
        return mock_people

    @property
    def documents_client(self):
        return Mock()

    async def test_connection(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "google"


class TestEmailServiceActions:
    """Test suite for EmailService actions with new architecture."""

    @pytest.fixture
    async def service(self):
        """Create service with test context and mock providers."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create services - need both Email and People services for actions to work
        from pragweb.services import PeopleService

        email_service = EmailService(providers)
        PeopleService(providers)  # Created for side effects

        yield email_service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_reply_to_email_thread_action_with_specific_email(self, service):
        """Test reply_to_email_thread action with specific email to reply to."""
        # Import required page types
        from datetime import datetime, timezone

        from pragweb.pages import EmailPage, EmailSummary, EmailThreadPage

        # Create test data
        thread_uri = PageURI(
            root="test://example", type="gmail_thread", id="thread123", version=1
        )
        email_uri = PageURI(
            root="test://example", type="gmail_email", id="msg123", version=1
        )

        # Create thread page
        current_time = datetime.now(timezone.utc)
        thread_page = EmailThreadPage(
            uri=thread_uri,
            thread_id="thread123",
            subject="Test Thread",
            participants=["sender@example.com", "recipient@example.com"],
            emails=[
                EmailSummary(
                    uri=email_uri,
                    sender="sender@example.com",
                    recipients=["recipient@example.com"],
                    body="Test email content",
                    time=current_time,
                )
            ],
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
            last_message_time=current_time,
            message_count=1,
        )

        # Create email page
        email_page = EmailPage(
            uri=email_uri,
            thread_id="thread123",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            body="Test email body",
            body_html=None,
            time=datetime.now(timezone.utc),
            permalink="https://mail.google.com/mail/u/0/#inbox/msg123",
        )

        # Create person pages for recipients
        person1 = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person1", version=1),
            provider_person_id="person1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )

        person2 = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person2", version=1),
            provider_person_id="person2",
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
        )

        # Mock the email service methods to return our test pages
        async def mock_create_email_page(page_uri):
            if page_uri == email_uri:
                return email_page
            raise ValueError(f"Unknown email URI: {page_uri}")

        async def mock_create_thread_page(page_uri):
            if page_uri == thread_uri:
                return thread_page
            raise ValueError(f"Unknown thread URI: {page_uri}")

        service.create_email_page = mock_create_email_page
        service.create_thread_page = mock_create_thread_page

        # Mock send_message to succeed
        service.providers["google"].email_client.send_message = AsyncMock(
            return_value={"id": "sent_msg_id"}
        )

        # Test the action through context
        context = service.context

        result = await context.invoke_action(
            "reply_to_email_thread",
            {
                "thread": thread_uri,
                "email": email_uri,
                "recipients": [person1.uri],
                "cc_list": [person2.uri],
                "message": "This is my reply message",
            },
        )

        # Verify the result
        assert result["success"] is True

        # Verify send_message was called correctly
        service.providers["google"].email_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_reply_to_email_thread_action_without_specific_email(self, service):
        """Test reply_to_email_thread action replying to latest email in thread."""
        # Create test data
        thread_uri = PageURI(
            root="test://example", type="gmail_thread", id="thread123", version=1
        )

        # Mock send_message to succeed
        service.providers["google"].email_client.send_message = AsyncMock(
            return_value={"id": "sent_msg_id"}
        )

        # Test the action through context
        context = service.context
        result = await context.invoke_action(
            "reply_to_email_thread",
            {
                "thread": thread_uri,
                "message": "Reply to the thread",
            },
        )

        # Verify the result
        assert result["success"] is True

        # Verify send_message was called
        service.providers["google"].email_client.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_email_action_basic(self, service):
        """Test send_email action with basic parameters."""
        # Create person page
        primary_recipient = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person1", version=1),
            provider_person_id="person1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )

        # Mock send_message to succeed
        service.providers["google"].email_client.send_message = AsyncMock(
            return_value={"id": "sent_msg_id"}
        )

        # Test the action through context
        context = service.context
        result = await context.invoke_action(
            "send_email",
            {
                "person": primary_recipient.uri,
                "subject": "Test Email Subject",
                "message": "This is the email body",
            },
        )

        # Verify the result
        assert result["success"] is True

        # Verify send_message was called correctly
        service.providers["google"].email_client.send_message.assert_called_once_with(
            to=["john@example.com"],
            subject="Test Email Subject",
            body="This is the email body",
            cc=[],
            bcc=[],
        )

    @pytest.mark.asyncio
    async def test_send_email_action_with_multiple_recipients(self, service):
        """Test send_email action with multiple recipients and CC."""
        # Create person pages
        primary = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person1", version=1),
            provider_person_id="person1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )

        additional1 = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person2", version=1),
            provider_person_id="person2",
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
        )

        additional2 = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person3", version=1),
            provider_person_id="person3",
            first_name="Bob",
            last_name="Wilson",
            email="bob@example.com",
        )

        cc_person = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person4", version=1),
            provider_person_id="person4",
            first_name="Alice",
            last_name="Brown",
            email="alice@example.com",
        )

        # Store pages in cache so they can be retrieved by the action
        await service.context.page_cache.store(primary)
        await service.context.page_cache.store(additional1)
        await service.context.page_cache.store(additional2)
        await service.context.page_cache.store(cc_person)

        # Mock send_message to succeed
        service.providers["google"].email_client.send_message = AsyncMock(
            return_value={"id": "sent_msg_id"}
        )

        # Test the action through context
        context = service.context
        result = await context.invoke_action(
            "send_email",
            {
                "person": primary.uri,
                "additional_recipients": [additional1.uri, additional2.uri],
                "cc_list": [cc_person.uri],
                "subject": "Group Email",
                "message": "Email to multiple people",
            },
        )

        # Verify the result
        assert result["success"] is True

        # Verify send_message was called with all recipients
        service.providers["google"].email_client.send_message.assert_called_once_with(
            to=["john@example.com", "jane@example.com", "bob@example.com"],
            cc=["alice@example.com"],
            subject="Group Email",
            body="Email to multiple people",
            bcc=[],
        )

    @pytest.mark.asyncio
    async def test_send_email_action_failure(self, service):
        """Test send_email action handles send failure."""
        # Create person page
        recipient = PersonPage(
            uri=PageURI(root="test://example", type="person", id="person1", version=1),
            provider_person_id="person1",
            first_name="John",
            last_name="Doe",
            email="john@example.com",
        )

        # Mock send_message to fail
        service.providers["google"].email_client.send_message = AsyncMock(
            side_effect=Exception("Send failed")
        )

        # Test the action through context
        context = service.context
        result = await context.invoke_action(
            "send_email",
            {
                "person": recipient.uri,
                "subject": "Test Email",
                "message": "Test body",
            },
        )

        # Verify it returns False on failure
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_action_registration(self, service):
        """Test that actions are properly registered with the context."""
        context = service.context

        # Verify actions are registered
        assert "reply_to_email_thread" in context._actions
        assert "send_email" in context._actions
