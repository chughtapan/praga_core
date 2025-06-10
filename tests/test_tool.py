"""Tests for the Tool class."""

from typing import Any, List

import pytest

from praga_core.tool import PaginatedResponse, Tool
from praga_core.types import Document


class SimpleDocument(Document):
    """Simple document for testing."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


def simple_function(query: str, limit: int = 5) -> List[SimpleDocument]:
    """Simple function that returns a list of documents."""
    return [
        SimpleDocument(
            id=f"doc_{i}",
            title=f"Document {i}",
            content=f"Content about {query} - document {i}",
        )
        for i in range(limit)
    ]


def paginated_function(query: str, page: int = 0) -> PaginatedResponse:
    """Function that returns a paginated response."""
    all_docs = [
        SimpleDocument(
            id=f"doc_{i}",
            title=f"Document {i}",
            content=f"Content about {query} - document {i}",
        )
        for i in range(10)
    ]

    page_size = 3
    start = page * page_size
    end = start + page_size
    page_docs = all_docs[start:end]

    return PaginatedResponse(
        documents=page_docs,
        page_number=page,
        has_next_page=end < len(all_docs),
        total_documents=len(all_docs),
        token_count=sum(doc.metadata.token_count or 0 for doc in page_docs),
    )


def failing_function(query: str) -> List[SimpleDocument]:
    """Function that always raises an exception."""
    if query == "no_results":
        raise ValueError("No matching documents found")
    raise RuntimeError("Something went wrong")


class TestTool:
    """Test cases for the Tool class."""

    def test_tool_initialization(self) -> None:
        """Test Tool initialization."""
        tool = Tool(simple_function, "test_tool", "A test tool")

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.func == simple_function

    def test_tool_initialization_with_docstring(self) -> None:
        """Test Tool initialization using function docstring."""
        tool = Tool(simple_function, "test_tool")

        assert tool.name == "test_tool"
        assert tool.description == "Simple function that returns a list of documents."

    def test_invoke_with_dict_input(self) -> None:
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

    def test_invoke_with_paginated_response(self) -> None:
        """Test invoking tool that returns PaginatedResponse."""
        tool = Tool(paginated_function, "paginated_tool")

        result = tool.invoke({"query": "python", "page": 0})

        assert "documents" in result
        assert "page_number" in result
        assert "has_next_page" in result
        assert "total_documents" in result
        assert "token_count" in result

        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_documents"] == 10
        assert len(result["documents"]) == 3

    def test_invoke_with_paginated_response_last_page(self) -> None:
        """Test invoking paginated tool on last page."""
        tool = Tool(paginated_function, "paginated_tool")

        result = tool.invoke({"query": "python", "page": 3})

        assert result["page_number"] == 3
        assert result["has_next_page"] is False
        assert (
            len(result["documents"]) == 1
        )  # 10 total docs, page size 3, so last page has 1

    def test_invoke_error_handling_no_documents(self) -> None:
        """Test error handling for 'No matching documents found' error."""
        tool = Tool(failing_function, "failing_tool")

        result = tool.invoke("no_results")

        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"
        assert result["references"] == []

    def test_invoke_error_handling_other_errors(self) -> None:
        """Test error handling for other exceptions."""
        tool = Tool(failing_function, "failing_tool")

        with pytest.raises(ValueError, match="Tool execution failed"):
            tool.invoke("other_error")

    def test_prepare_arguments_string_input(self) -> None:
        """Test _prepare_arguments with string input."""
        tool = Tool(simple_function, "test_tool")

        result = tool._prepare_arguments("test_query")

        assert result == {"query": "test_query"}

    def test_prepare_arguments_dict_input(self) -> None:
        """Test _prepare_arguments with dict input."""
        tool = Tool(simple_function, "test_tool")

        input_dict = {"query": "test", "limit": 10}
        result = tool._prepare_arguments(input_dict)

        assert result == input_dict

    def test_serialize_result_list(self) -> None:
        """Test _serialize_result with list of documents."""
        tool = Tool(simple_function, "test_tool")
        docs = simple_function("test", 2)

        result = tool._serialize_result(docs)

        assert "documents" in result
        assert len(result["documents"]) == 2
        assert result["documents"][0]["id"] == "doc_0"

    def test_serialize_result_paginated_response(self) -> None:
        """Test _serialize_result with PaginatedResponse."""
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

    def test_end_to_end_workflow(self) -> None:
        """Test complete workflow from invoke to serialized result."""
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


class TestToolPagination:
    """Test cases for Tool pagination functionality."""

    def test_tool_with_pagination_basic(self) -> None:
        """Test Tool with basic pagination (no token limits)."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Test first page
        result = tool.invoke({"query": "python", "limit": 10, "page": 0})

        assert "documents" in result
        assert "page_number" in result
        assert "has_next_page" in result
        assert "total_documents" in result
        assert "token_count" in result

        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_documents"] == 10
        assert len(result["documents"]) == 3

    def test_tool_with_pagination_last_page(self) -> None:
        """Test Tool pagination on last page."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Test last page (10 total, page size 3, so page 3 has 1 document)
        result = tool.invoke({"query": "python", "limit": 10, "page": 3})

        assert result["page_number"] == 3
        assert result["has_next_page"] is False
        assert result["total_documents"] == 10
        assert len(result["documents"]) == 1

    def test_tool_with_pagination_and_token_limits(self) -> None:
        """Test Tool with both pagination and token limits."""
        # Each document has roughly 5-6 tokens, so max_tokens=10 should limit to ~2 docs
        tool = Tool(simple_function, "token_limited_tool", page_size=5, max_tokens=10)

        result = tool.invoke({"query": "python", "limit": 10, "page": 0})

        assert result["page_number"] == 0
        assert result["total_documents"] == 10
        # Should be limited by tokens, not by page size
        assert len(result["documents"]) <= 3
        assert result["token_count"] <= 10

    def test_tool_pagination_always_includes_one_document(self) -> None:
        """Test that pagination always includes at least one document per page."""
        # Create a tool with very low token limit
        tool = Tool(simple_function, "minimal_tool", page_size=5, max_tokens=1)

        result = tool.invoke({"query": "python", "limit": 10, "page": 0})

        # Should always include at least one document, even if it exceeds token limit
        assert len(result["documents"]) >= 1
        assert result["page_number"] == 0

    def test_tool_direct_call_vs_invoke(self) -> None:
        """Test that direct calls to Tool still use pagination, but invoke serializes the result."""
        tool = Tool(simple_function, "dual_mode_tool", page_size=3)

        # Direct call to tool should still use pagination and return PaginatedResponse
        direct_result = tool(query="python", limit=10)
        assert isinstance(direct_result, PaginatedResponse)
        assert len(direct_result.documents) == 3  # Paginated
        assert direct_result.page_number == 0
        assert direct_result.has_next_page is True

        # Invoke call should use pagination and serialize to dict
        invoke_result = tool.invoke({"query": "python", "limit": 10, "page": 0})
        assert isinstance(invoke_result, dict)
        assert invoke_result["page_number"] == 0
        assert len(invoke_result["documents"]) == 3
        assert invoke_result["has_next_page"] is True

    def test_tool_pagination_page_parameter_added(self) -> None:
        """Test that page parameter is automatically added to paginated tools."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Check that page parameter was added to the function signature
        assert "page" in tool.parameters
        page_param = tool.parameters["page"]
        assert page_param.default == 0
        assert page_param.annotation == int

    def test_tool_pagination_docstring_updated(self) -> None:
        """Test that docstring is updated for paginated tools."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Check that docstring mentions pagination
        assert "page: Page number (starting from 0)" in tool.description
        assert "PaginatedResponse" in tool.description

    def test_tool_formatted_description_with_pagination(self) -> None:
        """Test formatted description includes pagination info."""
        tool = Tool(simple_function, "paginated_tool", page_size=3, max_tokens=100)

        description = tool.formatted_description
        assert "Paginated with 3 items per page, max 100 tokens" in description

    def test_tool_pagination_error_handling(self) -> None:
        """Test error handling in pagination scenarios."""
        tool = Tool(simple_function, "paginated_tool", page_size=3)

        # Test negative page number
        with pytest.raises(ValueError, match="Page number must be >= 0"):
            tool.invoke({"query": "python", "limit": 10, "page": -1})

        # Test no documents found
        result = tool.invoke({"query": "python", "limit": 0})
        assert result["response_code"] == "error_no_documents_found"

    def test_toolkit_integration_pagination_bypass(self) -> None:
        """Test that toolkit direct calls bypass pagination while invoke_tool uses it."""
        from praga_core.retriever_toolkit import RetrieverToolkit

        toolkit = RetrieverToolkit()

        # Register a method with pagination enabled
        toolkit.register_tool(
            method=simple_function,
            name="search_docs",
            paginate=True,
            max_docs=3,
            max_tokens=100,
        )

        # Direct call to toolkit method should bypass pagination
        direct_result = toolkit.search_docs(query="python", limit=10)
        assert len(direct_result) == 10  # All documents returned
        assert not isinstance(direct_result, PaginatedResponse)

        # invoke_tool should use pagination
        invoke_result = toolkit.invoke_tool(
            "search_docs", {"query": "python", "limit": 10, "page": 0}
        )
        assert isinstance(invoke_result, dict)
        assert invoke_result["page_number"] == 0
        assert len(invoke_result["documents"]) == 3  # Paginated
        assert invoke_result["has_next_page"] is True
