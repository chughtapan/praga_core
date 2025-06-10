import time
from datetime import timedelta
from typing import Any, Dict, List

import pytest

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.tool import PaginatedResponse, Tool
from praga_core.types import Document, TextDocument


class MockRetrieverToolkit(RetrieverToolkit):
    """Mock implementation of RetrieverToolkit for testing purposes."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count: int = 0
        self.cache_key_calls: List[str] = []

    def reset_counters(self) -> None:
        """Reset test counters."""
        self.call_count = 0
        self.cache_key_calls = []


# Test fixtures
@pytest.fixture
def toolkit() -> MockRetrieverToolkit:
    """Create a fresh RetrieverToolkit for each test."""
    return MockRetrieverToolkit()


@pytest.fixture
def sample_documents() -> List[Document]:
    """Create sample documents for testing."""
    docs: List[Document] = []
    for i in range(10):
        doc = TextDocument(
            id=f"doc_{i}",
            content=f"This is document {i} with some content.",
        )
        doc._metadata.token_count = 10 + i
        docs.append(doc)
    return docs


class TestCaching:
    """Test caching functionality of the RetrieverToolkit."""

    def test_cache_basic_functionality(self, toolkit: MockRetrieverToolkit) -> None:
        """Test basic caching behavior - cache hits and misses."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return [TextDocument(id="test", content=f"call_{toolkit.call_count}")]

        # Register with caching enabled
        toolkit.register_tool(get_docs, "get_docs", cache=True)

        # First call should execute function
        result1 = toolkit.get_docs()
        assert toolkit.call_count == 1
        assert result1[0].content == "call_1"

        # Second call should use cache
        result2 = toolkit.get_docs()
        assert toolkit.call_count == 1  # No additional call
        assert result2[0].content == "call_1"  # Same content

        # Results should be identical
        assert result1 == result2

    def test_cache_with_different_arguments(
        self, toolkit: MockRetrieverToolkit
    ) -> None:
        """Test that cache distinguishes between different arguments."""

        def get_docs_with_arg(name: str) -> List[Document]:
            toolkit.call_count += 1
            return [TextDocument(id="test", content=f"{name}_{toolkit.call_count}")]

        toolkit.register_tool(get_docs_with_arg, "get_docs_with_arg", cache=True)

        # Different arguments should result in different cache entries
        result1 = toolkit.get_docs_with_arg("arg1")
        result2 = toolkit.get_docs_with_arg("arg2")
        result3 = toolkit.get_docs_with_arg("arg1")  # Should use cache

        assert toolkit.call_count == 2  # Only two actual function calls
        assert result1[0].content == "arg1_1"
        assert result2[0].content == "arg2_2"
        assert result3[0].content == "arg1_1"  # Cached result

    def test_cache_ttl_expiration(self, toolkit: MockRetrieverToolkit) -> None:
        """Test that cache entries expire after TTL."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return [TextDocument(id="test", content=f"call_{toolkit.call_count}")]

        # Register with very short TTL
        toolkit.register_tool(
            get_docs, "get_docs", cache=True, ttl=timedelta(milliseconds=100)
        )

        # First call
        result1 = toolkit.get_docs()
        assert toolkit.call_count == 1

        # Second call immediately - should use cache
        result2 = toolkit.get_docs()
        assert toolkit.call_count == 1
        assert result1 == result2

        # Wait for TTL to expire
        time.sleep(0.15)  # 150ms > 100ms TTL

        # Third call should execute function again
        result3 = toolkit.get_docs()
        assert toolkit.call_count == 2
        assert result3[0].content == "call_2"

    def test_cache_invalidator(self, toolkit: MockRetrieverToolkit) -> None:
        """Test custom cache invalidation logic."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return [TextDocument(id="test", content=f"call_{toolkit.call_count}")]

        # Custom invalidator that always invalidates
        def always_invalidate(cache_key: str, cached_value: Dict[str, Any]) -> bool:
            return False  # Always invalidate

        toolkit.register_tool(
            get_docs, "get_docs", cache=True, invalidator=always_invalidate
        )

        # Each call should execute the function due to invalidation
        result1 = toolkit.get_docs()
        result2 = toolkit.get_docs()

        assert toolkit.call_count == 2
        assert result1[0].content == "call_1"
        assert result2[0].content == "call_2"

    def test_cache_key_generation(self, toolkit: MockRetrieverToolkit) -> None:
        """Test that cache keys are generated consistently."""

        def get_docs(arg1: str, arg2: int = 10) -> List[Document]:
            return [TextDocument(id="test", content="content")]

        # Test cache key generation directly
        key1 = toolkit.make_cache_key(get_docs, "hello", arg2=20)
        key2 = toolkit.make_cache_key(get_docs, "hello", arg2=20)
        key3 = toolkit.make_cache_key(get_docs, "hello", arg2=30)

        assert key1 == key2  # Same args should produce same key
        assert key1 != key3  # Different args should produce different key


