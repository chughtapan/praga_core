"""Tests for core RetrieverToolkit functionality.

This module focuses on testing the core features of RetrieverToolkit,
including tool registration, basic invocation, and toolkit management.
"""

from typing import List

import pytest

from praga_core.agents import RetrieverToolkit, tool
from praga_core.agents.tool import Tool
from praga_core.types import PageURI

from .conftest import MockRetrieverToolkit, SimpleTestPage, create_test_pages


class TestRetrieverToolkitCore:
    """Test core RetrieverToolkit functionality."""

    def test_toolkit_initialization(self) -> None:
        """Test basic toolkit initialization."""
        toolkit = MockRetrieverToolkit()

        assert toolkit is not None
        assert hasattr(toolkit, "tools")
        assert hasattr(toolkit, "_tools")
        assert len(toolkit.tools) == 0

    def test_tool_registration_with_method(self) -> None:
        """Test registering a method as a tool."""
        toolkit = MockRetrieverToolkit()

        def test_method(query: str) -> List[SimpleTestPage]:
            return create_test_pages(3, query)

        toolkit.register_tool(test_method, "test_tool")

        assert "test_tool" in toolkit.tools
        assert isinstance(toolkit.get_tool("test_tool"), Tool)

    def test_tool_registration_with_function(self) -> None:
        """Test registering a standalone function as a tool."""

        def standalone_function(query: str, limit: int = 5) -> List[SimpleTestPage]:
            return create_test_pages(limit, query)

        toolkit = MockRetrieverToolkit()
        toolkit.register_tool(standalone_function, "standalone_tool")

        assert "standalone_tool" in toolkit.tools
        tool = toolkit.get_tool("standalone_tool")
        assert tool.name == "standalone_tool"

    def test_tool_registration_with_function_no_name(self) -> None:
        """Test registering a standalone function as a tool without a name."""

        def standalone_function(query: str, limit: int = 5) -> List[SimpleTestPage]:
            return create_test_pages(limit, query)

        toolkit = MockRetrieverToolkit()
        toolkit.register_tool(standalone_function)

    def test_tool_registration_with_custom_description(self) -> None:
        """Test tool registration with custom description via docstring."""

        def test_func() -> List[SimpleTestPage]:
            """Custom description for this tool"""
            return []

        toolkit = MockRetrieverToolkit()
        toolkit.register_tool(test_func, "custom_tool")

        tool = toolkit.get_tool("custom_tool")
        assert tool.description == "Custom description for this tool"

    def test_get_tool_success(self) -> None:
        """Test successful tool retrieval."""
        toolkit = MockRetrieverToolkit()

        def sample_tool() -> List[SimpleTestPage]:
            return create_test_pages(1)

        toolkit.register_tool(sample_tool, "sample_tool")
        retrieved_tool = toolkit.get_tool("sample_tool")

        assert isinstance(retrieved_tool, Tool)
        assert retrieved_tool.name == "sample_tool"

    def test_get_tool_not_found(self) -> None:
        """Test tool retrieval when tool doesn't exist."""
        toolkit = MockRetrieverToolkit()

        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            toolkit.get_tool("nonexistent")

    def test_tools_property(self) -> None:
        """Test the tools property returns correct tool mapping."""
        toolkit = MockRetrieverToolkit()

        def tool1() -> List[SimpleTestPage]:
            return []

        def tool2() -> List[SimpleTestPage]:
            return []

        toolkit.register_tool(tool1, "tool1")
        toolkit.register_tool(tool2, "tool2")

        tools = toolkit.tools
        assert len(tools) == 2
        assert "tool1" in tools
        assert "tool2" in tools
        assert isinstance(tools["tool1"], Tool)
        assert isinstance(tools["tool2"], Tool)

    def test_invoke_tool_basic(self) -> None:
        """Test basic tool invocation through invoke_tool method."""
        toolkit = MockRetrieverToolkit()

        def simple_tool(query: str) -> List[SimpleTestPage]:
            return create_test_pages(2, query)

        toolkit.register_tool(simple_tool, "simple_tool")
        result = toolkit.invoke_tool("simple_tool", "test_query")

        assert "results" in result
        assert len(result["results"]) == 2
        assert "test_query" in result["results"][0]["title"]

    def test_invoke_tool_with_dict_args(self) -> None:
        """Test tool invocation with dictionary arguments."""
        toolkit = MockRetrieverToolkit()

        def parameterized_tool(query: str, limit: int = 5) -> List[SimpleTestPage]:
            return create_test_pages(limit, query)

        toolkit.register_tool(parameterized_tool, "param_tool")
        result = toolkit.invoke_tool("param_tool", {"query": "test", "limit": 3})

        assert len(result["results"]) == 3

    def test_invoke_tool_not_found(self) -> None:
        """Test invoking a non-existent tool raises appropriate error."""
        toolkit = MockRetrieverToolkit()

        with pytest.raises(ValueError, match="Tool 'missing_tool' not found"):
            toolkit.invoke_tool("missing_tool", "test")

    def test_direct_method_access(self) -> None:
        """Test that registered tools are accessible as toolkit methods."""
        toolkit = MockRetrieverToolkit()

        def accessible_tool(name: str) -> List[SimpleTestPage]:
            return [
                SimpleTestPage(
                    uri=PageURI.parse("test/SimpleTestPage:test@1"),
                    title="Test",
                    content=f"Hello {name}",
                )
            ]

        toolkit.register_tool(accessible_tool, "accessible_tool")

        # Should be able to call as a method
        result = toolkit.accessible_tool("World")
        assert len(result) == 1
        assert "Hello World" in result[0].content


