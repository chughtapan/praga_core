"""Integration tests for MCP server with Gmail service."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core import ServerContext
from praga_core.global_context import clear_global_context, set_global_context
from praga_core.integrations.mcp import create_mcp_server
from pragweb.google_api.gmail.service import GmailService
from pragweb.google_api.people.service import PeopleService


class TestMCPGmailIntegration:
    """Test MCP server integration with Gmail service."""

    @pytest.fixture
    async def context_with_gmail(self):
        """Create test context with Gmail service."""
        # Clear any existing global context
        clear_global_context()

        context = await ServerContext.create(
            root="test", cache_url="sqlite+aiosqlite:///:memory:"
        )

        # Set the global context so Gmail service can register
        set_global_context(context)

        # Mock Google API client
        mock_client = Mock()
        mock_client.list_messages = AsyncMock(return_value=[])
        mock_client.get_message = AsyncMock()
        mock_client.send_message = AsyncMock()
        mock_client.list_threads = AsyncMock(return_value=[])
        mock_client.get_thread = AsyncMock()

        # Mock People service
        mock_people_service = Mock(spec=PeopleService)
        mock_people_service.search_existing_records = AsyncMock(return_value=[])

        # Create Gmail service with mocked dependencies
        with patch.object(context, "get_service", return_value=mock_people_service):
            gmail_service = GmailService(mock_client)

        yield context, gmail_service, mock_client

        # Clean up global context after test
        clear_global_context()

    @pytest.fixture
    def mcp_server_with_gmail(self, context_with_gmail):
        """Create MCP server with Gmail service."""
        context, gmail_service, mock_client = context_with_gmail
        return create_mcp_server(context), context, gmail_service, mock_client

    async def test_gmail_actions_available_via_invoke_action(
        self, mcp_server_with_gmail
    ):
        """Test that Gmail actions are available via the single invoke_action tool."""
        mcp_server, context, gmail_service, mock_client = mcp_server_with_gmail

        tools = await mcp_server.get_tools()
        tool_names = [tool for tool in tools]

        # Check that invoke_action tool is registered
        assert "invoke_action" in tool_names

        # Verify no individual action tools exist
        assert "reply_to_email_thread_tool" not in tool_names
        assert "send_email_tool" not in tool_names

        # Get the invoke_action tool and check it lists Gmail actions
        invoke_tool = await mcp_server.get_tool("invoke_action")
        description = invoke_tool.description
        assert "reply_to_email_thread" in description
        assert "send_email" in description

    async def test_reply_to_email_thread_action_execution(self, mcp_server_with_gmail):
        """Test executing reply_to_email_thread action via invoke_action tool."""
        mcp_server, context, gmail_service, mock_client = mcp_server_with_gmail

        # Mock the invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Get the invoke_action tool
        invoke_tool = await mcp_server.get_tool("invoke_action")

        # Execute the tool with action_name and action_input
        result = await invoke_tool.fn(
            action_name="reply_to_email_thread",
            action_input={
                "thread": "EmailThreadPage:thread123",
                "email": "EmailPage:email456",
                "recipients": ["PersonPage:person1"],
                "cc_list": ["PersonPage:person2"],
                "message": "This is a test reply",
            },
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify the action was called correctly
        expected_action_input = {
            "thread": "EmailThreadPage:thread123",
            "email": "EmailPage:email456",
            "recipients": ["PersonPage:person1"],
            "cc_list": ["PersonPage:person2"],
            "message": "This is a test reply",
        }
        context.invoke_action.assert_called_once_with(
            "reply_to_email_thread", expected_action_input
        )

    async def test_send_email_action_execution(self, mcp_server_with_gmail):
        """Test executing send_email action via invoke_action tool."""
        mcp_server, context, gmail_service, mock_client = mcp_server_with_gmail

        # Mock the invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Get the invoke_action tool
        invoke_tool = await mcp_server.get_tool("invoke_action")

        # Execute the tool with action_name and action_input
        result = await invoke_tool.fn(
            action_name="send_email",
            action_input={
                "person": "PersonPage:person1",
                "additional_recipients": ["PersonPage:person2"],
                "cc_list": ["PersonPage:person3"],
                "subject": "Test Email Subject",
                "message": "This is a test email message",
            },
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify the action was called correctly
        expected_action_input = {
            "person": "PersonPage:person1",
            "additional_recipients": ["PersonPage:person2"],
            "cc_list": ["PersonPage:person3"],
            "subject": "Test Email Subject",
            "message": "This is a test email message",
        }
        context.invoke_action.assert_called_once_with(
            "send_email", expected_action_input
        )

    async def test_invoke_action_error_handling(self, mcp_server_with_gmail):
        """Test error handling in invoke_action tool."""
        mcp_server, context, gmail_service, mock_client = mcp_server_with_gmail

        # Mock the invoke_action method to raise an exception
        context.invoke_action = AsyncMock(
            side_effect=ValueError("Email sending failed")
        )

        # Get the invoke_action tool
        invoke_tool = await mcp_server.get_tool("invoke_action")

        # Execute the tool with parameters that will cause an error
        result = await invoke_tool.fn(
            action_name="send_email",
            action_input={
                "person": "PersonPage:person1",
                "subject": "Test Subject",
                "message": "Test message",
            },
        )

        # Verify the error result
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Email sending failed" in result_data["error"]

    async def test_mcp_server_with_all_services(self):
        """Test MCP server creation with all Google services."""
        # Clear any existing global context
        clear_global_context()

        # This test simulates the real application setup
        context = await ServerContext.create(
            root="test", cache_url="sqlite+aiosqlite:///:memory:"
        )

        # Set the global context so services can register
        set_global_context(context)

        try:
            # Mock Google API client
            mock_client = Mock()
            mock_client.list_messages = AsyncMock(return_value=[])
            mock_client.get_message = AsyncMock()
            mock_client.send_message = AsyncMock()
            mock_client.list_threads = AsyncMock(return_value=[])
            mock_client.get_thread = AsyncMock()
            mock_client.list_events = AsyncMock(return_value=[])
            mock_client.get_event = AsyncMock()
            mock_client.list_contacts = AsyncMock(return_value=[])
            mock_client.get_contact = AsyncMock()
            mock_client.list_documents = AsyncMock(return_value=[])
            mock_client.get_document = AsyncMock()

            # Mock People service
            mock_people_service = Mock(spec=PeopleService)
            mock_people_service.search_existing_records = AsyncMock(return_value=[])

            # Create all services (simulating real app)
            with patch.object(context, "get_service", return_value=mock_people_service):
                # Import the services to trigger registration
                from pragweb.google_api.calendar.service import CalendarService
                from pragweb.google_api.docs.service import GoogleDocsService

                GmailService(mock_client)
                CalendarService(mock_client)
                PeopleService(mock_client)
                GoogleDocsService(mock_client)

            # Create MCP server
            mcp_server = create_mcp_server(context)

            # Get all tools
            tools = await mcp_server.get_tools()

            # Should have core tools + single invoke_action tool
            # Core tools: search_pages, get_pages
            # Action tool: invoke_action
            expected_tools = {
                "search_pages",
                "get_pages",
                "invoke_action",
            }

            actual_tools = set(tools)
            assert expected_tools.issubset(actual_tools)

            # Verify no individual action tools exist
            assert "reply_to_email_thread_tool" not in actual_tools
            assert "send_email_tool" not in actual_tools

        finally:
            # Clean up global context after test
            clear_global_context()
