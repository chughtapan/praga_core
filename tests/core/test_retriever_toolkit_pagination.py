"""Tests for RetrieverToolkit pagination functionality.

This module focuses on testing pagination mechanisms in RetrieverToolkit,
including page sizing, token limits, and pagination edge cases.
"""

from typing import List

import pytest

from praga_core.agents import PaginatedResponse
from praga_core.types import PageURI

from .conftest import (
    SAMPLE_PAGE_SIZES,
    MockRetrieverToolkit,
    SimpleTestPage,
    create_test_pages,
)


class TestRetrieverToolkitPagination:
    """Test pagination functionality via invoke method."""

    def test_direct_call_bypasses_pagination(self) -> None:
        """Test that direct method calls bypass pagination."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(10, "sample")

        def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=True, max_docs=3)

        # Direct call should return all pages without pagination
        result = toolkit.get_all_pages()
        assert isinstance(result, list)
        assert len(result) == 10  # All pages
        assert all(isinstance(page, SimpleTestPage) for page in result)

    def test_invoke_applies_pagination(self) -> None:
        """Test that invoke calls apply pagination when enabled."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(10, "sample")

        def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=True, max_docs=3)

        # Invoke call should apply pagination
        result = toolkit.invoke_tool("get_all_pages", {})
        assert len(result["results"]) == 3
        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_results"] == 10

    def test_pagination_multiple_pages(self) -> None:
        """Test pagination across multiple pages via invoke."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(10, "sample")

        def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=True, max_docs=4)

        # Page 0
        page0 = toolkit.invoke_tool("get_all_pages", {"page": 0})
        assert len(page0["results"]) == 4
        assert page0["page_number"] == 0
        assert page0["has_next_page"] is True

        # Page 1
        page1 = toolkit.invoke_tool("get_all_pages", {"page": 1})
        assert len(page1["results"]) == 4
        assert page1["page_number"] == 1
        assert page1["has_next_page"] is True

        # Page 2 (partial)
        page2 = toolkit.invoke_tool("get_all_pages", {"page": 2})
        assert len(page2["results"]) == 2  # Remaining pages
        assert page2["page_number"] == 2
        assert page2["has_next_page"] is False

    def test_pagination_last_page_detection(self) -> None:
        """Test accurate detection of the last page."""
        toolkit = MockRetrieverToolkit()

        def get_exact_fit() -> List[SimpleTestPage]:
            return create_test_pages(9, "exact")  # 9 docs, 3 per page = exactly 3 pages

        toolkit.register_tool(get_exact_fit, "exact_fit", paginate=True, max_docs=3)

        # Last page should have no next page
        last_page = toolkit.invoke_tool("exact_fit", {"page": 2})
        assert len(last_page["results"]) == 3
        assert last_page["page_number"] == 2
        assert last_page["has_next_page"] is False
        assert last_page["total_results"] == 9

    def test_pagination_beyond_last_page(self) -> None:
        """Test behavior when requesting a page beyond the last page."""
        toolkit = MockRetrieverToolkit()

        def get_few_pages() -> List[SimpleTestPage]:
            return create_test_pages(5, "few")

        toolkit.register_tool(get_few_pages, "few_pages", paginate=True, max_docs=3)

        # Request page beyond available data
        result = toolkit.invoke_tool("few_pages", {"page": 3})
        assert len(result["results"]) == 0
        assert result["page_number"] == 3
        assert result["has_next_page"] is False
        assert result["total_results"] == 5

    def test_invoke_without_pagination(self) -> None:
        """Test invoke on non-paginated tools."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(3, "sample")

        def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=False)

        # Invoke call should not apply pagination
        result = toolkit.invoke_tool("get_all_pages", {})

        assert "results" in result
        assert len(result["results"]) == 3
        # Should not have pagination metadata
        assert "page_number" not in result
        assert "has_next_page" not in result

    def test_pagination_with_different_page_sizes(self) -> None:
        """Test pagination with various page sizes."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(20, "varied")

        def get_pages() -> List[SimpleTestPage]:
            return sample_pages

        for page_size in SAMPLE_PAGE_SIZES:
            tool_name = f"docs_page_{page_size}"
            toolkit.register_tool(
                get_pages, tool_name, paginate=True, max_docs=page_size
            )

            result = toolkit.invoke_tool(tool_name, {"page": 0})
            assert len(result["results"]) == min(page_size, 20)
            assert result["total_results"] == 20

    @pytest.mark.parametrize("page_size", [1, 3, 7, 15])
    def test_pagination_consistency_across_pages(self, page_size: int) -> None:
        """Test that pagination is consistent across all pages."""
        toolkit = MockRetrieverToolkit()
        total_pages = 23  # Prime number to test edge cases
        sample_pages = create_test_pages(total_pages, "consistent")

        def get_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(
            get_pages, "consistent_pages", paginate=True, max_docs=page_size
        )

        collected_pages = []
        page = 0

        while True:
            result = toolkit.invoke_tool("consistent_pages", {"page": page})
            assert result["total_results"] == total_pages
            assert result["page_number"] == page

            if len(result["results"]) == 0:
                break

            collected_pages.extend(result["results"])

            if not result["has_next_page"]:
                break

            page += 1

        # Should have collected all pages exactly once
        assert len(collected_pages) == total_pages
        # Verify no duplicates by checking IDs
        collected_ids = [page["uri"] for page in collected_pages]
        assert len(set(collected_ids)) == total_pages


class TestPaginationWithTokenLimits:
    """Test pagination combined with token limits."""

    def test_pagination_with_token_limits(self) -> None:
        """Test pagination respects token limits."""
        toolkit = MockRetrieverToolkit()

        def get_pages_with_tokens() -> List[SimpleTestPage]:
            pages = []
            for i in range(10):
                page = SimpleTestPage(
                    uri=PageURI.parse(f"test/TextPage:doc{i}@1"),
                    title=f"Document {i}",
                    content="Content " * (i + 1),  # Varying content length
                )
                # Manually set token count for predictable testing
                page._metadata.token_count = (i + 1) * 5  # 5, 10, 15, 20, ...
                pages.append(page)
            return pages

        toolkit.register_tool(
            get_pages_with_tokens,
            "token_limited",
            paginate=True,
            max_docs=5,
            max_tokens=25,
        )

        result = toolkit.invoke_tool("token_limited", {})

        # Should be limited by token count, not max_docs
        # pages 0,1,2,3 have tokens 5,10,15,20 = 50 total (exceeds 25)
        # So should get pages 0,1,2 with tokens 5,10,15 = 30 total, but that still exceeds
        # Actually should get pages 0,1 with tokens 5,10 = 15 total (under 25)
        assert len(result["results"]) <= 3  # Token-limited, fewer than max_docs
        assert result["token_count"] <= 25

    def test_pagination_with_large_first_document(self) -> None:
        """Test pagination when first document exceeds token limit."""
        toolkit = MockRetrieverToolkit()

        def get_pages_with_large_first() -> List[SimpleTestPage]:
            pages = []
            # First document is very large
            large_doc = SimpleTestPage(
                uri=PageURI.parse("test/TextPage:large_doc@1"),
                title="Large Document",
                content="Large content " * 20,
            )
            large_doc._metadata.token_count = 100  # Exceeds any reasonable limit
            pages.append(large_doc)

            # Subsequent documents are small
            for i in range(5):
                small_doc = SimpleTestPage(
                    uri=PageURI.parse(f"test/TextPage:small{i}@1"),
                    title=f"Small {i}",
                    content="Small content",
                )
                small_doc._metadata.token_count = 5
                pages.append(small_doc)
            return pages

        toolkit.register_tool(
            get_pages_with_large_first,
            "large_first",
            paginate=True,
            max_docs=10,
            max_tokens=20,
        )

        result = toolkit.invoke_tool("large_first", {})

        # Should include the large first document despite exceeding token limit
        assert len(result["results"]) == 1
        assert result["results"][0]["uri"] == "test/TextPage:large_doc@1"
        assert result["token_count"] == 100  # Exceeds limit but includes first doc

    def test_pagination_token_counting_accuracy(self) -> None:
        """Test that token counting in pagination is accurate."""
        toolkit = MockRetrieverToolkit()

        def get_counted_pages() -> List[SimpleTestPage]:
            pages = []
            for i in range(8):
                page = SimpleTestPage(
                    uri=PageURI.parse(f"test/TextPage:counted{i}@1"),
                    title=f"Doc {i}",
                    content="Test content",
                )
                page._metadata.token_count = 10  # Each page has exactly 10 tokens
                pages.append(page)
            return pages

        toolkit.register_tool(
            get_counted_pages, "counted", paginate=True, max_docs=10, max_tokens=35
        )

        result = toolkit.invoke_tool("counted", {})

        # Should get 3 pages (30 tokens) but not 4 pages (40 tokens)
        assert len(result["results"]) == 3
        assert result["token_count"] == 30

    def test_token_limits_vs_page_size_priority(self) -> None:
        """Test priority when both token limits and page size apply."""
        toolkit = MockRetrieverToolkit()

        def get_priority_test_pages() -> List[SimpleTestPage]:
            pages = []
            for i in range(10):
                page = SimpleTestPage(
                    uri=PageURI.parse(f"test/TextPage:priority{i}@1"),
                    title=f"Priority Doc {i}",
                    content="Content",
                )
                page._metadata.token_count = 8  # Each page has 8 tokens
                pages.append(page)
            return pages

        # Page size allows 6 docs, but token limit allows only 3 docs (24 tokens)
        toolkit.register_tool(
            get_priority_test_pages,
            "priority",
            paginate=True,
            max_docs=6,
            max_tokens=25,
        )

        result = toolkit.invoke_tool("priority", {})

        # Token limit should take precedence
        assert len(result["results"]) == 3  # Limited by tokens, not page size
        assert result["token_count"] == 24  # 3 pages * 8 tokens each


class TestPaginationEdgeCases:
    """Test edge cases and error conditions in pagination."""

    def test_pagination_with_empty_results(self) -> None:
        """Test pagination behavior with empty result sets."""
        toolkit = MockRetrieverToolkit()

        def get_empty_pages() -> List[SimpleTestPage]:
            return []

        toolkit.register_tool(get_empty_pages, paginate=True, max_docs=5)

        result = toolkit.invoke_tool("get_empty_pages", {})

        # Empty results should return error response per current implementation
        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"
        assert result["references"] == []

    def test_pagination_with_single_document(self) -> None:
        """Test pagination with only one document."""
        toolkit = MockRetrieverToolkit()

        def get_single_pages() -> List[SimpleTestPage]:
            return create_test_pages(1, "single")

        toolkit.register_tool(get_single_pages, paginate=True, max_docs=5)

        result = toolkit.invoke_tool("get_single_pages", {})

        assert len(result["results"]) == 1
        assert result["page_number"] == 0
        assert result["has_next_page"] is False
        assert result["total_results"] == 1

    def test_pagination_invalid_page_number(self) -> None:
        """Test error handling for invalid page numbers."""
        toolkit = MockRetrieverToolkit()

        def get_pages() -> List[SimpleTestPage]:
            return create_test_pages(5, "test")

        toolkit.register_tool(get_pages, paginate=True, max_docs=2)

        # Negative page numbers should raise an error
        with pytest.raises(ValueError, match="Page number must be >= 0"):
            toolkit.invoke_tool("get_pages", {"page": -1})

    def test_pagination_with_paginated_response_tool(self) -> None:
        """Test that tools returning PaginatedResponse work correctly."""
        toolkit = MockRetrieverToolkit()

        def get_paginated_response() -> PaginatedResponse[SimpleTestPage]:
            pages = create_test_pages(10, "paginated")
            return PaginatedResponse(
                results=pages[:3],  # First 3 pages
                page_number=0,
                has_next_page=True,
                total_results=10,
                token_count=sum(page.metadata.token_count or 0 for page in pages[:3]),
            )

        # Should not try to paginate a tool that already returns PaginatedResponse
        with pytest.raises(TypeError, match="Cannot paginate tool"):
            toolkit.register_tool(
                get_paginated_response, "already_paginated", paginate=True
            )

    def test_pagination_preserves_document_order(self) -> None:
        """Test that pagination preserves the original document order."""
        toolkit = MockRetrieverToolkit()

        def get_ordered_pages() -> List[SimpleTestPage]:
            return [
                SimpleTestPage(
                    uri=PageURI.parse(f"test/TextPage:ordered_{i:02d}@1"),
                    title=f"Doc {i:02d}",
                    content="Content",
                )
                for i in range(15)
            ]

        toolkit.register_tool(get_ordered_pages, paginate=True, max_docs=4)

        # Collect documents from multiple pages
        all_collected = []
        for page in range(4):  # Should cover all 15 documents
            result = toolkit.invoke_tool("get_ordered_pages", {"page": page})
            all_collected.extend(result["results"])

        # Verify order is preserved
        for i, doc in enumerate(all_collected):
            expected_id = f"test/TextPage:ordered_{i:02d}@1"
            assert doc["uri"] == expected_id

    def test_pagination_with_zero_max_docs(self) -> None:
        """Test pagination behavior with zero max_docs."""
        toolkit = MockRetrieverToolkit()

        def get_pages() -> List[SimpleTestPage]:
            return create_test_pages(5, "test")

        # Zero max_docs should either raise an error or be handled gracefully
        with pytest.raises((ValueError, TypeError)):
            toolkit.register_tool(get_pages, paginate=True, max_docs=0)