class TestRetrieverToolkitDecorator:
    """Test the @tool decorator functionality."""

    def test_decorator_basic(self) -> None:
        """Test basic decorator functionality."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        @TestToolkit.tool()
        def decorated_tool(query: str) -> List[SimpleTestPage]:
            return create_test_pages(2, query)

        toolkit = TestToolkit()

        assert "decorated_tool" in toolkit.tools
        result = toolkit.invoke_tool("decorated_tool", "test")
        assert len(result["results"]) == 2

    def test_decorator_with_description(self) -> None:
        """Test decorator uses function docstring for description."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        @TestToolkit.tool()
        def described_tool() -> List[SimpleTestPage]:
            """Custom decorated tool description"""
            return []

        toolkit = TestToolkit()
        tool = toolkit.get_tool("described_tool")
        assert tool.description == "Custom decorated tool description"

    def test_multiple_decorated_tools(self) -> None:
        """Test multiple tools decorated on the same toolkit."""

        class MultiToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "MultiToolkit"

        @MultiToolkit.tool()
        def tool_one() -> List[SimpleTestPage]:
            return create_test_pages(1, "one")

        @MultiToolkit.tool()
        def tool_two() -> List[SimpleTestPage]:
            return create_test_pages(2, "two")

        toolkit = MultiToolkit()

        assert len(toolkit.tools) == 2
        assert "tool_one" in toolkit.tools
        assert "tool_two" in toolkit.tools

    def test_decorator_inheritance(self) -> None:
        """Test that decorated tools work with toolkit inheritance."""

        class BaseToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "BaseToolkit"

        @BaseToolkit.tool()
        def base_tool() -> List[SimpleTestPage]:
            return create_test_pages(1, "base")

        class DerivedToolkit(BaseToolkit):
            @property
            def name(self) -> str:
                return "DerivedToolkit"

        @DerivedToolkit.tool()
        def derived_tool() -> List[SimpleTestPage]:
            return create_test_pages(1, "derived")

        # Note: Current implementation shares decorated tools across classes
        # This test verifies the actual behavior
        base_toolkit = BaseToolkit()
        derived_toolkit = DerivedToolkit()

        # Both toolkits will have both tools due to shared decorator state
        assert "base_tool" in base_toolkit.tools
        assert "derived_tool" in base_toolkit.tools
        assert len(base_toolkit.tools) == 2

        assert "base_tool" in derived_toolkit.tools
        assert "derived_tool" in derived_toolkit.tools
        assert len(derived_toolkit.tools) == 2


class TestRetrieverToolkitErrorHandling:
    """Test error handling in RetrieverToolkit operations."""

    def test_invalid_tool_registration_no_annotation(self) -> None:
        """Test that tools without proper type annotations are rejected."""
        toolkit = MockRetrieverToolkit()

        def invalid_tool():  # type: ignore[no-untyped-def]
            return []

        with pytest.raises(TypeError, match="must have return type annotation"):
            toolkit.register_tool(invalid_tool, "invalid_tool")

    def test_invalid_tool_registration_wrong_return_type(self) -> None:
        """Test that tools with invalid return types are rejected."""
        toolkit = MockRetrieverToolkit()

        def wrong_return_type() -> str:
            return "not a document list"

        with pytest.raises(TypeError, match="must have return type annotation"):
            toolkit.register_tool(wrong_return_type, "wrong_tool")  # type: ignore

    def test_tool_execution_error_handling(self) -> None:
        """Test error handling during tool execution."""
        toolkit = MockRetrieverToolkit()

        def failing_tool(query: str) -> List[SimpleTestPage]:
            if query == "no_results":
                raise ValueError("No matching documents found")
            raise RuntimeError("General error")

        toolkit.register_tool(failing_tool, "failing_tool")

        # Test "no documents found" error
        result = toolkit.invoke_tool("failing_tool", "no_results")
        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"

        # Test other errors should bubble up
        with pytest.raises(ValueError, match="Tool execution failed"):
            toolkit.invoke_tool("failing_tool", "other_error")

    def test_duplicate_tool_registration(self) -> None:
        """Test behavior when registering tools with duplicate names."""
        toolkit = MockRetrieverToolkit()

        def tool1() -> List[SimpleTestPage]:
            return create_test_pages(1, "first")

        def tool2() -> List[SimpleTestPage]:
            return create_test_pages(1, "second")

        # Register first tool
        toolkit.register_tool(tool1, "duplicate_name")
        first_result = toolkit.invoke_tool("duplicate_name", {})

        # Register second tool with same name (should replace first)
        toolkit.register_tool(tool2, "duplicate_name")
        second_result = toolkit.invoke_tool("duplicate_name", {})

        # Results should be different, confirming replacement
        assert (
            first_result["results"][0]["title"] != second_result["results"][0]["title"]
        )
        assert "second" in second_result["results"][0]["title"]


