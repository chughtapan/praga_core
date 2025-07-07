"""Integration tests for MCP server with real Gmail actions."""

import json
from unittest.mock import AsyncMock

import pytest

from praga_core import ServerContext
from praga_core.context import Page, PageURI
from praga_core.integrations.mcp import create_mcp_server


class TestEmailPage(Page):
    """Test email page for MCP integration."""

    subject: str
    from_addr: str
    content: str


class TestPersonPage(Page):
    """Test person page for MCP integration."""

    name: str
    email: str


class TestMCPRealActions:
    """Test MCP server integration with realistic action scenarios."""

    @pytest.fixture
    async def context_with_actions(self):
        """Create test context with realistic actions."""
        context = await ServerContext.create(
            root="test", cache_url="sqlite+aiosqlite:///:memory:"
        )

        # Register test page handlers
        @context.route("TestEmailPage")
        async def get_test_email(page_uri: PageURI) -> TestEmailPage:
            return TestEmailPage(
                uri=page_uri,
                subject=f"Email {page_uri.id}",
                from_addr=f"sender{page_uri.id}@example.com",
                content=f"Email content {page_uri.id}",
            )

        @context.route("TestPersonPage")
        async def get_test_person(page_uri: PageURI) -> TestPersonPage:
            return TestPersonPage(
                uri=page_uri,
                name=f"Person {page_uri.id}",
                email=f"person{page_uri.id}@example.com",
            )

        # Register realistic actions similar to Gmail actions
        @context.action()
        async def send_email(
            person: TestPersonPage,
            additional_recipients: list[TestPersonPage] = None,
            cc_list: list[TestPersonPage] = None,
            subject: str = "",
            message: str = "",
        ) -> bool:
            """Send a new email."""
            return True

        @context.action()
        async def reply_to_email(
            email: TestEmailPage,
            recipients: list[TestPersonPage] = None,
            cc_list: list[TestPersonPage] = None,
            message: str = "",
        ) -> bool:
            """Reply to an email."""
            return True

        @context.action()
        async def mark_email_read(email: TestEmailPage) -> bool:
            """Mark an email as read."""
            return True

        return context

    @pytest.fixture
    def mcp_server_with_actions(self, context_with_actions):
        """Create MCP server with realistic actions."""
        return create_mcp_server(context_with_actions)

    async def test_realistic_action_tools_registered(self, mcp_server_with_actions):
        """Test that realistic action tools are registered as separate tools."""
        tools = await mcp_server_with_actions.get_tools()
        tool_names = [tool for tool in tools]

        # Check that action tools are registered with correct names
        assert "send_email_tool" in tool_names
        assert "reply_to_email_tool" in tool_names
        assert "mark_email_read_tool" in tool_names

        # Check core tools are also present
        assert "search_pages" in tool_names
        assert "get_pages" in tool_names

        # Verify no generic action_tool exists
        assert "action_tool" not in tool_names

        # Should have 5 tools total (3 actions + 2 core)
        assert len(tool_names) == 5

    async def test_send_email_tool_execution(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test executing the send_email_tool with realistic parameters."""
        # Mock the invoke_action method
        context_with_actions.invoke_action = AsyncMock(return_value={"success": True})

        # Get the send email tool
        send_tool = await mcp_server_with_actions.get_tool("send_email_tool")
        assert send_tool is not None

        # Execute the tool with explicit parameters
        result = await send_tool.fn(
            person="TestPersonPage:recipient1",
            additional_recipients=[
                "TestPersonPage:recipient2",
                "TestPersonPage:recipient3",
            ],
            cc_list=["TestPersonPage:cc1"],
            subject="Test Email Subject",
            message="This is a test email message",
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        expected_action_input = {
            "person": "TestPersonPage:recipient1",
            "additional_recipients": [
                "TestPersonPage:recipient2",
                "TestPersonPage:recipient3",
            ],
            "cc_list": ["TestPersonPage:cc1"],
            "subject": "Test Email Subject",
            "message": "This is a test email message",
        }
        context_with_actions.invoke_action.assert_called_once_with(
            "send_email", expected_action_input
        )

    async def test_reply_to_email_tool_execution(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test executing the reply_to_email_tool."""
        # Mock the invoke_action method
        context_with_actions.invoke_action = AsyncMock(return_value={"success": True})

        # Get the reply tool
        reply_tool = await mcp_server_with_actions.get_tool("reply_to_email_tool")
        assert reply_tool is not None

        # Execute the tool with explicit parameters
        result = await reply_tool.fn(
            email="TestEmailPage:email123",
            recipients=["TestPersonPage:person1", "TestPersonPage:person2"],
            cc_list=["TestPersonPage:cc1"],
            message="This is a reply message",
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        expected_action_input = {
            "email": "TestEmailPage:email123",
            "recipients": ["TestPersonPage:person1", "TestPersonPage:person2"],
            "cc_list": ["TestPersonPage:cc1"],
            "message": "This is a reply message",
        }
        context_with_actions.invoke_action.assert_called_once_with(
            "reply_to_email", expected_action_input
        )

    async def test_mark_email_read_tool_execution(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test executing the mark_email_read_tool."""
        # Mock the invoke_action method
        context_with_actions.invoke_action = AsyncMock(return_value={"success": True})

        # Get the mark read tool
        mark_read_tool = await mcp_server_with_actions.get_tool("mark_email_read_tool")
        assert mark_read_tool is not None

        # Execute the tool with explicit parameters
        result = await mark_read_tool.fn(
            email="TestEmailPage:email456",
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        expected_action_input = {
            "email": "TestEmailPage:email456",
        }
        context_with_actions.invoke_action.assert_called_once_with(
            "mark_email_read", expected_action_input
        )

    async def test_action_tool_descriptions_contain_parameters(
        self, mcp_server_with_actions
    ):
        """Test that action tool descriptions contain parameter information."""
        # Get the send email tool
        send_tool = await mcp_server_with_actions.get_tool("send_email_tool")
        description = send_tool.description

        # Check that the description contains expected information
        assert "send_email" in description
        assert "Send a new email" in description

        # Check that parameters are documented (note: first Page parameter is excluded from description)
        assert "additional_recipients:" in description
        assert "cc_list:" in description
        assert "subject:" in description
        assert "message:" in description

        # Check parameter types are shown (transformed to PageURI types)
        assert "PageURI" in description
        assert "List[PageURI]" in description
        assert "str" in description

    async def test_all_action_tools_have_unique_descriptions(
        self, mcp_server_with_actions
    ):
        """Test that all action tools have unique, specific descriptions."""
        # Get all action tools
        send_tool = await mcp_server_with_actions.get_tool("send_email_tool")
        reply_tool = await mcp_server_with_actions.get_tool("reply_to_email_tool")
        mark_read_tool = await mcp_server_with_actions.get_tool("mark_email_read_tool")

        # Verify all tools exist
        assert send_tool is not None
        assert reply_tool is not None
        assert mark_read_tool is not None

        # Verify descriptions are unique
        assert send_tool.description != reply_tool.description
        assert send_tool.description != mark_read_tool.description
        assert reply_tool.description != mark_read_tool.description

        # Verify each description contains the correct action name
        assert "send_email" in send_tool.description
        assert "reply_to_email" in reply_tool.description
        assert "mark_email_read" in mark_read_tool.description

    async def test_action_tool_error_handling_realistic(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test error handling in action tools with realistic error scenarios."""
        # Mock the invoke_action method to raise an exception
        context_with_actions.invoke_action = AsyncMock(
            side_effect=ValueError("Email sending failed: invalid recipient")
        )

        # Get the send email tool
        send_tool = await mcp_server_with_actions.get_tool("send_email_tool")

        # Execute the tool with explicit parameters
        result = await send_tool.fn(
            person="TestPersonPage:invalid_person",
            subject="Test Subject",
            message="Test message",
        )

        # Verify the error result
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Email sending failed: invalid recipient" in result_data["error"]

    async def test_no_generic_action_tool_in_realistic_setup(
        self, mcp_server_with_actions
    ):
        """Test that no generic 'action_tool' exists in realistic setup."""
        tools = await mcp_server_with_actions.get_tools()

        # Should not have any generic action tool
        assert "action_tool" not in tools

        # All action tools should be specifically named
        action_tools = [tool for tool in tools if tool.endswith("_tool")]
        expected_action_tools = {
            "send_email_tool",
            "reply_to_email_tool",
            "mark_email_read_tool",
        }

        actual_action_tools = set(action_tools)
        assert expected_action_tools == actual_action_tools

        # Verify no generic tool exists
        for tool_name in action_tools:
            assert tool_name != "action_tool"
            assert "_tool" in tool_name
