import time
from datetime import timedelta
from typing import Any, Callable, Dict, List, cast

import pytest

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.types import Document, PageMetadata, PaginatedResponse


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
    return [
        Document(
            id=f"doc_{i}",
            content=f"This is document {i} with some content.",
            metadata={"token_count": 10 + i, "index": i},
        )
        for i in range(10)
    ]


class TestCaching:
    """Test caching functionality of the RetrieverToolkit."""

    def test_cache_basic_functionality(self, toolkit: MockRetrieverToolkit) -> None:
        """Test basic caching behavior - cache hits and misses."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return [Document(id="test", content=f"call_{toolkit.call_count}")]

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
            return [Document(id="test", content=f"{name}_{toolkit.call_count}")]

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
            return [Document(id="test", content=f"call_{toolkit.call_count}")]

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
            return [Document(id="test", content=f"call_{toolkit.call_count}")]

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

    def test_cache_invalidator_conditional(self, toolkit: MockRetrieverToolkit) -> None:
        """Test conditional cache invalidation."""

        def get_docs() -> List[Document]:
            toolkit.call_count += 1
            return [Document(id="test", content=f"call_{toolkit.call_count}")]

        # Invalidator that invalidates after 2 calls
        def conditional_invalidate(
            cache_key: str, cached_value: Dict[str, Any]
        ) -> bool:
            return toolkit.call_count < 2

        toolkit.register_tool(
            get_docs, "get_docs", cache=True, invalidator=conditional_invalidate
        )

        # First call executes
        _ = toolkit.get_docs()
        assert toolkit.call_count == 1

        # Second call uses cache (invalidator returns True)
        _ = toolkit.get_docs()
        assert toolkit.call_count == 1

        # Manually increment to trigger invalidation
        toolkit.call_count = 2

        # Third call should execute due to invalidation
        _ = toolkit.get_docs()
        assert toolkit.call_count == 3

    def test_cache_key_generation(self, toolkit: MockRetrieverToolkit) -> None:
        """Test that cache keys are generated consistently."""

        def get_docs(arg1: str, arg2: int = 10) -> List[Document]:
            return [Document(id="test", content="content")]

        # Test cache key generation directly
        key1 = toolkit.make_cache_key(get_docs, "hello", arg2=20)
        key2 = toolkit.make_cache_key(get_docs, "hello", arg2=20)
        key3 = toolkit.make_cache_key(get_docs, "hello", arg2=30)

        assert key1 == key2  # Same args should produce same key
        assert key1 != key3  # Different args should produce different key


class TestPagination:
    """Test pagination functionality of the RetrieverToolkit."""

    def test_pagination_basic_functionality(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test basic pagination behavior."""

        def get_all_docs() -> List[Document]:
            return sample_documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=3)

        # First page
        result = toolkit.get_all_docs(page=0)
        assert isinstance(result, PaginatedResponse)
        assert len(result.documents) == 3
        assert result.metadata.page_number == 0
        assert result.metadata.has_next_page is True
        assert result.metadata.total_documents == 10

        # Check document IDs
        doc_ids = [doc.id for doc in result.documents]
        assert doc_ids == ["doc_0", "doc_1", "doc_2"]

    def test_pagination_multiple_pages(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test pagination across multiple pages."""

        def get_all_docs() -> List[Document]:
            return sample_documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=4)
        paginated_tool_call = cast(
            Callable[..., PaginatedResponse], toolkit.get_all_docs
        )

        # Page 0
        page0 = paginated_tool_call(page=0)
        assert len(page0.documents) == 4
        assert page0.metadata.page_number == 0
        assert page0.metadata.has_next_page is True

        # Page 1
        page1 = paginated_tool_call(page=1)
        assert len(page1.documents) == 4
        assert page1.metadata.page_number == 1
        assert page1.metadata.has_next_page is True

        # Page 2 (partial)
        page2 = paginated_tool_call(page=2)
        assert len(page2.documents) == 2  # Remaining documents
        assert page2.metadata.page_number == 2
        assert page2.metadata.has_next_page is False

    def test_pagination_last_page(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:  # Added types
        """Test pagination on the last page."""

        def get_all_docs() -> List[Document]:
            return sample_documents[:5]  # Only 5 documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=3)

        # First page
        page0 = toolkit.get_all_docs(page=0)
        assert len(page0.documents) == 3
        assert page0.metadata.has_next_page is True

        # Second page (last page)
        page1 = toolkit.get_all_docs(page=1)
        assert len(page1.documents) == 2
        assert page1.metadata.has_next_page is False

    def test_pagination_empty_page(
        self, toolkit: MockRetrieverToolkit, sample_documents: List[Document]
    ) -> None:
        """Test pagination when requesting a page beyond available data."""

        def get_all_docs() -> List[Document]:
            return sample_documents[:3]  # Only 3 documents

        toolkit.register_tool(get_all_docs, "get_all_docs", paginate=True, max_docs=5)

        # Page 0 has all documents
        page0 = toolkit.get_all_docs(page=0)
        assert len(page0.documents) == 3
        assert page0.metadata.has_next_page is False

        # Page 1 should be empty
        page1 = toolkit.get_all_docs(page=1)
        assert len(page1.documents) == 0
        assert page1.metadata.has_next_page is False

    def test_pagination_with_token_limits(self, toolkit: MockRetrieverToolkit) -> None:
        """Test pagination with token count limits."""

        docs_with_tokens = [
            Document(id="doc_1", content="Short", metadata={"token_count": 5}),
            Document(id="doc_2", content="Medium length", metadata={"token_count": 10}),
            Document(
                id="doc_3", content="Very long content", metadata={"token_count": 15}
            ),
            Document(id="doc_4", content="Another short", metadata={"token_count": 5}),
        ]

        def get_docs_with_tokens() -> List[Document]:
            return docs_with_tokens

        toolkit.register_tool(
            get_docs_with_tokens,
            "get_docs_with_tokens",
            paginate=True,
            max_docs=10,  # High doc limit
            max_tokens=20,  # Low token limit
        )

        result = toolkit.get_docs_with_tokens(page=0)

        # Should include doc_1 (5 tokens) + doc_2 (10 tokens) = 15 tokens
        # Should NOT include doc_3 (15 tokens) as it would exceed 20 token limit
        assert len(result.documents) == 2
        assert result.documents[0].id == "doc_1"
        assert result.documents[1].id == "doc_2"
        assert result.metadata.token_count == 15

    def test_pagination_with_missing_token_metadata(
        self, toolkit: MockRetrieverToolkit
    ) -> None:
        """Test pagination when documents don't have token_count metadata."""

        docs_no_tokens = [
            Document(id="doc_1", content="Content 1"),
            Document(id="doc_2", content="Content 2", metadata={}),
            Document(id="doc_3", content="Content 3", metadata={"other": "data"}),
        ]

        def get_docs_no_tokens() -> List[Document]:
            return docs_no_tokens

        toolkit.register_tool(
            get_docs_no_tokens,
            "get_docs_no_tokens",
            paginate=True,
            max_docs=5,
            max_tokens=10,
        )
        result = toolkit.get_docs_no_tokens(page=0)

        # Should include all documents since they have 0 tokens each
        assert len(result.documents) == 3
        assert result.metadata.token_count == 0

    def test_pagination_invalid_return_type(
        self, toolkit: MockRetrieverToolkit
    ) -> None:
        """Test that pagination fails with invalid return types."""

        def returns_paginated_response() -> PaginatedResponse:
            return PaginatedResponse(
                documents=[], metadata=PageMetadata(page_number=0, has_next_page=False)
            )

        with pytest.raises(TypeError, match="Cannot paginate tool"):
            toolkit.register_tool(
                returns_paginated_response, "invalid_paginated", paginate=True
            )


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

        # First call to page 0
        page0_first = toolkit.get_docs(page=0)
        assert toolkit.call_count == 1
        assert len(page0_first.documents) == 3

        # Second call to page 0 - should use cache
        page0_second = toolkit.get_docs(page=0)
        assert toolkit.call_count == 1  # No additional function call
        assert page0_first.documents == page0_second.documents

        # Call to page 1 - should use cache but different page
        page1 = toolkit.get_docs(page=1)
        assert toolkit.call_count == 1  # Still no additional function call
        assert len(page1.documents) == 3
        assert page1.documents != page0_first.documents


class TestDecoratorTools:
    """Test the @RetrieverToolkit.tool decorator functionality."""

    def test_decorator_basic_functionality(self) -> None:
        """Test basic decorator-based tool registration."""

        call_count = {"value": 0}

        class DecoratorToolkit(RetrieverToolkit):
            pass

        # Define the stateless function outside the class
        @DecoratorToolkit.tool()
        def get_basic_docs() -> List[Document]:
            call_count["value"] += 1
            return [Document(id="basic", content=f"call_{call_count['value']}")]

        toolkit = DecoratorToolkit()

        # Tool should be registered automatically
        assert "get_basic_docs" in toolkit._tools

        # Should be callable
        result = toolkit.get_basic_docs()
        assert len(result) == 1
        assert result[0].content == "call_1"

    def test_decorator_with_caching(self) -> None:
        """Test decorator with caching options."""

        call_count = {"value": 0}

        class CachedDecoratorToolkit(RetrieverToolkit):
            pass

        @CachedDecoratorToolkit.tool(cache=True)
        def get_cached_docs() -> List[Document]:
            call_count["value"] += 1
            return [Document(id="cached", content=f"call_{call_count['value']}")]

        toolkit = CachedDecoratorToolkit()

        # First call
        result1 = toolkit.get_cached_docs()
        assert call_count["value"] == 1

        # Second call should use cache
        result2 = toolkit.get_cached_docs()
        assert call_count["value"] == 1
        assert result1 == result2

    def test_decorator_with_pagination(self, sample_documents: List[Document]) -> None:
        """Test decorator with pagination options."""

        class PaginatedDecoratorToolkit(RetrieverToolkit):
            pass

        @PaginatedDecoratorToolkit.tool(paginate=True, max_docs=4)
        def get_paginated_docs() -> List[Document]:
            return sample_documents

        toolkit = PaginatedDecoratorToolkit()
        result = toolkit.get_paginated_docs(page=0)
        assert isinstance(result, PaginatedResponse)
        assert len(result.documents) == 4
        assert result.metadata.has_next_page is True

    def test_decorator_with_all_options(self, sample_documents: List[Document]) -> None:
        """Test decorator with all options combined."""

        call_count = {"value": 0}

        class FullDecoratorToolkit(RetrieverToolkit):
            pass

        @FullDecoratorToolkit.tool(
            cache=True,
            ttl=timedelta(minutes=5),
            paginate=True,
            max_docs=3,
            max_tokens=50,
        )
        def get_full_featured_docs() -> List[Document]:
            call_count["value"] += 1
            return sample_documents

        toolkit = FullDecoratorToolkit()

        # First call
        result1 = toolkit.get_full_featured_docs(page=0)
        assert call_count["value"] == 1
        assert isinstance(result1, PaginatedResponse)
        assert len(result1.documents) == 3

        # Second call to same page should use cache
        result2 = toolkit.get_full_featured_docs(page=0)
        assert call_count["value"] == 1  # No additional call
        assert result1.documents == result2.documents


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
            return [Document(id="test", content="test")]

        toolkit.register_tool(valid_tool, "my_tool")

        # Should be accessible as attribute
        assert hasattr(toolkit, "my_tool")
        result = toolkit.my_tool()
        assert len(result) == 1

        # Should raise AttributeError for non-existent tools
        with pytest.raises(AttributeError):
            _ = toolkit.non_existent_tool