class TestPagination:
    """Test pagination functionality via invoke method."""

    def test_direct_call_no_pagination(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test that direct method calls bypass pagination."""

        def get_all_docs() -> List[Document]:
            return sample_documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=3)

        # Direct call should return all documents without pagination
        result = toolkit.get_all_docs()
        assert isinstance(result, list)
        assert len(result) == 10  # All documents
        assert all(isinstance(doc, Document) for doc in result)

    def test_invoke_call_with_pagination(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test that invoke calls apply pagination when enabled."""

        def get_all_docs() -> List[Document]:
            return sample_documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=3)

        # Invoke call should apply pagination
        result = toolkit.invoke_tool("get_all_docs", {})

        assert "documents" in result
        assert "page_number" in result
        assert "has_next_page" in result
        assert "total_documents" in result

        assert len(result["documents"]) == 3
        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_documents"] == 10

    def test_invoke_pagination_multiple_pages(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test pagination across multiple pages via invoke."""

        def get_all_docs() -> List[Document]:
            return sample_documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=4)

        # Page 0
        page0 = toolkit.invoke_tool("get_all_docs", {"page": 0})
        assert len(page0["documents"]) == 4
        assert page0["page_number"] == 0
        assert page0["has_next_page"] is True

        # Page 1
        page1 = toolkit.invoke_tool("get_all_docs", {"page": 1})
        assert len(page1["documents"]) == 4
        assert page1["page_number"] == 1
        assert page1["has_next_page"] is True

        # Page 2 (partial)
        page2 = toolkit.invoke_tool("get_all_docs", {"page": 2})
        assert len(page2["documents"]) == 2  # Remaining documents
        assert page2["page_number"] == 2
        assert page2["has_next_page"] is False

    def test_invoke_without_pagination(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test invoke on non-paginated tools."""

        def get_all_docs() -> List[Document]:
            return sample_documents[:3]

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=False)

        # Invoke call should not apply pagination
        result = toolkit.invoke_tool("get_all_docs", {})

        assert "documents" in result
        assert len(result["documents"]) == 3
        # Should not have pagination metadata
        assert "page_number" not in result
        assert "has_next_page" not in result

    def test_invoke_with_token_limits(self, toolkit: MockRetrieverToolkit) -> None:
        """Test pagination with token count limits via invoke."""

        docs_with_tokens: List[Document] = []
        for doc_id, content, tokens in [
            ("doc_1", "Short", 5),
            ("doc_2", "Medium length", 10),
            ("doc_3", "Very long content", 15),
            ("doc_4", "Another short", 5),
        ]:
            doc = TextDocument(id=doc_id, content=content)
            doc._metadata.token_count = tokens
            docs_with_tokens.append(doc)

        def get_docs_with_tokens() -> List[Document]:
            return docs_with_tokens

        toolkit.register_tool(
            get_docs_with_tokens,
            "get_docs_with_tokens",
            paginate=True,
            max_docs=10,  # High doc limit
            max_tokens=20,  # Low token limit
        )

        result = toolkit.invoke_tool("get_docs_with_tokens", {})

        # Should include doc_1 (5 tokens) + doc_2 (10 tokens) = 15 tokens
        # Should NOT include doc_3 (15 tokens) as it would exceed 20 token limit
        assert len(result["documents"]) == 2
        assert result["documents"][0]["id"] == "doc_1"
        assert result["documents"][1]["id"] == "doc_2"
        assert result["token_count"] == 15

    def test_invoke_with_large_first_document(
        self, toolkit: MockRetrieverToolkit
    ) -> None:
        """Test that at least one document is included even if it exceeds token limit."""

        docs_with_large_first: List[Document] = []
        for doc_id, content, tokens in [
            (
                "large_doc",
                "Extremely long content that exceeds limit",
                3000,
            ),  # Exceeds 2048 default
            ("doc_2", "Short", 10),
            ("doc_3", "Another short", 5),
        ]:
            doc = TextDocument(id=doc_id, content=content)
            doc._metadata.token_count = tokens
            docs_with_large_first.append(doc)

        def get_docs_with_large_first() -> List[Document]:
            return docs_with_large_first

        toolkit.register_tool(
            get_docs_with_large_first,
            "get_docs_with_large_first",
            paginate=True,
            max_docs=10,
            max_tokens=2048,  # Default token limit
        )

        result = toolkit.invoke_tool("get_docs_with_large_first", {})

        # Should include at least the first document, even though it exceeds token limit
        assert len(result["documents"]) >= 1
        assert result["documents"][0]["id"] == "large_doc"
        assert result["token_count"] == 3000  # Just the large document

        # Should have next page since there are more documents available
        assert result["has_next_page"] is True
        assert result["total_documents"] == 3

    def test_has_next_page_with_token_filtering(
        self, toolkit: MockRetrieverToolkit
    ) -> None:
        """Test that has_next_page is correct when documents are filtered by token limits."""

        # Create 20 documents, each with high token count
        docs_many_large: List[Document] = []
        for i in range(20):
            doc = TextDocument(id=f"doc_{i}", content=f"Large content {i}")
            doc._metadata.token_count = 1000  # Each doc is 1000 tokens
            docs_many_large.append(doc)

        def get_many_large_docs() -> List[Document]:
            return docs_many_large

        toolkit.register_tool(
            get_many_large_docs,
            "get_many_large_docs",
            paginate=True,
            max_docs=20,  # High doc limit
            max_tokens=2500,  # Can fit 2 documents (2000 tokens) but not 3 (3000 tokens)
        )

        result = toolkit.invoke_tool("get_many_large_docs", {})

        # Should include 2 documents due to token limit (2000 tokens)
        assert len(result["documents"]) == 2
        assert result["documents"][0]["id"] == "doc_0"
        assert result["documents"][1]["id"] == "doc_1"
        assert result["token_count"] == 2000

        # Should have next page since there are 18 more documents available
        assert result["has_next_page"] is True
        assert result["total_documents"] == 20

    def test_pagination_invalid_return_type(
        self, toolkit: MockRetrieverToolkit
    ) -> None:
        """Test that pagination fails with invalid return types."""

        def returns_paginated_response() -> PaginatedResponse:
            return PaginatedResponse(documents=[], page_number=0, has_next_page=False)

        with pytest.raises(TypeError, match="Cannot paginate tool"):
            toolkit.register_tool(
                returns_paginated_response, "invalid_paginated", paginate=True
            )


