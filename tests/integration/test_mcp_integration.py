"""Integration tests for MCP server functionality."""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Context

from praga_core import ServerContext
from praga_core.integrations.mcp import create_mcp_server
from praga_core.types import Page, PageURI


class MCPTestPage(Page):
    """Test page for MCP integration tests."""

    title: str
    content: str
    count: int = 0


class MCPTestPersonPage(Page):
    """Test person page for action testing."""

    name: str
    email: str


class TestMCPIntegration:
    """Test MCP server integration."""

    @pytest.fixture
    async def context(self):
        """Create test context."""
        context = await ServerContext.create(
            root="test", cache_url="sqlite+aiosqlite:///:memory:"
        )

        # Register a test page handler
        @context.route("MCPTestPage")
        async def get_test_page(page_uri: PageURI) -> MCPTestPage:
            return MCPTestPage(
                uri=page_uri,
                title=f"Test Page {page_uri.id}",
                content=f"Content for {page_uri.id}",
                count=1,
            )

        # Register a test person handler
        @context.route("MCPTestPersonPage")
        async def get_test_person(page_uri: PageURI) -> MCPTestPersonPage:
            return MCPTestPersonPage(
                uri=page_uri,
                name=f"Person {page_uri.id}",
                email=f"person{page_uri.id}@example.com",
            )

        # Register test actions
        @context.action()
        async def test_action_basic(
            page: MCPTestPage, message: str = "default"
        ) -> bool:
            """Basic test action."""
            return True

        @context.action()
        async def test_action_with_person(
            page: MCPTestPage, person: MCPTestPersonPage, note: str = ""
        ) -> bool:
            """Action that takes multiple pages."""
            return True

        @context.action()
        async def test_action_failure(page: MCPTestPage) -> bool:
            """Action that always fails."""
            raise ValueError("Test failure")

        return context

    @pytest.fixture
    def mcp_server(self, context):
        """Create MCP server from context."""
        return create_mcp_server(context)

    async def test_mcp_server_creation(self, mcp_server):
        """Test that MCP server is created successfully."""
        assert mcp_server is not None
        assert mcp_server.name == "Praga Core Server"

    async def test_tool_registration(self, mcp_server):
        """Test that all tools are registered correctly."""
        tools = await mcp_server.get_tools()
        tool_names = [tool for tool in tools]

        # Check that core tools are registered
        assert "search_pages" in tool_names
        assert "get_pages" in tool_names

        # Check that action tools are registered with correct names
        assert "test_action_basic_tool" in tool_names
        assert "test_action_with_person_tool" in tool_names
        assert "test_action_failure_tool" in tool_names

        # Verify we have the expected number of tools
        assert len(tool_names) == 5  # 2 core + 3 action tools

    async def test_individual_action_tools_registered(self, mcp_server):
        """Test that each action gets its own tool."""
        tools = await mcp_server.get_tools()
        action_tools = [tool for tool in tools if tool.endswith("_tool")]

        # Each action should have its own tool
        assert "test_action_basic_tool" in action_tools
        assert "test_action_with_person_tool" in action_tools
        assert "test_action_failure_tool" in action_tools

        # No generic 'action_tool' should exist
        assert "action_tool" not in tools

    async def test_search_pages_tool(self, mcp_server, context):
        """Test search_pages tool functionality."""
        # Get the search tool
        search_tool = await mcp_server.get_tool("search_pages")
        assert search_tool is not None

        # Mock the context search method
        context.search = AsyncMock()
        mock_response = Mock()
        mock_response.model_dump_json.return_value = '{"results": []}'
        context.search.return_value = mock_response

        # Test calling the tool
        result = await search_tool.fn(
            instruction="find test pages", resolve_references=True
        )

        # Verify the result
        assert result == '{"results": []}'
        context.search.assert_called_once_with(
            "find test pages", resolve_references=True
        )

    async def test_get_pages_tool(self, mcp_server, context):
        """Test get_pages tool functionality."""
        # Get the get_pages tool
        get_pages_tool = await mcp_server.get_tool("get_pages")
        assert get_pages_tool is not None

        # Mock the context get_pages method
        test_page = MCPTestPage(
            uri=PageURI(root="test", type="MCPTestPage", id="123"),
            title="Test Page 123",
            content="Test content",
            count=1,
        )
        context.get_pages = AsyncMock(return_value=[test_page])

        # Test calling the tool
        result = await get_pages_tool.fn(page_uris=["MCPTestPage:123"])

        # Verify the result
        result_data = json.loads(result)
        assert result_data["requested_count"] == 1
        assert result_data["successful_count"] == 1
        assert result_data["error_count"] == 0
        assert len(result_data["pages"]) == 1
        assert result_data["pages"][0]["uri"] == "MCPTestPage:123"

    async def test_action_tool_success(self, mcp_server, context):
        """Test successful action tool execution."""
        # Get the action tool
        action_tool = await mcp_server.get_tool("test_action_basic_tool")
        assert action_tool is not None

        # Mock the context invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Test calling the tool with explicit parameters
        result = await action_tool.fn(page="MCPTestPage:123", message="test")

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        context.invoke_action.assert_called_once_with(
            "test_action_basic", {"page": "MCPTestPage:123", "message": "test"}
        )

    async def test_action_tool_failure(self, mcp_server, context):
        """Test action tool execution with failure."""
        # Get the action tool
        action_tool = await mcp_server.get_tool("test_action_failure_tool")
        assert action_tool is not None

        # Mock the context invoke_action method to raise exception
        context.invoke_action = AsyncMock(side_effect=ValueError("Test error"))

        # Test calling the tool with explicit parameters
        result = await action_tool.fn(page="MCPTestPage:123")

        # Verify the result
        result_data = json.loads(result)
        assert result_data["success"] is False
        assert "Test error" in result_data["error"]

    async def test_action_tool_with_multiple_pages(self, mcp_server, context):
        """Test action tool with multiple page parameters."""
        # Get the action tool
        action_tool = await mcp_server.get_tool("test_action_with_person_tool")
        assert action_tool is not None

        # Mock the context invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Test calling the tool with explicit parameters
        result = await action_tool.fn(
            page="MCPTestPage:123",
            person="MCPTestPersonPage:456",
            note="test note",
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify the action was called correctly
        context.invoke_action.assert_called_once_with(
            "test_action_with_person",
            {
                "page": "MCPTestPage:123",
                "person": "MCPTestPersonPage:456",
                "note": "test note",
            },
        )

    async def test_search_tool_with_context_logging(self, mcp_server, context):
        """Test search tool with MCP context logging."""
        # Get the search tool
        search_tool = await mcp_server.get_tool("search_pages")
        assert search_tool is not None

        # Mock the context search method
        context.search = AsyncMock()
        mock_response = Mock()
        mock_response.results = [{"uri": "test:123"}]  # Add actual results attribute
        mock_response.model_dump_json.return_value = (
            '{"results": [{"uri": "test:123"}]}'
        )
        context.search.return_value = mock_response

        # Mock MCP context
        mock_ctx = Mock(spec=Context)
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Test calling the tool with context
        result = await search_tool.fn(
            instruction="find test pages", resolve_references=True, ctx=mock_ctx
        )

        # Verify the result
        assert '"uri": "test:123"' in result

        # Verify logging was called
        mock_ctx.info.assert_called()
        assert (
            mock_ctx.info.call_count >= 2
        )  # At least search instruction and result count

    async def test_action_tool_with_context_logging(self, mcp_server, context):
        """Test action tool with MCP context logging."""
        # Get the action tool
        action_tool = await mcp_server.get_tool("test_action_basic_tool")
        assert action_tool is not None

        # Mock the context invoke_action method
        context.invoke_action = AsyncMock(return_value={"success": True})

        # Mock MCP context
        mock_ctx = Mock(spec=Context)
        mock_ctx.info = AsyncMock()
        mock_ctx.error = AsyncMock()

        # Test calling the tool with explicit parameters and context
        result = await action_tool.fn(
            page="MCPTestPage:123", message="test", ctx=mock_ctx
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data == {"success": True}

        # Verify logging was called
        mock_ctx.info.assert_called()
        assert mock_ctx.info.call_count >= 3  # Action name, input, and result

    async def test_get_pages_tool_with_errors(self, mcp_server, context):
        """Test get_pages tool with some page errors."""
        # Get the get_pages tool
        get_pages_tool = await mcp_server.get_tool("get_pages")
        assert get_pages_tool is not None

        # Mock the context get_pages method with mixed results
        test_page = MCPTestPage(
            uri=PageURI(root="test", type="MCPTestPage", id="123"),
            title="Test Page 123",
            content="Test content",
            count=1,
        )
        error = ValueError("Page not found")
        context.get_pages = AsyncMock(return_value=[test_page, error])

        # Test calling the tool
        result = await get_pages_tool.fn(
            page_uris=["MCPTestPage:123", "MCPTestPage:456"]
        )

        # Verify the result
        result_data = json.loads(result)
        assert result_data["requested_count"] == 2
        assert result_data["successful_count"] == 1
        assert result_data["error_count"] == 1
        assert len(result_data["pages"]) == 1
        assert len(result_data["errors"]) == 1
        assert result_data["errors"][0]["uri"] == "MCPTestPage:456"
        assert "Page not found" in result_data["errors"][0]["error"]

    async def test_tool_descriptions_are_specific(self, mcp_server):
        """Test that each tool has a specific description."""
        # Get tool descriptions
        basic_tool = await mcp_server.get_tool("test_action_basic_tool")
        person_tool = await mcp_server.get_tool("test_action_with_person_tool")
        failure_tool = await mcp_server.get_tool("test_action_failure_tool")

        # Check that descriptions are specific to each action
        assert basic_tool.description != person_tool.description
        assert basic_tool.description != failure_tool.description
        assert person_tool.description != failure_tool.description

        # Check that action names are in descriptions
        assert "test_action_basic" in basic_tool.description
        assert "test_action_with_person" in person_tool.description
        assert "test_action_failure" in failure_tool.description

    async def test_no_generic_action_tool_exists(self, mcp_server):
        """Test that no generic 'action_tool' exists."""
        tools = await mcp_server.get_tools()

        # Should not have any generic action tool
        assert "action_tool" not in tools

        # All action tools should be specifically named
        action_tools = [tool for tool in tools if tool.endswith("_tool")]
        for tool_name in action_tools:
            assert tool_name != "action_tool"
            assert "_tool" in tool_name
            assert tool_name.startswith("test_action_")
