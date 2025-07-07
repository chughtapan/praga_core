"""Tests for Gmail service email actions."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.gmail import (
    EmailPage,
    EmailSummary,
    EmailThreadPage,
    GmailService,
)
from pragweb.google_api.people import PersonPage


class TestGmailActions:
    """Test suite for Gmail service actions."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing global context first
        clear_global_context()

        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_context._actions = {}

        # Mock the register_service method
        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service

        # Mock create_page_uri to return predictable URIs
        self.mock_context.create_page_uri = AsyncMock(
            side_effect=lambda page_type, type_path, id, version=None: PageURI(
                root="test-root", type=type_path, id=id, version=version or 1
            )
        )

        # Mock get_pages for action executor
        self.mock_context.get_pages = AsyncMock()
        self.mock_context.get_page = AsyncMock()

        # Mock get_service to return people service when needed
        from pragweb.google_api.people.service import PeopleService

        self.mock_people_service = Mock(spec=PeopleService)
        self.mock_people_service.search_existing_records = AsyncMock()

        def mock_get_service(name):
            if name == "people":
                return self.mock_people_service
            raise ValueError(f"Unknown service: {name}")

        self.mock_context.get_service = mock_get_service

        # Mock route decorator (for handler registration)
        def mock_route_decorator(path, cache=True):
            def decorator(func):
                return func

            return decorator

        self.mock_context.route = mock_route_decorator

        # Track registered actions separately
        self.registered_actions = {}

        # Mock action decorator
        def mock_action_decorator(name=None):
            def decorator(func):
                action_name = name if name is not None else func.__name__
                self.registered_actions[action_name] = func
                return func

            return decorator

        self.mock_context.action = mock_action_decorator

        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()
        self.mock_api_client.get_message = AsyncMock()
        self.mock_api_client.search_messages = AsyncMock()
        self.mock_api_client.get_thread = AsyncMock()
        self.mock_api_client.send_message = AsyncMock()

        self.service = GmailService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    @pytest.mark.asyncio
    async def test_reply_to_email_thread_action_with_specific_email(self):
        """Test reply_to_email_thread action with specific email to reply to."""
        # Create test data
        thread_uri = PageURI(
            root="test-root", type="email_thread", id="thread123", version=1
        )
        email_uri = PageURI(root="test-root", type="email", id="msg123", version=1)

        thread = EmailThreadPage(
            uri=thread_uri,
            thread_id="thread123",
            subject="Test Thread",
            emails=[
                EmailSummary(
                    uri=email_uri,
                    sender="sender@example.com",
                    recipients=["recipient@example.com"],
                    body="Test email body",
                    time=datetime.now(),
                )
            ],
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        email = EmailPage(
            uri=email_uri,
            message_id="msg123",
            thread_id="thread123",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            body="Test email body",
            time=datetime.now(),
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        # Create person pages for recipients
        person1 = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person1", version=1),
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        person2 = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person2", version=1),
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            source="people_api",
        )

        # Mock send_message to succeed
        self.mock_api_client.send_message.return_value = {"id": "sent_msg_id"}

        # Call the internal action method directly
        result = await self.service._reply_to_thread_internal(
            thread=thread,
            email=email,
            recipients=[person1],
            cc_list=[person2],
            message="This is my reply message",
        )

        # Verify the result
        assert result is True

        # Verify send_message was called correctly
        self.mock_api_client.send_message.assert_called_once_with(
            to=["john@example.com"],
            cc=["jane@example.com"],
            subject="Re: Test Subject",
            body="This is my reply message",
            thread_id="thread123",
            references="msg123",
            in_reply_to="msg123",
        )

    @pytest.mark.asyncio
    async def test_reply_to_email_thread_action_without_specific_email(self):
        """Test reply_to_email_thread action replying to latest email in thread."""
        # Create test data
        thread_uri = PageURI(
            root="test-root", type="email_thread", id="thread123", version=1
        )
        email_uri1 = PageURI(root="test-root", type="email", id="msg1", version=1)
        email_uri2 = PageURI(root="test-root", type="email", id="msg2", version=1)

        thread = EmailThreadPage(
            uri=thread_uri,
            thread_id="thread123",
            subject="Test Thread",
            emails=[
                EmailSummary(
                    uri=email_uri1,
                    sender="sender1@example.com",
                    recipients=["recipient@example.com"],
                    body="First email",
                    time=datetime.now(),
                ),
                EmailSummary(
                    uri=email_uri2,
                    sender="sender2@example.com",
                    recipients=["recipient@example.com"],
                    body="Second email",
                    time=datetime.now(),
                ),
            ],
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        latest_email = EmailPage(
            uri=email_uri2,
            message_id="msg2",
            thread_id="thread123",
            subject="Re: Test Subject",
            sender="sender2@example.com",
            recipients=["recipient@example.com"],
            body="Second email",
            time=datetime.now(),
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        # Mock get_page to return the latest email
        self.mock_context.get_page.return_value = latest_email

        # Mock people service to find sender
        sender_person = PersonPage(
            uri=PageURI(root="test-root", type="person", id="sender_person", version=1),
            first_name="Sender",
            last_name="Two",
            email="sender2@example.com",
            source="emails",
        )
        self.mock_people_service.search_existing_records.return_value = [sender_person]

        # Mock send_message to succeed
        self.mock_api_client.send_message.return_value = {"id": "sent_msg_id"}

        # Call the internal action method directly without specifying email
        result = await self.service._reply_to_thread_internal(
            thread=thread,
            email=None,
            recipients=None,  # Should default to sender of latest email
            cc_list=None,
            message="Reply to the thread",
        )

        # Verify the result
        assert result is True

        # Verify get_page was called for latest email
        self.mock_context.get_page.assert_called_once_with(email_uri2)

        # Verify people service was called to find sender
        self.mock_people_service.search_existing_records.assert_called_once_with(
            "sender2@example.com"
        )

        # Verify send_message was called correctly
        self.mock_api_client.send_message.assert_called_once_with(
            to=["sender2@example.com"],
            cc=[],
            subject="Re: Test Subject",
            body="Reply to the thread",
            thread_id="thread123",
            references="msg2",
            in_reply_to="msg2",
        )

    @pytest.mark.asyncio
    async def test_reply_to_email_thread_action_handles_re_prefix(self):
        """Test that reply_to_email_thread doesn't add duplicate Re: prefix."""
        # Create email with subject already having Re:
        email = EmailPage(
            uri=PageURI(root="test-root", type="email", id="msg123", version=1),
            message_id="msg123",
            thread_id="thread123",
            subject="Re: Already a reply",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            body="Test email body",
            time=datetime.now(),
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        thread = EmailThreadPage(
            uri=PageURI(
                root="test-root", type="email_thread", id="thread123", version=1
            ),
            thread_id="thread123",
            subject="Re: Already a reply",
            emails=[],
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        # Mock send_message to succeed
        self.mock_api_client.send_message.return_value = {"id": "sent_msg_id"}

        # Verify the registered action exists
        assert "reply_to_email_thread" in self.registered_actions

        # Call the action
        await self.service._reply_to_thread_internal(
            thread=thread,
            email=email,
            recipients=[],
            cc_list=None,
            message="Reply message",
        )

        # Verify subject doesn't have double Re:
        call_args = self.mock_api_client.send_message.call_args[1]
        assert call_args["subject"] == "Re: Already a reply"

    @pytest.mark.asyncio
    async def test_reply_to_email_thread_action_failure(self):
        """Test reply_to_email_thread action handles send failure."""
        # Create test data
        email = EmailPage(
            uri=PageURI(root="test-root", type="email", id="msg123", version=1),
            message_id="msg123",
            thread_id="thread123",
            subject="Test Subject",
            sender="sender@example.com",
            recipients=["recipient@example.com"],
            body="Test email body",
            time=datetime.now(),
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        thread = EmailThreadPage(
            uri=PageURI(
                root="test-root", type="email_thread", id="thread123", version=1
            ),
            thread_id="thread123",
            subject="Test Subject",
            emails=[],
            permalink="https://mail.google.com/mail/u/0/#inbox/thread123",
        )

        # Mock send_message to fail
        self.mock_api_client.send_message.side_effect = Exception("Send failed")

        # Verify the registered action exists
        assert "reply_to_email_thread" in self.registered_actions

        # Call the action
        result = await self.service._reply_to_thread_internal(
            thread=thread,
            email=email,
            recipients=[],
            cc_list=None,
            message="Reply message",
        )

        # Verify it returns False on failure
        assert result is False

    @pytest.mark.asyncio
    async def test_send_email_action_basic(self):
        """Test send_email action with basic parameters."""
        # Create person pages
        primary_recipient = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person1", version=1),
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        # Mock send_message to succeed
        self.mock_api_client.send_message.return_value = {"id": "sent_msg_id"}

        # Call the internal action method directly
        result = await self.service._send_email_internal(
            person=primary_recipient,
            additional_recipients=None,
            cc_list=None,
            subject="Test Email Subject",
            message="This is the email body",
        )

        # Verify the result
        assert result is True

        # Verify send_message was called correctly
        self.mock_api_client.send_message.assert_called_once_with(
            to=["john@example.com"],
            cc=[],
            subject="Test Email Subject",
            body="This is the email body",
        )

    @pytest.mark.asyncio
    async def test_send_email_action_with_multiple_recipients(self):
        """Test send_email action with multiple recipients and CC."""
        # Create person pages
        primary = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person1", version=1),
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        additional1 = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person2", version=1),
            first_name="Jane",
            last_name="Smith",
            email="jane@example.com",
            source="people_api",
        )

        additional2 = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person3", version=1),
            first_name="Bob",
            last_name="Wilson",
            email="bob@example.com",
            source="people_api",
        )

        cc_person = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person4", version=1),
            first_name="Alice",
            last_name="Brown",
            email="alice@example.com",
            source="people_api",
        )

        # Mock send_message to succeed
        self.mock_api_client.send_message.return_value = {"id": "sent_msg_id"}

        # Call the internal action method directly
        result = await self.service._send_email_internal(
            person=primary,
            additional_recipients=[additional1, additional2],
            cc_list=[cc_person],
            subject="Group Email",
            message="Email to multiple people",
        )

        # Verify the result
        assert result is True

        # Verify send_message was called with all recipients
        self.mock_api_client.send_message.assert_called_once_with(
            to=["john@example.com", "jane@example.com", "bob@example.com"],
            cc=["alice@example.com"],
            subject="Group Email",
            body="Email to multiple people",
        )

    @pytest.mark.asyncio
    async def test_send_email_action_failure(self):
        """Test send_email action handles send failure."""
        # Create person page
        recipient = PersonPage(
            uri=PageURI(root="test-root", type="person", id="person1", version=1),
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        # Mock send_message to fail
        self.mock_api_client.send_message.side_effect = Exception("Send failed")

        # Call the internal action method directly
        result = await self.service._send_email_internal(
            person=recipient,
            additional_recipients=None,
            cc_list=None,
            subject="Test Email",
            message="Test body",
        )

        # Verify it returns False on failure
        assert result is False

    @pytest.mark.asyncio
    async def test_action_registration(self):
        """Test that actions are properly registered with the context."""
        # The service has internal action methods that we can test directly
        assert hasattr(self.service, "_reply_to_thread_internal")
        assert hasattr(self.service, "_send_email_internal")
        assert callable(self.service._reply_to_thread_internal)
        assert callable(self.service._send_email_internal)