class TestToolIntegration:
    """Test Tool class integration with RetrieverToolkit."""

    def test_tool_creation_and_access(self, toolkit: MockRetrieverToolkit) -> None:
        """Test that tools are properly created and accessible."""

        def get_docs() -> List[Document]:
            return [TextDocument(id="test", content="content")]

        toolkit.register_tool(get_docs, "get_docs")

        # Should be able to get tool object
        tool = toolkit.get_tool("get_docs")
        assert isinstance(tool, Tool)
        assert tool.name == "get_docs"
        assert "get_docs" in tool.description

        # Should be accessible as attribute (direct call)
        result = toolkit.get_docs()
        assert len(result) == 1

    def test_tool_invoke_method(self, toolkit: MockRetrieverToolkit) -> None:
        """Test that tool invoke method works correctly."""

        def get_docs(query: str = "default") -> List[Document]:
            return [TextDocument(id="test", content=f"query_{query}")]

        toolkit.register_tool(get_docs, "get_docs")

        tool = toolkit.get_tool("get_docs")

        # Test invoke with dict
        result1 = tool.invoke({"query": "test"})
        assert "documents" in result1
        assert "query_test" in result1["documents"][0]["content"]

        # Test invoke with string (maps to first parameter)
        result2 = tool.invoke("string_query")
        assert "query_string_query" in result2["documents"][0]["content"]

    def test_toolkit_invoke_tool_method(self, toolkit: MockRetrieverToolkit) -> None:
        """Test toolkit's invoke_tool method."""

        def get_docs(query: str) -> List[Document]:
            return [TextDocument(id="test", content=f"query_{query}")]

        toolkit.register_tool(get_docs, "get_docs", paginate=True, max_docs=5)

        # Should work the same as tool.invoke()
        result = toolkit.invoke_tool("get_docs", {"query": "test"})
        assert "documents" in result
        assert "page_number" in result  # Paginated
        assert "query_test" in result["documents"][0]["content"]

    def test_tool_not_found_error(self, toolkit: MockRetrieverToolkit) -> None:
        """Test error handling for non-existent tools."""

        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            toolkit.get_tool("nonexistent")

        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            toolkit.invoke_tool("nonexistent", {})


