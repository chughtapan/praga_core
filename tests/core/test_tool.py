"""Tests for the Tool class.

This module contains comprehensive tests for the Tool class functionality,
including initialization, invocation, pagination, and error handling.
"""

from typing import Any, List, Optional

import pytest

from praga_core.agents import PaginatedResponse, Tool
from praga_core.types import Page, PageURI


class SimpleDocument(Page):
    """Simple document implementation for testing."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


# Test helper functions
async def create_simple_documents(query: str, limit: int = 5) -> List[SimpleDocument]:
    """Create a list of simple documents for testing."""
    return [
        SimpleDocument(
            uri=PageURI.parse(f"test/SimpleDocument:doc_{i}@1"),
            title=f"Document {i}",
            content=f"Content about {query} - document {i}",
        )
        for i in range(limit)
    ]


async def paginated_function(
    query: str, cursor: Optional[str] = None
) -> PaginatedResponse[SimpleDocument]:
    """Function that returns a paginated response."""
    all_docs = await create_simple_documents(query, 10)

    page_size = 3
    # Parse cursor to get starting position
    start = 0
    if cursor is not None:
        try:
            start = int(cursor)
        except ValueError:
            start = 0

    end = start + page_size
    page_docs = all_docs[start:end]

    # Create next cursor if there are more documents
    next_cursor = str(end) if end < len(all_docs) else None

    return PaginatedResponse(
        results=page_docs,
        next_cursor=next_cursor,
    )


async def failing_function(query: str) -> List[SimpleDocument]:
    """Function that raises exceptions for testing error handling."""
    if query == "no_results":
        raise ValueError("No matching documents found")
    raise RuntimeError("Something went wrong")


class TestToolInitialization:
    """Test Tool class initialization and basic properties."""

    def test_initialization_with_explicit_description(self) -> None:
        """Test Tool initialization with explicit description."""
        tool = Tool(create_simple_documents, "test_tool", "A test tool")

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.func == create_simple_documents

    def test_initialization_with_docstring_description(self) -> None:
        """Test Tool initialization using function docstring as description."""
        tool = Tool(create_simple_documents, "test_tool")

        assert tool.name == "test_tool"
        assert tool.description == "Create a list of simple documents for testing."

    def test_initialization_with_pagination_settings(self) -> None:
        """Test Tool initialization with pagination parameters."""
        tool = Tool(
            create_simple_documents, "paginated_tool", page_size=3, max_tokens=100
        )

        assert tool.name == "paginated_tool"
        assert tool.page_size == 3
        assert tool.max_tokens == 100


class TestToolInvocation:
    """Test Tool invocation with different input types and scenarios."""

    @pytest.mark.asyncio
    async def test_invoke_with_dictionary_input(self) -> None:
        """Test invoking tool with dictionary input."""
        tool = Tool(create_simple_documents, "test_tool")

        result = await tool.invoke({"query": "python", "limit": 3})

        assert "results" in result
        assert len(result["results"]) == 3
        assert result["results"][0]["title"] == "Document 0"
        assert result["results"][0]["content"] == "Content about python - document 0"

    @pytest.mark.asyncio
    async def test_invoke_with_string_input(self) -> None:
        """Test invoking tool with string input (maps to first parameter)."""
        tool = Tool(create_simple_documents, "test_tool")

        result = await tool.invoke("javascript")

        assert "results" in result
        assert len(result["results"]) == 5  # default limit
        assert "javascript" in result["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_invoke_with_paginated_response_function(self) -> None:
        """Test invoking tool that returns PaginatedResponse."""
        tool = Tool(paginated_function, "paginated_tool")

        result = await tool.invoke({"query": "python", "cursor": None})

        # Verify expected pagination fields are present
        expected_fields = {"results", "next_cursor"}
        assert set(result.keys()) == expected_fields

        # Verify pagination values
        assert result["next_cursor"] == "3"  # next cursor points to position 3
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_invoke_paginated_response_last_page(self) -> None:
        """Test invoking paginated tool on the last page."""
        tool = Tool(paginated_function, "paginated_tool")

        result = await tool.invoke({"query": "python", "cursor": "9"})

        assert result["next_cursor"] is None  # No more pages
        assert (
            len(result["results"]) == 1
        )  # 10 total docs, page size 3, last page has 1

    @pytest.mark.asyncio
    async def test_end_to_end_workflow(self) -> None:
        """Test complete workflow from tool creation to result."""
        tool = Tool(create_simple_documents, "search_tool", "Search for documents")

        # Test with string input
        result1 = await tool.invoke("machine learning")
        assert len(result1["results"]) == 5
        assert "machine learning" in result1["results"][0]["content"]

        # Test with dict input
        result2 = await tool.invoke({"query": "AI", "limit": 2})
        assert len(result2["results"]) == 2
        assert "AI" in result2["results"][0]["content"]

        # Verify tool properties
        assert tool.name == "search_tool"
        assert tool.description == "Search for documents"


class TestToolErrorHandling:
    """Test Tool error handling scenarios."""

    @pytest.mark.asyncio
    async def test_error_handling_no_documents_found(self) -> None:
        """Test error handling for 'No matching documents found' error."""
        tool = Tool(failing_function, "failing_tool")

        result = await tool.invoke("no_results")

        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"
        assert result["references"] == []

    @pytest.mark.asyncio
    async def test_error_handling_other_exceptions(self) -> None:
        """Test error handling for other exceptions."""
        tool = Tool(failing_function, "failing_tool")

        with pytest.raises(ValueError, match="Tool execution failed"):
            await tool.invoke("other_error")


class TestToolArgumentProcessing:
    """Test Tool argument preparation and processing."""

    def test_prepare_arguments_string_input(self) -> None:
        """Test argument preparation with string input."""
        tool = Tool(create_simple_documents, "test_tool")

        result = tool._prepare_arguments("test_query")

        assert result == {"query": "test_query"}

    def test_prepare_arguments_dictionary_input(self) -> None:
        """Test argument preparation with dictionary input."""
        tool = Tool(create_simple_documents, "test_tool")

        input_dict = {"query": "test", "limit": 10}
        result = tool._prepare_arguments(input_dict)

        assert result == input_dict


class TestToolResultSerialization:
    """Test Tool result serialization functionality."""

    @pytest.mark.asyncio
    async def test_serialize_document_list(self) -> None:
        """Test serializing a list of documents."""
        tool = Tool(create_simple_documents, "test_tool")
        docs = await create_simple_documents("test", 2)

        result = tool._serialize_result(docs)

        assert "results" in result
        assert len(result["results"]) == 2
        assert result["results"][0]["uri"] == "test/SimpleDocument:doc_0@1"
        assert result["results"][0]["title"] == "Document 0"
        assert result["results"][0]["content"] == "Content about test - document 0"

    @pytest.mark.asyncio
    async def test_serialize_paginated_response(self) -> None:
        """Test serialization of PaginatedResponse results."""
        tool = Tool(paginated_function, "test_tool")
        paginated = await paginated_function("test", None)

        result = tool._serialize_result(paginated)

        assert "next_cursor" in result
        assert result["next_cursor"] == "3"
        assert len(result["results"]) == 3
        assert result["results"][0]["title"] == "Document 0"
        assert result["results"][0]["content"] == "Content about test - document 0"


class TestToolPagination:
    """Test Tool pagination functionality and edge cases."""

    @pytest.mark.asyncio
    async def test_basic_pagination(self) -> None:
        """Test Tool with basic pagination settings."""
        tool = Tool(create_simple_documents, "paginated_tool", page_size=3)

        result = await tool.invoke({"query": "python", "limit": 10, "cursor": None})

        # Verify pagination metadata is added
        expected_keys = {"results", "next_cursor"}
        assert set(result.keys()) == expected_keys

        assert result["next_cursor"] == "3"  # next cursor points to position 3
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_pagination_last_page(self) -> None:
        """Test pagination behavior on the last page."""
        tool = Tool(create_simple_documents, "paginated_tool", page_size=3)

        # Use cursor "9" to get documents starting from position 9 (last page)
        result = await tool.invoke({"query": "python", "limit": 10, "cursor": "9"})

        assert result["next_cursor"] is None  # No more pages
        assert len(result["results"]) == 1

    @pytest.mark.asyncio
    async def test_pagination_page_parameter_injection(self) -> None:
        """Test that cursor parameter is properly injected for pagination."""
        tool = Tool(create_simple_documents, "paginated_tool", page_size=3)

        # Invoke without cursor parameter - should default to cursor None (start from beginning)
        result1 = await tool.invoke({"query": "test", "limit": 10})
        assert result1["next_cursor"] == "3"  # first page ends at position 3

        # Invoke with explicit cursor parameter
        result2 = await tool.invoke({"query": "test", "limit": 10, "cursor": "6"})
        assert (
            result2["next_cursor"] == "9"
        )  # starting from position 6, next cursor is 9

    @pytest.mark.asyncio
    async def test_direct_call_bypasses_pagination(self) -> None:
        """Test that direct tool calls bypass pagination."""
        tool = Tool(create_simple_documents, "paginated_tool", page_size=3)

        # Direct call to the underlying function should return all results
        direct_result = await tool.func("test", 10)
        assert len(direct_result) == 10

        # Invoke call should apply pagination
        invoke_result = await tool.invoke({"query": "test", "limit": 10})
        assert len(invoke_result["results"]) == 3


class TestToolDocumentation:
    """Test Tool documentation and description handling."""

    def test_docstring_description_formatting(self) -> None:
        """Test that docstrings are properly formatted as descriptions."""
        tool = Tool(paginated_function, "test_tool")

        # Should use first line of docstring
        assert tool.description == "Function that returns a paginated response."

    def test_formatted_description_with_pagination(self) -> None:
        """Test that pagination info is added to tool description."""
        tool = Tool(
            create_simple_documents, "paginated_tool", page_size=5, max_tokens=100
        )

        # Should include pagination information in formatted description
        formatted_desc = tool.formatted_description
        assert "paginated" in formatted_desc.lower()
        assert "5" in formatted_desc  # page size
        assert "100" in formatted_desc  # max tokens
