"""Tests for RetrieverToolkit integration with Tool class."""

from datetime import timedelta
from typing import Any, List

import pytest

from praga_core.agents import RetrieverToolkit
from praga_core.agents.tool import Tool
from praga_core.types import Page, PageURI


class SimpleDocument(Page):
    """Simple document for testing."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


class IntegrationTestToolkit(RetrieverToolkit):
    """Toolkit for testing integration functionality."""

    def __init__(self) -> None:
        super().__init__()

        # Register tool with pagination
        self.register_tool(
            self.search_documents,
            cache=True,
            ttl=timedelta(minutes=5),
            paginate=True,
            max_docs=3,
            max_tokens=1000,
        )

        # Register tool without pagination
        self.register_tool(self.count_documents, cache=False, paginate=False)

        # Register stateless tool
        self.register_tool(get_test_docs, cache=True, paginate=False)

    @property
    def name(self) -> str:
        return "IntegrationTestToolkit"

    async def search_documents(
        self, query: str, limit: int = 10
    ) -> List[SimpleDocument]:
        """Search for documents matching the query."""
        return [
            SimpleDocument(
                uri=PageURI.parse(f"test/SimpleDocument:doc_{i}@1"),
                title=f"Document {i} - {query}",
                content=f"This is content about {query} in document {i}. " * 3,
            )
            for i in range(limit)
        ]

    async def count_documents(self, query: str) -> List[SimpleDocument]:
        """Get a count document."""
        return [
            SimpleDocument(
                uri=PageURI.parse("test/SimpleDocument:count_doc@1"),
                title="Document Count",
                content=f"Found documents for query: {query}",
            )
        ]


async def get_test_docs(category: str = "general") -> List[SimpleDocument]:
    """Stateless function for testing decorator."""
    return [
        SimpleDocument(
            uri=PageURI.parse(f"test/SimpleDocument:test_{i}@1"),
            title=f"Test Document {i}",
            content=f"Test content for {category} category",
        )
        for i in range(3)
    ]


@IntegrationTestToolkit.tool(
    cache=True, ttl=timedelta(minutes=10), paginate=True, max_docs=2
)
async def get_cached_docs(topic: str) -> List[SimpleDocument]:
    """Get cached documents."""
    return [
        SimpleDocument(
            uri=PageURI.parse(f"test/SimpleDocument:cached_{i}@1"),
            title=f"Cached Doc {i}",
            content=f"Cached content about {topic}",
        )
        for i in range(5)
    ]


class TestRetrieverToolkitIntegration:
    """Test RetrieverToolkit integration with Tool class."""

    @pytest.mark.asyncio
    async def test_toolkit_initialization(self) -> None:
        """Test toolkit initializes with correct tools."""
        toolkit = IntegrationTestToolkit()

        expected_tools = {
            "search_documents",
            "count_documents",
            "get_test_docs",
            "get_cached_docs",
        }
        assert set(toolkit.tools.keys()) == expected_tools

    @pytest.mark.asyncio
    async def test_direct_method_call_no_pagination(self) -> None:
        """Test direct method calls bypass pagination."""
        toolkit = IntegrationTestToolkit()

        # Direct call should return all documents without pagination
        docs = await toolkit.search_documents("python", limit=8)

        assert len(docs) == 8
        assert all(isinstance(doc, SimpleDocument) for doc in docs)
        assert "python" in docs[0].title

    @pytest.mark.asyncio
    async def test_invoke_method_with_pagination(self) -> None:
        """Test invoke method applies pagination when enabled."""
        toolkit = IntegrationTestToolkit()

        # Invoke call should apply pagination
        result = await toolkit.invoke_tool(
            "search_documents", {"query": "python", "limit": 8}
        )

        assert "results" in result
        assert "next_cursor" in result

        # Should be paginated to max_docs=3
        assert len(result["results"]) <= 3
        assert result["next_cursor"] is not None  # Has more pages

    @pytest.mark.asyncio
    async def test_invoke_method_pagination_second_page(self) -> None:
        """Test invoke method can get second page."""
        toolkit = IntegrationTestToolkit()

        result = await toolkit.invoke_tool(
            "search_documents", {"query": "python", "limit": 8, "cursor": "3"}
        )

        assert len(result["results"]) <= 3
        assert result["next_cursor"] is not None  # Has more pages

    @pytest.mark.asyncio
    async def test_invoke_method_without_pagination(self) -> None:
        """Test invoke method on non-paginated tool."""
        toolkit = IntegrationTestToolkit()

        # Direct call
        docs_direct = await toolkit.count_documents("test")
        assert len(docs_direct) == 1

        # Invoke call should behave the same for non-paginated tools
        result_invoke = await toolkit.invoke_tool("count_documents", "test")

        assert "results" in result_invoke
        assert len(result_invoke["results"]) == 1
        assert "next_cursor" not in result_invoke  # No pagination metadata

    @pytest.mark.asyncio
    async def test_string_input_for_invoke(self) -> None:
        """Test invoke with string input maps to first parameter."""
        toolkit = IntegrationTestToolkit()

        result = await toolkit.invoke_tool("search_documents", "javascript")

        assert "results" in result
        assert len(result["results"]) <= 3  # Paginated
        doc_content = result["results"][0]["content"]
        assert "javascript" in doc_content

    @pytest.mark.asyncio
    async def test_tool_inspection(self) -> None:
        """Test tool inspection and metadata."""
        toolkit = IntegrationTestToolkit()

        # Get tool objects
        search_tool = toolkit.get_tool("search_documents")
        count_tool = toolkit.get_tool("count_documents")

        assert isinstance(search_tool, Tool)
        assert isinstance(count_tool, Tool)

        assert search_tool.name == "search_documents"
        assert count_tool.name == "count_documents"

        # Check descriptions
        assert "Search for documents" in search_tool.description
        assert "Get a count document" in count_tool.description

    @pytest.mark.asyncio
    async def test_stateless_tool_decorator(self) -> None:
        """Test stateless tool registration with decorator."""
        toolkit = IntegrationTestToolkit()

        # Direct call
        docs_direct = await toolkit.get_cached_docs("AI")
        assert len(docs_direct) == 5
        assert "AI" in docs_direct[0].content

        # Invoke call (should be paginated with max_docs=2)
        result_invoke = await toolkit.invoke_tool("get_cached_docs", "AI")

        assert len(result_invoke["results"]) <= 2
        assert result_invoke["next_cursor"] is not None  # Has more pages

    @pytest.mark.asyncio
    async def test_caching_behavior(self) -> None:
        """Test that caching still works with the new Tool integration."""
        toolkit = IntegrationTestToolkit()

        # First call (should hit the actual function)
        result1 = await toolkit.invoke_tool(
            "search_documents", {"query": "cache_test", "limit": 5}
        )

        # Second call (should hit cache and return same results)
        result2 = await toolkit.invoke_tool(
            "search_documents", {"query": "cache_test", "limit": 5}
        )

        # Results should be identical (cached)
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_different_pages_same_cache(self) -> None:
        """Test that different pages use the same cached underlying data."""
        toolkit = IntegrationTestToolkit()

        # Get page 0
        page0 = await toolkit.invoke_tool(
            "search_documents", {"query": "pagination_test", "limit": 8, "cursor": None}
        )

        # Get page 1 (using cursor from page 0)
        page1 = await toolkit.invoke_tool(
            "search_documents", {"query": "pagination_test", "limit": 8, "cursor": "3"}
        )

        # Documents should be different (different pages)
        page0_ids = [doc["uri"] for doc in page0["results"]]
        page1_ids = [doc["uri"] for doc in page1["results"]]
        assert page0_ids != page1_ids

    @pytest.mark.asyncio
    async def test_error_handling_no_documents(self) -> None:
        """Test error handling is preserved through Tool wrapper."""
        toolkit = IntegrationTestToolkit()

        # Create a method that raises the specific error
        async def failing_search(query: str) -> List[SimpleDocument]:
            if query == "no_results":
                raise ValueError("No matching documents found")
            return []

        toolkit.register_tool(failing_search, "failing_search", paginate=False)

        result = await toolkit.invoke_tool("failing_search", "no_results")

        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"

    @pytest.mark.asyncio
    async def test_tool_not_found(self) -> None:
        """Test error when tool doesn't exist."""
        toolkit = IntegrationTestToolkit()

        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            toolkit.get_tool("nonexistent")

    @pytest.mark.asyncio
    async def test_mixed_usage_patterns(self) -> None:
        """Test that direct calls and invoke calls can be mixed."""
        toolkit = IntegrationTestToolkit()

        # Mix direct and invoke calls
        docs_direct = await toolkit.search_documents("mixed_test", 6)
        result_invoke = await toolkit.invoke_tool(
            "search_documents", {"query": "mixed_test", "limit": 6}
        )

        # Direct call returns all docs
        assert len(docs_direct) == 6

        # Invoke call returns paginated result
        assert len(result_invoke["results"]) <= 3

        # Both should have documents about the same query
        assert "mixed_test" in docs_direct[0].title
        assert "mixed_test" in result_invoke["results"][0]["title"]