class TestGlobalToolDecorator:
    """Test the global @tool decorator functionality."""

    def test_global_tool_decorator_basic(self) -> None:
        """Test basic functionality of the global @tool decorator."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

            @tool()
            def search_items(self, query: str) -> List[SimpleTestPage]:
                """Search for items"""
                return create_test_pages(2, query)

        toolkit = TestToolkit()

        # Tool should be automatically registered
        assert "search_items" in toolkit.tools
        assert len(toolkit.tools) == 1

        # Test direct method call
        result = toolkit.search_items("test")
        assert len(result) == 2
        assert "test" in result[0].title

        # Test invocation
        invoke_result = toolkit.invoke_tool("search_items", "test")
        assert len(invoke_result["results"]) == 2

    def test_global_tool_decorator_with_options(self) -> None:
        """Test global @tool decorator with various options."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

            @tool(name="custom_search", cache=True, paginate=True, max_docs=1)
            def search_items(self, query: str) -> List[SimpleTestPage]:
                """Search for items with custom options"""
                return create_test_pages(3, query)

        toolkit = TestToolkit()

        # Tool should be registered with custom name
        assert "custom_search" in toolkit.tools
        assert "search_items" not in toolkit.tools

        # Test pagination works
        result = toolkit.invoke_tool("custom_search", "test")
        assert len(result["results"]) == 1  # max_docs=1
        assert "next_cursor" in result

    def test_global_tool_decorator_multiple_tools(self) -> None:
        """Test multiple tools decorated with global @tool decorator."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

            @tool()
            def search_items(self, query: str) -> List[SimpleTestPage]:
                """Search for items"""
                return create_test_pages(1, query)

            @tool(cache=True)
            def search_users(self, name: str) -> List[SimpleTestPage]:
                """Search for users"""
                return create_test_pages(1, name)

        toolkit = TestToolkit()

        # Both tools should be registered
        assert len(toolkit.tools) == 2
        assert "search_items" in toolkit.tools
        assert "search_users" in toolkit.tools

        # Both should work
        items_result = toolkit.search_items("items")
        users_result = toolkit.search_users("users")

        assert len(items_result) == 1
        assert len(users_result) == 1
        assert "items" in items_result[0].title
        assert "users" in users_result[0].title

    def test_global_tool_decorator_non_retriever_toolkit_error(self) -> None:
        """Test that @tool decorator raises error when used on non-RetrieverToolkit classes."""

        # Error should be raised when defining the class (during method assignment)
        with pytest.raises(
            TypeError,
            match="@tool decorator can only be used on RetrieverToolkit classes",
        ):

            class NonRetrieverClass:
                @tool()
                def some_method(self) -> List[SimpleTestPage]:
                    return []

    def test_global_tool_decorator_inherits_from_decorated_class(self) -> None:
        """Test that @tool decorator works with class inheritance."""

        class BaseToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "BaseToolkit"

            @tool()
            def base_search(self, query: str) -> List[SimpleTestPage]:
                """Base search method"""
                return create_test_pages(1, f"base_{query}")

        class DerivedToolkit(BaseToolkit):
            @property
            def name(self) -> str:
                return "DerivedToolkit"

            @tool()
            def derived_search(self, query: str) -> List[SimpleTestPage]:
                """Derived search method"""
                return create_test_pages(1, f"derived_{query}")

        toolkit = DerivedToolkit()

        # Both tools should be available
        assert len(toolkit.tools) == 2
        assert "base_search" in toolkit.tools
        assert "derived_search" in toolkit.tools

        # Both should work
        base_result = toolkit.base_search("test")
        derived_result = toolkit.derived_search("test")

        assert "base_test" in base_result[0].title
        assert "derived_test" in derived_result[0].title

    def test_global_tool_decorator_with_manual_registration(self) -> None:
        """Test that @tool decorator can coexist with manual tool registration."""

        class TestToolkit(RetrieverToolkit):
            def __init__(self):
                super().__init__()
                # Manually register a tool
                self.register_tool(self.manual_tool, "manual_tool")

            @property
            def name(self) -> str:
                return "TestToolkit"

            @tool()
            def decorated_tool(self, query: str) -> List[SimpleTestPage]:
                """Decorated tool"""
                return create_test_pages(1, f"decorated_{query}")

            def manual_tool(self, query: str) -> List[SimpleTestPage]:
                """Manually registered tool"""
                return create_test_pages(1, f"manual_{query}")

        toolkit = TestToolkit()

        # Both tools should be available
        assert len(toolkit.tools) == 2
        assert "decorated_tool" in toolkit.tools
        assert "manual_tool" in toolkit.tools

        # Both should work
        decorated_result = toolkit.decorated_tool("test")
        manual_result = toolkit.manual_tool("test")

        assert "decorated_test" in decorated_result[0].title
        assert "manual_test" in manual_result[0].title
