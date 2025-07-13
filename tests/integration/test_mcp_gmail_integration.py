"""Integration tests for MCP server with Email service (new architecture)."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import ServerContext
from praga_core.global_context import clear_global_context, set_global_context
from praga_core.integrations.mcp import create_mcp_server
from pragweb.api_clients.base import BaseProviderClient
from pragweb.services import EmailService, PeopleService


class MockEmailClient:
    """Mock email client for testing."""

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
            provider_message_id=message_data.get("id", "test_msg"),
            thread_id=message_data.get("threadId", "test_thread"),
            subject=headers.get("Subject", ""),
            sender=headers.get("From", ""),
            recipients=(
                [email.strip() for email in headers.get("To", "").split(",")]
                if headers.get("To")
                else []
            ),
            body="Test email body content",
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
        self._email_client = MockEmailClient()

    @property
    def email_client(self):
        return self._email_client

    @property
    def calendar_client(self):
        return Mock()

    @property
    def people_client(self):
        return Mock()

    @property
    def documents_client(self):
        return Mock()

    async def test_connection(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "google"


class TestMCPEmailIntegration:
    """Test MCP server integration with Email service (new architecture)."""

    @pytest.fixture
    async def context_with_email_service(self):
        """Create test context with Email service."""
        # Clear any existing global context
        clear_global_context()

        context = await ServerContext.create(
            root="test", cache_url="sqlite+aiosqlite:///:memory:"
        )

        # Set the global context so Email service can register
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create Email service with mocked provider
        email_service = EmailService(providers)

        yield context, email_service, google_provider

        # Clean up global context after test
        clear_global_context()

    @pytest.fixture
    def mcp_server_with_email_service(self, context_with_email_service):
        """Create MCP server with Email service."""
        context, email_service, google_provider = context_with_email_service
        return create_mcp_server(context), context, email_service, google_provider

    async def test_email_actions_registered_as_separate_tools(
        self, mcp_server_with_email_service
    ):
        """Test that Email service actions are registered as separate MCP tools."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        tools = await mcp_server.get_tools()
        tool_names = [tool for tool in tools]

        # Check that Email action tools are registered with correct names
        assert "reply_to_email_thread_tool" in tool_names
        assert "send_email_tool" in tool_names
        assert "mark_email_as_read_tool" in tool_names
        assert "mark_email_as_unread_tool" in tool_names

        # Verify no generic action_tool exists
        assert "action_tool" not in tool_names

    async def test_reply_to_email_thread_tool_exists(
        self, mcp_server_with_email_service
    ):
        """Test that reply_to_email_thread_tool exists and has correct description."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Get the reply tool
        reply_tool = await mcp_server.get_tool("reply_to_email_thread_tool")
        assert reply_tool is not None

        # Check that the description contains expected information
        description = reply_tool.description
        assert "reply_to_email_thread" in description
        assert "Reply to an email thread" in description
        assert "thread:" in description  # Should show parameters

    async def test_send_email_tool_exists(self, mcp_server_with_email_service):
        """Test that send_email_tool exists and has correct description."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Get the send tool
        send_tool = await mcp_server.get_tool("send_email_tool")
        assert send_tool is not None

        # Check that the description contains expected information
        description = send_tool.description
        assert "send_email" in description
        assert "Send a new email" in description
        assert "recipient:" in description  # Should show parameters

    async def test_reply_to_email_thread_tool_execution(
        self, mcp_server_with_email_service
    ):
        """Test executing the reply_to_email_thread_tool."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Mock the invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Get the reply tool
        reply_tool = await mcp_server.get_tool("reply_to_email_thread_tool")

        # Execute the tool with explicit parameters
        result = await reply_tool.fn(
            thread="EmailThreadPage:thread123",
            email="EmailPage:email456",
            recipients=["PersonPage:person1"],
            cc=["PersonPage:person2"],
            body="This is a test reply",
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        expected_action_input = {
            "thread": "EmailThreadPage:thread123",
            "email": "EmailPage:email456",
            "recipients": ["PersonPage:person1"],
            "cc": ["PersonPage:person2"],
            "body": "This is a test reply",
        }
        context.invoke_action.assert_called_once_with(
            "reply_to_email_thread", expected_action_input
        )

    async def test_send_email_tool_execution(self, mcp_server_with_email_service):
        """Test executing the send_email_tool."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Mock the invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Get the send tool
        send_tool = await mcp_server.get_tool("send_email_tool")

        # Execute the tool with explicit parameters
        result = await send_tool.fn(
            recipient="PersonPage:person1",
            additional_recipients=["PersonPage:person2"],
            cc=["PersonPage:person3"],
            subject="Test Email Subject",
            body="This is a test email message",
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        expected_action_input = {
            "recipient": "PersonPage:person1",
            "additional_recipients": ["PersonPage:person2"],
            "cc": ["PersonPage:person3"],
            "subject": "Test Email Subject",
            "body": "This is a test email message",
        }
        context.invoke_action.assert_called_once_with(
            "send_email", expected_action_input
        )

    async def test_action_tool_error_handling(self, mcp_server_with_email_service):
        """Test error handling in action tools."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Mock the invoke_action method to raise an exception
        context.invoke_action = AsyncMock(
            side_effect=ValueError("Email sending failed")
        )

        # Get the send tool
        send_tool = await mcp_server.get_tool("send_email_tool")

        # Execute the tool with explicit parameters
        result = await send_tool.fn(
            recipient="PersonPage:person1",
            subject="Test Subject",
            body="Test message",
        )

        # Verify the error result
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Email sending failed" in result_data["error"]

    async def test_tools_have_unique_names_and_descriptions(
        self, mcp_server_with_email_service
    ):
        """Test that each Email service action tool has a unique name and description."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Get the Email service action tools
        reply_tool = await mcp_server.get_tool("reply_to_email_thread_tool")
        send_tool = await mcp_server.get_tool("send_email_tool")

        assert reply_tool is not None
        assert send_tool is not None

        # Verify names are different
        assert reply_tool != send_tool

        # Verify descriptions are different
        assert reply_tool.description != send_tool.description

        # Verify each description is specific to its action
        assert "reply_to_email_thread" in reply_tool.description
        assert "reply_to_email_thread" not in send_tool.description
        assert "send_email" in send_tool.description
        assert "send_email" not in reply_tool.description

    async def test_mcp_server_with_all_services(self):
        """Test MCP server creation with all services."""
        # Clear any existing global context
        clear_global_context()

        # This test simulates the real application setup
        context = await ServerContext.create(
            root="test", cache_url="sqlite+aiosqlite:///:memory:"
        )

        # Set the global context so services can register
        set_global_context(context)

        try:
            # Create mock providers
            google_provider = MockGoogleProviderClient()
            providers = {"google": google_provider}

            # Create all services (simulating real app)
            from pragweb.services import CalendarService, DocumentService

            EmailService(providers)
            CalendarService(providers)
            PeopleService(providers)
            DocumentService(providers)

            # Create MCP server
            mcp_server = create_mcp_server(context)

            # Get all tools
            tools = await mcp_server.get_tools()

            # Should have core tools + Email service action tools
            # Core tools: search_pages, get_pages
            # Email action tools: reply_to_email_thread_tool, send_email_tool, mark_email_as_read_tool, mark_email_as_unread_tool
            expected_tools = {
                "search_pages",
                "get_pages",
                "reply_to_email_thread_tool",
                "send_email_tool",
                "mark_email_as_read_tool",
                "mark_email_as_unread_tool",
            }

            actual_tools = set(tools)
            assert expected_tools.issubset(actual_tools)

            # Verify no generic action_tool exists
            assert "action_tool" not in actual_tools

        finally:
            # Clean up global context after test
            clear_global_context()

    async def test_tool_parameter_extraction(self, mcp_server_with_email_service):
        """Test that tool descriptions correctly extract parameters."""
        mcp_server, context, email_service, google_provider = (
            mcp_server_with_email_service
        )

        # Get the reply tool
        reply_tool = await mcp_server.get_tool("reply_to_email_thread_tool")
        description = reply_tool.description

        # Check that all expected parameters are documented
        expected_params = [
            "thread:",
            "email:",
            "recipients:",
            "cc:",
            "body:",
        ]

        for param in expected_params:
            assert param in description, f"Parameter {param} not found in description"

        # Check parameter types are shown (transformed to PageURI types)
        assert "PageURI" in description
        assert "Optional[PageURI]" in description
        assert "Optional[List[PageURI]]" in description
        assert "str" in description