class TestCombinedFeatures:
    """Test combinations of caching and pagination."""

    def test_cache_and_pagination_together(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test that caching and pagination work together correctly."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return sample_documents

        toolkit.register_tool(
            get_docs, "get_docs", cache=True, paginate=True, max_docs=3
        )

        # First invoke call to page 0
        page0_first = toolkit.invoke_tool("get_docs", {"page": 0})
        assert toolkit.call_count == 1
        assert len(page0_first["documents"]) == 3

        # Second invoke call to page 0 - should use cache
        page0_second = toolkit.invoke_tool("get_docs", {"page": 0})
        assert toolkit.call_count == 1  # No additional function call
        assert page0_first["documents"] == page0_second["documents"]

        # Call to page 1 - should use cache but different page
        page1 = toolkit.invoke_tool("get_docs", {"page": 1})
        assert toolkit.call_count == 1  # Still no additional function call
        assert len(page1["documents"]) == 3
        assert page1["documents"] != page0_first["documents"]

    def test_direct_vs_invoke_caching(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test that both direct and invoke calls use the same cache."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return sample_documents

        toolkit.register_tool(get_docs, "get_docs", cache=True)

        # Direct call first
        direct_result = toolkit.get_docs()
        assert toolkit.call_count == 1

        # Invoke call should use same cache
        invoke_result = toolkit.invoke_tool("get_docs", {})
        assert toolkit.call_count == 1  # No additional call

        # Results should be from same cached data
        assert len(direct_result) == len(invoke_result["documents"])


class TestDecoratorTools:
    """Test the @RetrieverToolkit.tool decorator functionality."""

    def test_decorator_basic_functionality(self) -> None:
        """Test basic decorator-based tool registration."""

        call_count = {"value": 0}

        class DecoratorToolkit(RetrieverToolkit):
            pass

        @DecoratorToolkit.tool()
        def get_basic_docs() -> List[Document]:
            call_count["value"] += 1
            return [TextDocument(id="basic", content=f"call_{call_count['value']}")]

        toolkit = DecoratorToolkit()

        # Tool should be registered automatically
        assert "get_basic_docs" in toolkit.tools

        # Should be callable directly
        result = toolkit.get_basic_docs()
        assert len(result) == 1
        assert result[0].content == "call_1"

        # Should also be invokable
        invoke_result = toolkit.invoke_tool("get_basic_docs", {})
        assert len(invoke_result["documents"]) == 1

    def test_decorator_with_pagination(self, sample_documents: List[Document]) -> None:
        """Test decorator with pagination options."""

        class PaginatedDecoratorToolkit(RetrieverToolkit):
            pass

        @PaginatedDecoratorToolkit.tool(paginate=True, max_docs=4)
        def get_paginated_docs() -> List[Document]:
            return sample_documents

        toolkit = PaginatedDecoratorToolkit()

        # Direct call should return all documents
        direct_result = toolkit.get_paginated_docs()
        assert len(direct_result) == 10

        # Invoke call should be paginated
        invoke_result = toolkit.invoke_tool("get_paginated_docs", {"page": 0})
        assert len(invoke_result["documents"]) == 4
        assert invoke_result["has_next_page"] is True


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_tool_registration(self, toolkit: MockRetrieverToolkit) -> None:
        """Test registration of tools with invalid signatures."""

        def no_return_annotation():  # type: ignore[no-untyped-def]
            return []

        with pytest.raises(TypeError, match="must have return type annotation"):
            toolkit.register_tool(no_return_annotation, "invalid")

    def test_invalid_return_type(self, toolkit: MockRetrieverToolkit) -> None:
        """Test registration of tools with invalid return types."""

        def wrong_return_type() -> str:
            return "not a document list"

        with pytest.raises(TypeError, match="must have return type annotation"):
            toolkit.register_tool(wrong_return_type, "invalid")  # type: ignore[arg-type]

    def test_tool_attribute_access(self, toolkit: MockRetrieverToolkit) -> None:
        """Test accessing tools as attributes."""

        def valid_tool() -> List[Document]:
            return [TextDocument(id="test", content="test")]

        toolkit.register_tool(valid_tool, "my_tool")

        # Should be accessible as attribute (direct call)
        assert hasattr(toolkit, "my_tool")
        result = toolkit.my_tool()
        assert len(result) == 1

        # Should raise AttributeError for non-existent tools
        with pytest.raises(AttributeError):
            _ = toolkit.non_existent_tool

    def test_error_handling_in_invoke(self, toolkit: MockRetrieverToolkit) -> None:
        """Test error handling in tool invoke method."""

        def failing_tool(query: str) -> List[Document]:
            if query == "no_results":
                raise ValueError("No matching documents found")
            raise RuntimeError("Other error")

        toolkit.register_tool(failing_tool, "failing_tool")

        # Should handle specific "No matching documents found" error
        result = toolkit.invoke_tool("failing_tool", "no_results")
        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"

        # Should propagate other errors
        with pytest.raises(ValueError, match="Tool execution failed"):
            toolkit.invoke_tool("failing_tool", "other")
