"""Tests for core RetrieverToolkit functionality.

This module focuses on testing the core features of RetrieverToolkit,
including tool registration, basic invocation, and toolkit management.
"""

from typing import List, Optional

import pytest
from conftest import MockRetrieverToolkit, SimpleTestDocument, create_test_documents

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.tool import Tool
from praga_core.types import Document


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

        def test_method(query: str) -> List[SimpleTestDocument]:
            return create_test_documents(3, query)

        toolkit.register_tool(test_method, "test_tool")

        assert "test_tool" in toolkit.tools
        assert isinstance(toolkit.get_tool("test_tool"), Tool)

    def test_tool_registration_with_function(self) -> None:
        """Test registering a standalone function as a tool."""

        def standalone_function(query: str, limit: int = 5) -> List[SimpleTestDocument]:
            return create_test_documents(limit, query)

        toolkit = MockRetrieverToolkit()
        toolkit.register_tool(standalone_function, "standalone_tool")

        assert "standalone_tool" in toolkit.tools
        tool = toolkit.get_tool("standalone_tool")
        assert tool.name == "standalone_tool"

    def test_tool_registration_with_function_no_name(self) -> None:
        """Test registering a standalone function as a tool without a name."""

        def standalone_function(query: str, limit: int = 5) -> List[SimpleTestDocument]:
            return create_test_documents(limit, query)

        toolkit = MockRetrieverToolkit()
        toolkit.register_tool(standalone_function)

    def test_tool_registration_with_custom_description(self) -> None:
        """Test tool registration with custom description via docstring."""

        def test_func() -> List[SimpleTestDocument]:
            """Custom description for this tool"""
            return []

        toolkit = MockRetrieverToolkit()
        toolkit.register_tool(test_func, "custom_tool")

        tool = toolkit.get_tool("custom_tool")
        assert tool.description == "Custom description for this tool"

    def test_get_tool_success(self) -> None:
        """Test successful tool retrieval."""
        toolkit = MockRetrieverToolkit()

        def sample_tool() -> List[SimpleTestDocument]:
            return create_test_documents(1)

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

        def tool1() -> List[SimpleTestDocument]:
            return []

        def tool2() -> List[SimpleTestDocument]:
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

        def simple_tool(query: str) -> List[SimpleTestDocument]:
            return create_test_documents(2, query)

        toolkit.register_tool(simple_tool, "simple_tool")
        result = toolkit.invoke_tool("simple_tool", "test_query")

        assert "documents" in result
        assert len(result["documents"]) == 2
        assert "test_query" in result["documents"][0]["title"]

    def test_invoke_tool_with_dict_args(self) -> None:
        """Test tool invocation with dictionary arguments."""
        toolkit = MockRetrieverToolkit()

        def parameterized_tool(query: str, limit: int = 5) -> List[SimpleTestDocument]:
            return create_test_documents(limit, query)

        toolkit.register_tool(parameterized_tool, "param_tool")
        result = toolkit.invoke_tool("param_tool", {"query": "test", "limit": 3})

        assert len(result["documents"]) == 3

    def test_invoke_tool_not_found(self) -> None:
        """Test invoking a non-existent tool raises appropriate error."""
        toolkit = MockRetrieverToolkit()

        with pytest.raises(ValueError, match="Tool 'missing_tool' not found"):
            toolkit.invoke_tool("missing_tool", "test")

    def test_direct_method_access(self) -> None:
        """Test that registered tools are accessible as toolkit methods."""
        toolkit = MockRetrieverToolkit()

        def accessible_tool(name: str) -> List[SimpleTestDocument]:
            return [
                SimpleTestDocument(id="test", title="Test", content=f"Hello {name}")
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
            def get_document_by_id(self, document_id: str) -> Optional[Document]:
                """Get document by ID - mock implementation returns None."""
                return None

        @TestToolkit.tool()
        def decorated_tool(query: str) -> List[SimpleTestDocument]:
            return create_test_documents(2, query)

        toolkit = TestToolkit()

        assert "decorated_tool" in toolkit.tools
        result = toolkit.invoke_tool("decorated_tool", "test")
        assert len(result["documents"]) == 2

    def test_decorator_with_description(self) -> None:
        """Test decorator uses function docstring for description."""

        class TestToolkit(RetrieverToolkit):
            def get_document_by_id(self, document_id: str) -> Optional[Document]:
                """Get document by ID - mock implementation returns None."""
                return None

        @TestToolkit.tool()
        def described_tool() -> List[SimpleTestDocument]:
            """Custom decorated tool description"""
            return []

        toolkit = TestToolkit()
        tool = toolkit.get_tool("described_tool")
        assert tool.description == "Custom decorated tool description"

    def test_multiple_decorated_tools(self) -> None:
        """Test multiple tools decorated on the same toolkit."""

        class MultiToolkit(RetrieverToolkit):
            def get_document_by_id(self, document_id: str) -> Optional[Document]:
                """Get document by ID - mock implementation returns None."""
                return None

        @MultiToolkit.tool()
        def tool_one() -> List[SimpleTestDocument]:
            return create_test_documents(1, "one")

        @MultiToolkit.tool()
        def tool_two() -> List[SimpleTestDocument]:
            return create_test_documents(2, "two")

        toolkit = MultiToolkit()

        assert len(toolkit.tools) == 2
        assert "tool_one" in toolkit.tools
        assert "tool_two" in toolkit.tools

    def test_decorator_inheritance(self) -> None:
        """Test that decorated tools work with toolkit inheritance."""

        class BaseToolkit(RetrieverToolkit):
            def get_document_by_id(self, document_id: str) -> Optional[Document]:
                """Get document by ID - mock implementation returns None."""
                return None

        @BaseToolkit.tool()
        def base_tool() -> List[SimpleTestDocument]:
            return create_test_documents(1, "base")

        class DerivedToolkit(BaseToolkit):
            pass

        @DerivedToolkit.tool()
        def derived_tool() -> List[SimpleTestDocument]:
            return create_test_documents(1, "derived")

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
            toolkit.register_tool(wrong_return_type, "wrong_tool")

    def test_tool_execution_error_handling(self) -> None:
        """Test error handling during tool execution."""
        toolkit = MockRetrieverToolkit()

        def failing_tool(query: str) -> List[SimpleTestDocument]:
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

        def tool1() -> List[SimpleTestDocument]:
            return create_test_documents(1, "first")

        def tool2() -> List[SimpleTestDocument]:
            return create_test_documents(1, "second")

        # Register first tool
        toolkit.register_tool(tool1, "duplicate_name")
        first_result = toolkit.invoke_tool("duplicate_name", {})

        # Register second tool with same name (should replace first)
        toolkit.register_tool(tool2, "duplicate_name")
        second_result = toolkit.invoke_tool("duplicate_name", {})

        # Results should be different, confirming replacement
        assert (
            first_result["documents"][0]["title"]
            != second_result["documents"][0]["title"]
        )
        assert "second" in second_result["documents"][0]["title"]
