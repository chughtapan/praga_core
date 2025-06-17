"""Tests for the Tool class.

This module contains comprehensive tests for the Tool class functionality,
including initialization, invocation, pagination, and error handling.
"""

from typing import Any, List

import pytest

from praga_core.agents import PaginatedResponse, Tool
from praga_core.types import Page


class SimpleDocument(Page):
    """Simple document implementation for testing."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


# Test helper functions
def create_simple_documents(query: str, limit: int = 5) -> List[SimpleDocument]:
    """Create a list of simple documents for testing."""
    return [
        SimpleDocument(
            id=f"doc_{i}",
            title=f"Document {i}",
            content=f"Content about {query} - document {i}",
        )
        for i in range(limit)
    ]


def simple_function(query: str, limit: int = 5) -> List[SimpleDocument]:
    """Simple function that returns a list of documents."""
    return create_simple_documents(query, limit)


def paginated_function(query: str, page: int = 0) -> PaginatedResponse[SimpleDocument]:
    """Function that returns a paginated response."""
    all_docs = create_simple_documents(query, 10)

    page_size = 3
    start = page * page_size
    end = start + page_size
    page_docs = all_docs[start:end]

    return PaginatedResponse(
        results=page_docs,
        page_number=page,
        has_next_page=end < len(all_docs),
        total_results=len(all_docs),
        token_count=sum(doc.metadata.token_count or 0 for doc in page_docs),
    )


def failing_function(query: str) -> List[SimpleDocument]:
    """Function that raises exceptions for testing error handling."""
    if query == "no_results":
        raise ValueError("No matching documents found")
    raise RuntimeError("Something went wrong")


class TestToolInitialization:
    """Test Tool class initialization and basic properties."""

    def test_initialization_with_explicit_description(self) -> None:
        """Test Tool initialization with explicit description."""
        tool = Tool(simple_function, "test_tool", "A test tool")

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.func == simple_function

    def test_initialization_with_docstring_description(self) -> None:
        """Test Tool initialization using function docstring as description."""
        tool = Tool(simple_function, "test_tool")

        assert tool.name == "test_tool"
        assert tool.description == "Simple function that returns a list of documents."

    def test_initialization_with_pagination_settings(self) -> None:
        """Test Tool initialization with pagination parameters."""
        tool = Tool(simple_function, "paginated_tool", page_size=3, max_tokens=100)

        assert tool.name == "paginated_tool"
        assert tool.page_size == 3
        assert tool.max_tokens == 100


class TestToolInvocation:
    """Test Tool invocation with different input types and scenarios."""

    def test_invoke_with_dictionary_input(self) -> None:
        """Test invoking tool with dictionary input."""
        tool = Tool(simple_function, "test_tool")

        result = tool.invoke({"query": "python", "limit": 3})

        assert "documents" in result
        assert len(result["documents"]) == 3
        assert result["documents"][0]["title"] == "Document 0"
        assert result["documents"][0]["content"] == "Content about python - document 0"

    def test_invoke_with_string_input(self) -> None:
        """Test invoking tool with string input (maps to first parameter)."""
        tool = Tool(simple_function, "test_tool")

        result = tool.invoke("javascript")

        assert "documents" in result
        assert len(result["documents"]) == 5  # default limit
        assert "javascript" in result["documents"][0]["content"]

    def test_invoke_with_paginated_response_function(self) -> None:
        """Test invoking tool that returns PaginatedResponse."""
        tool = Tool(paginated_function, "paginated_tool")

        result = tool.invoke({"query": "python", "page": 0})

        # Verify all expected pagination fields are present
        expected_fields = {
            "documents",
            "page_number",
            "has_next_page",
            "total_documents",
            "token_count",
        }
        assert set(result.keys()) == expected_fields

        # Verify pagination values
        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_documents"] == 10
        assert len(result["documents"]) == 3

    def test_invoke_paginated_response_last_page(self) -> None:
        """Test invoking paginated tool on the last page."""
        tool = Tool(paginated_function, "paginated_tool")

        result = tool.invoke({"query": "python", "page": 3})

        assert result["page_number"] == 3
        assert result["has_next_page"] is False
        assert (
            len(result["documents"]) == 1
        )  # 10 total docs, page size 3, last page has 1

    def test_end_to_end_workflow(self) -> None:
        """Test complete workflow from tool creation to result."""
        tool = Tool(simple_function, "search_tool", "Search for documents")

        # Test with string input
        result1 = tool.invoke("machine learning")
        assert len(result1["documents"]) == 5
        assert "machine learning" in result1["documents"][0]["content"]

        # Test with dict input
        result2 = tool.invoke({"query": "AI", "limit": 2})
        assert len(result2["documents"]) == 2
        assert "AI" in result2["documents"][0]["content"]

        # Verify tool properties
        assert tool.name == "search_tool"
        assert tool.description == "Search for documents"


class TestToolErrorHandling:
    """Test Tool error handling scenarios."""

    def test_error_handling_no_documents_found(self) -> None:
        """Test error handling for 'No matching documents found' error."""
        tool = Tool(failing_function, "failing_tool")

        result = tool.invoke("no_results")

        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"
        assert result["references"] == []

    def test_error_handling_other_exceptions(self) -> None:
        """Test error handling for other exceptions."""
        tool = Tool(failing_function, "failing_tool")

        with pytest.raises(ValueError, match="Tool execution failed"):
            tool.invoke("other_error")


class TestToolArgumentProcessing:
    """Test Tool argument preparation and processing."""

    def test_prepare_arguments_string_input(self) -> None:
        """Test argument preparation with string input."""
        tool = Tool(simple_function, "test_tool")

        result = tool._prepare_arguments("test_query")

        assert result == {"query": "test_query"}

    def test_prepare_arguments_dictionary_input(self) -> None:
        """Test argument preparation with dictionary input."""
        tool = Tool(simple_function, "test_tool")

        input_dict = {"query": "test", "limit": 10}
        result = tool._prepare_arguments(input_dict)

        assert result == input_dict


class TestToolResultSerialization:
    """Test Tool result serialization functionality."""

    def test_serialize_document_list(self) -> None:
        """Test serialization of document list results."""
        tool = Tool(simple_function, "test_tool")
        docs = simple_function("test", 2)

        result = tool._serialize_result(docs)

        assert "documents" in result
        assert len(result["documents"]) == 2
        assert result["documents"][0]["id"] == "doc_0"

    def test_serialize_paginated_response(self) -> None:
        """Test serialization of PaginatedResponse results."""
        tool = Tool(paginated_function, "test_tool")
        paginated = paginated_function("test", 0)

        result = tool._serialize_result(paginated)

        expected_keys = {
            "documents",
            "page_number",
            "has_next_page",
            "total_documents",
            "token_count",
        }
        assert set(result.keys()) == expected_keys


class TestToolPagination:
    """Test Tool pagination functionality and edge cases."""

    def test_basic_pagination(self) -> None:
        """Test Tool with basic pagination settings."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        result = tool.invoke({"query": "python", "limit": 10, "page": 0})

        # Verify pagination metadata is added
        pagination_fields = {
            "page_number",
            "has_next_page",
            "total_documents",
            "token_count",
        }
        assert pagination_fields.issubset(set(result.keys()))

        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_documents"] == 10
        assert len(result["documents"]) == 3

    def test_pagination_last_page(self) -> None:
        """Test pagination behavior on the last page."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        result = tool.invoke({"query": "python", "limit": 10, "page": 3})

        assert result["page_number"] == 3
        assert result["has_next_page"] is False
        assert result["total_documents"] == 10
        assert len(result["documents"]) == 1

    def test_pagination_with_token_limits(self) -> None:
        """Test Tool with both pagination and token limits."""
        # Each document has roughly 5-6 tokens, so max_tokens=10 should limit to ~2 docs
        tool = Tool(simple_function, "token_limited_tool", page_size=5, max_tokens=10)

        result = tool.invoke({"query": "python", "limit": 10})

        # Should be limited by token count, not page size
        assert len(result["documents"]) <= 3  # Token-limited
        assert result["token_count"] <= 10

    def test_pagination_always_includes_one_document(self) -> None:
        """Test that pagination always includes at least one document."""
        tool = Tool(simple_function, "min_doc_tool", page_size=1, max_tokens=1)

        result = tool.invoke({"query": "python", "limit": 10})

        # Should include at least 1 document even with very restrictive token limit
        assert len(result["documents"]) >= 1

    def test_pagination_page_parameter_injection(self) -> None:
        """Test that page parameter is properly injected for pagination."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Invoke without page parameter - should default to page 0
        result1 = tool.invoke({"query": "test", "limit": 10})
        assert result1["page_number"] == 0

        # Invoke with explicit page parameter
        result2 = tool.invoke({"query": "test", "limit": 10, "page": 2})
        assert result2["page_number"] == 2

    def test_direct_call_bypasses_pagination(self) -> None:
        """Test that direct tool calls bypass pagination."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Direct call to the underlying function should return all results
        direct_result = tool.func("test", 10)
        assert len(direct_result) == 10

        # Invoke call should apply pagination
        invoke_result = tool.invoke({"query": "test", "limit": 10})
        assert len(invoke_result["documents"]) == 3


class TestToolDocumentation:
    """Test Tool documentation and description handling."""

    def test_docstring_description_formatting(self) -> None:
        """Test that docstrings are properly formatted as descriptions."""
        tool = Tool(paginated_function, "test_tool")

        # Should use first line of docstring
        assert tool.description == "Function that returns a paginated response."

    def test_formatted_description_with_pagination(self) -> None:
        """Test that pagination info is added to tool description."""
        tool = Tool(simple_function, "paginated_tool", page_size=5, max_tokens=100)

        # Should include pagination information in formatted description
        formatted_desc = tool.formatted_description
        assert "paginated" in formatted_desc.lower()
        assert "5" in formatted_desc  # page size
        assert "100" in formatted_desc  # max tokens
