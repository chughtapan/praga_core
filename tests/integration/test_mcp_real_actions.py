"""Integration tests for MCP server with real Gmail actions."""

import json
from unittest.mock import AsyncMock

import pytest

from praga_core import ServerContext
from praga_core.integrations.mcp import create_mcp_server
from praga_core.types import Page, PageURI


class SampleEmailPage(Page):
    """Sample email page for MCP integration."""

    subject: str
    from_addr: str
    content: str


class SamplePersonPage(Page):
    """Sample person page for MCP integration."""

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
        @context.route("SampleEmailPage")
        async def get_test_email(page_uri: PageURI) -> SampleEmailPage:
            return SampleEmailPage(
                uri=page_uri,
                subject=f"Email {page_uri.id}",
                from_addr=f"sender{page_uri.id}@example.com",
                content=f"Email content {page_uri.id}",
            )

        @context.route("SamplePersonPage")
        async def get_test_person(page_uri: PageURI) -> SamplePersonPage:
            return SamplePersonPage(
                uri=page_uri,
                name=f"Person {page_uri.id}",
                email=f"person{page_uri.id}@example.com",
            )

        # Register realistic actions similar to Gmail actions
        @context.action()
        async def send_email(
            person: SamplePersonPage,
            additional_recipients: list[SamplePersonPage] = None,
            cc_list: list[SamplePersonPage] = None,
            subject: str = "",
            message: str = "",
        ) -> bool:
            """Send a new email."""
            return True

        @context.action()
        async def reply_to_email(
            email: SampleEmailPage,
            recipients: list[SamplePersonPage] = None,
            cc_list: list[SamplePersonPage] = None,
            message: str = "",
        ) -> bool:
            """Reply to an email."""
            return True

        @context.action()
        async def mark_email_read(email: SampleEmailPage) -> bool:
            """Mark an email as read."""
            return True

        return context

    @pytest.fixture
    def mcp_server_with_actions(self, context_with_actions):
        """Create MCP server with realistic actions."""
        return create_mcp_server(context_with_actions)

    async def test_single_invoke_action_tool_registered(self, mcp_server_with_actions):
        """Test that a single invoke_action tool is registered."""
        tools = await mcp_server_with_actions.get_tools()
        tool_names = [tool for tool in tools]

        # Check that invoke_action tool is registered
        assert "invoke_action" in tool_names

        # Check core tools are also present
        assert "search_pages" in tool_names
        assert "get_pages" in tool_names

        # Verify no individual action tools exist
        assert "send_email_tool" not in tool_names
        assert "reply_to_email_tool" not in tool_names
        assert "mark_email_read_tool" not in tool_names

        # Should have 3 tools total (1 invoke_action + 2 core)
        assert len(tool_names) == 3

    async def test_send_email_action_execution(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test executing send_email action via invoke_action tool."""
        # Mock the invoke_action method
        context_with_actions.invoke_action = AsyncMock(return_value={"success": True})

        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")
        assert invoke_tool is not None

        # Execute the tool with action_name and action_input
        result = await invoke_tool.fn(
            action_name="send_email",
            action_input={
                "person": "SamplePersonPage:recipient1",
                "additional_recipients": [
                    "SamplePersonPage:recipient2",
                    "SamplePersonPage:recipient3",
                ],
                "cc_list": ["SamplePersonPage:cc1"],
                "subject": "Test Email Subject",
                "message": "This is a test email message",
            },
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify the action was called correctly
        expected_action_input = {
            "person": "SamplePersonPage:recipient1",
            "additional_recipients": [
                "SamplePersonPage:recipient2",
                "SamplePersonPage:recipient3",
            ],
            "cc_list": ["SamplePersonPage:cc1"],
            "subject": "Test Email Subject",
            "message": "This is a test email message",
        }
        context_with_actions.invoke_action.assert_called_once_with(
            "send_email", expected_action_input
        )

    async def test_reply_to_email_action_execution(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test executing reply_to_email action via invoke_action tool."""
        # Mock the invoke_action method
        context_with_actions.invoke_action = AsyncMock(return_value={"success": True})

        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")
        assert invoke_tool is not None

        # Execute the tool with action_name and action_input
        result = await invoke_tool.fn(
            action_name="reply_to_email",
            action_input={
                "email": "SampleEmailPage:email123",
                "recipients": ["SamplePersonPage:person1", "SamplePersonPage:person2"],
                "cc_list": ["SamplePersonPage:cc1"],
                "message": "This is a reply message",
            },
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify the action was called correctly
        expected_action_input = {
            "email": "SampleEmailPage:email123",
            "recipients": ["SamplePersonPage:person1", "SamplePersonPage:person2"],
            "cc_list": ["SamplePersonPage:cc1"],
            "message": "This is a reply message",
        }
        context_with_actions.invoke_action.assert_called_once_with(
            "reply_to_email", expected_action_input
        )

    async def test_mark_email_read_action_execution(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test executing mark_email_read action via invoke_action tool."""
        # Mock the invoke_action method
        context_with_actions.invoke_action = AsyncMock(return_value={"success": True})

        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")
        assert invoke_tool is not None

        # Execute the tool with action_name and action_input
        result = await invoke_tool.fn(
            action_name="mark_email_read",
            action_input={
                "email": "SampleEmailPage:email456",
            },
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify the action was called correctly
        expected_action_input = {
            "email": "SampleEmailPage:email456",
        }
        context_with_actions.invoke_action.assert_called_once_with(
            "mark_email_read", expected_action_input
        )

    async def test_invoke_action_tool_description_contains_available_actions(
        self, mcp_server_with_actions
    ):
        """Test that invoke_action tool description contains available actions."""
        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")
        description = invoke_tool.description

        # Check that the description contains expected information
        assert "Execute any registered action" in description
        assert "send_email" in description
        assert "reply_to_email" in description
        assert "mark_email_read" in description

        # Check that parameters are documented
        assert "action_name" in description
        assert "action_input" in description

        # Check usage examples
        assert "action_name=" in description
        assert "action_input=" in description

    async def test_invoke_action_error_handling(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test error handling in invoke_action tool."""
        # Mock the invoke_action method to raise an exception
        context_with_actions.invoke_action = AsyncMock(
            side_effect=ValueError("Action execution failed: invalid parameters")
        )

        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")

        # Execute the tool with parameters that will cause an error
        result = await invoke_tool.fn(
            action_name="send_email",
            action_input={
                "person": "SamplePersonPage:invalid_person",
                "subject": "Test Subject",
                "message": "Test message",
            },
        )

        # Verify the error result
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Action execution failed: invalid parameters" in result_data["error"]

    async def test_invoke_action_with_invalid_action_name(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test invoke_action with invalid action name."""
        # Mock the invoke_action method to raise an exception for invalid action
        context_with_actions.invoke_action = AsyncMock(
            side_effect=ValueError("Action 'invalid_action' not found")
        )

        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")

        # Execute the tool with invalid action name
        result = await invoke_tool.fn(
            action_name="invalid_action", action_input={"some_param": "some_value"}
        )

        # Verify the error result
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Action 'invalid_action' not found" in result_data["error"]

    async def test_invoke_action_with_complex_input(
        self, mcp_server_with_actions, context_with_actions
    ):
        """Test invoke_action with complex action input containing lists and nested data."""
        # Mock invoke_action to capture the arguments
        captured_args = {}

        async def mock_invoke_action(action_name, args):
            captured_args[action_name] = args
            return {"success": True}

        context_with_actions.invoke_action = mock_invoke_action

        # Get the invoke_action tool
        invoke_tool = await mcp_server_with_actions.get_tool("invoke_action")

        # Execute the tool with complex action input
        result = await invoke_tool.fn(
            action_name="send_email",
            action_input={
                "person": "SamplePersonPage:person1",
                "additional_recipients": [
                    "SamplePersonPage:person2",
                    "SamplePersonPage:person3",
                ],
                "cc_list": ["SamplePersonPage:cc1"],
                "subject": "Test Email Subject",
                "message": "This is a test email message",
            },
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is True

        # Verify that the complex input was passed through correctly
        assert "send_email" in captured_args
        args = captured_args["send_email"]

        # All parameters should be passed through as-is
        assert args["person"] == "SamplePersonPage:person1"
        assert args["additional_recipients"] == [
            "SamplePersonPage:person2",
            "SamplePersonPage:person3",
        ]
        assert args["cc_list"] == ["SamplePersonPage:cc1"]
        assert args["subject"] == "Test Email Subject"
        assert args["message"] == "This is a test email message"
