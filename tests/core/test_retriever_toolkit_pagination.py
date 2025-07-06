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

    @pytest.mark.asyncio
    async def test_direct_call_bypasses_pagination(self) -> None:
        """Test that direct method calls bypass pagination."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(10, "sample")

        async def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=True, max_docs=3)

        # Direct call should return all pages without pagination
        result = await toolkit.get_all_pages()
        assert isinstance(result, list)
        assert len(result) == 10  # All pages
        assert all(isinstance(page, SimpleTestPage) for page in result)

    @pytest.mark.asyncio
    async def test_invoke_applies_pagination(self) -> None:
        """Test that invoke calls apply pagination when enabled."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(10, "sample")

        async def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=True, max_docs=3)

        # Invoke call should apply pagination
        result = await toolkit.invoke_tool("get_all_pages", {})
        assert len(result["results"]) == 3
        assert result["next_cursor"] is not None  # Has more pages

    @pytest.mark.asyncio
    async def test_pagination_multiple_pages(self) -> None:
        """Test pagination across multiple pages via invoke."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(10, "sample")

        async def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=True, max_docs=4)

        # First page
        page0 = await toolkit.invoke_tool("get_all_pages", {"cursor": None})
        assert len(page0["results"]) == 4
        assert page0["next_cursor"] is not None  # Has more pages

        # Second page using cursor from first page
        page1 = await toolkit.invoke_tool(
            "get_all_pages", {"cursor": page0["next_cursor"]}
        )
        assert len(page1["results"]) == 4
        assert page1["next_cursor"] is not None  # Has more pages

        # Third page (partial)
        page2 = await toolkit.invoke_tool(
            "get_all_pages", {"cursor": page1["next_cursor"]}
        )
        assert len(page2["results"]) == 2  # Remaining pages
        assert page2["next_cursor"] is None  # No more pages

    @pytest.mark.asyncio
    async def test_pagination_last_page_detection(self) -> None:
        """Test accurate detection of the last page."""
        toolkit = MockRetrieverToolkit()

        async def get_exact_fit() -> List[SimpleTestPage]:
            return create_test_pages(9, "exact")  # 9 docs, 3 per page = exactly 3 pages

        toolkit.register_tool(get_exact_fit, "exact_fit", paginate=True, max_docs=3)

        # Navigate to last page using cursor
        page0 = await toolkit.invoke_tool("exact_fit", {"cursor": None})
        page1 = await toolkit.invoke_tool("exact_fit", {"cursor": page0["next_cursor"]})
        last_page = await toolkit.invoke_tool(
            "exact_fit", {"cursor": page1["next_cursor"]}
        )

        assert len(last_page["results"]) == 3
        assert last_page["next_cursor"] is None  # No more pages

    @pytest.mark.asyncio
    async def test_invoke_without_pagination(self) -> None:
        """Test invoke on non-paginated tools."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(3, "sample")

        async def get_all_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(get_all_pages, "get_all_pages", paginate=False)

        # Invoke call should not apply pagination
        result = await toolkit.invoke_tool("get_all_pages", {})

        assert "results" in result
        assert len(result["results"]) == 3
        # Should not have pagination metadata
        assert "next_cursor" not in result

    @pytest.mark.asyncio
    async def test_pagination_with_different_page_sizes(self) -> None:
        """Test pagination with various page sizes."""
        toolkit = MockRetrieverToolkit()
        sample_pages = create_test_pages(20, "varied")

        async def get_pages() -> List[SimpleTestPage]:
            return sample_pages

        for page_size in SAMPLE_PAGE_SIZES:
            tool_name = f"docs_page_{page_size}"
            toolkit.register_tool(
                get_pages, tool_name, paginate=True, max_docs=page_size
            )

            result = await toolkit.invoke_tool(tool_name, {"cursor": None})
            assert len(result["results"]) == min(page_size, 20)
            # Check if there are more pages when page_size < 20
            if page_size < 20:
                assert result["next_cursor"] is not None
            else:
                assert result["next_cursor"] is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("page_size", [1, 3, 7, 15])
    async def test_pagination_consistency_across_pages(self, page_size: int) -> None:
        """Test that pagination is consistent across all pages."""
        toolkit = MockRetrieverToolkit()
        total_pages = 23  # Prime number to test edge cases
        sample_pages = create_test_pages(total_pages, "consistent")

        async def get_pages() -> List[SimpleTestPage]:
            return sample_pages

        toolkit.register_tool(
            get_pages, "consistent_pages", paginate=True, max_docs=page_size
        )

        collected_pages = []
        cursor = None

        while True:
            result = await toolkit.invoke_tool("consistent_pages", {"cursor": cursor})

            if len(result["results"]) == 0:
                break

            collected_pages.extend(result["results"])

            if result["next_cursor"] is None:
                break

            cursor = result["next_cursor"]

        # Should have collected all pages exactly once
        assert len(collected_pages) == total_pages
        # Verify no duplicates by checking IDs
        collected_ids = [page["uri"] for page in collected_pages]
        assert len(set(collected_ids)) == total_pages


class TestPaginationWithTokenLimits:
    """Test pagination combined with token limits."""

    def test_pagination_with_token_limits(self) -> None:
        pass

    def test_pagination_with_large_first_document(self) -> None:
        pass

    def test_pagination_token_counting_accuracy(self) -> None:
        pass

    def test_token_limits_vs_page_size_priority(self) -> None:
        pass

    def test_pagination_with_empty_results(self) -> None:
        pass


class TestPaginationEdgeCases:
    """Test edge cases and error conditions in pagination."""

    @pytest.mark.asyncio
    async def test_pagination_with_empty_results(self) -> None:
        """Test pagination behavior with empty result sets."""
        toolkit = MockRetrieverToolkit()

        async def get_empty_pages() -> List[SimpleTestPage]:
            return []

        toolkit.register_tool(get_empty_pages, paginate=True, max_docs=5)

        result = await toolkit.invoke_tool("get_empty_pages", {})

        # Empty results should return error response per current implementation
        assert result["response_code"] == "error_no_documents_found"
        assert result["error_message"] == "No matching documents found"
        assert result["references"] == []

    @pytest.mark.asyncio
    async def test_pagination_with_single_document(self) -> None:
        """Test pagination with only one document."""
        toolkit = MockRetrieverToolkit()

        async def get_single_pages() -> List[SimpleTestPage]:
            return create_test_pages(1, "single")

        toolkit.register_tool(get_single_pages, paginate=True, max_docs=5)

        result = await toolkit.invoke_tool("get_single_pages", {})

        assert len(result["results"]) == 1
        assert result["next_cursor"] is None  # No more pages

    @pytest.mark.asyncio
    async def test_pagination_invalid_cursor(self) -> None:
        """Test error handling for invalid cursor values."""
        toolkit = MockRetrieverToolkit()

        async def get_pages() -> List[SimpleTestPage]:
            return create_test_pages(5, "test")

        toolkit.register_tool(get_pages, paginate=True, max_docs=2)

        # Invalid cursor (non-numeric) should raise an error
        with pytest.raises(ValueError, match="Invalid cursor format"):
            await toolkit.invoke_tool("get_pages", {"cursor": "invalid"})

    @pytest.mark.asyncio
    async def test_pagination_with_paginated_response_tool(self) -> None:
        """Test that tools returning PaginatedResponse work correctly."""
        toolkit = MockRetrieverToolkit()

        async def get_paginated_response() -> PaginatedResponse[SimpleTestPage]:
            pages = create_test_pages(10, "paginated")
            return PaginatedResponse(
                results=pages[:3],  # First 3 pages
                next_cursor="3",  # Cursor pointing to next page
            )

        # Should not try to paginate a tool that already returns PaginatedResponse
        with pytest.raises(TypeError, match="Cannot paginate tool"):
            toolkit.register_tool(
                get_paginated_response, "already_paginated", paginate=True
            )

    @pytest.mark.asyncio
    async def test_pagination_preserves_document_order(self) -> None:
        """Test that pagination preserves the original document order."""
        toolkit = MockRetrieverToolkit()

        async def get_ordered_pages() -> List[SimpleTestPage]:
            return [
                SimpleTestPage(
                    uri=PageURI.parse(f"test/TextPage:ordered_{i:02d}@1"),
                    title=f"Doc {i:02d}",
                    content="Content",
                )
                for i in range(15)
            ]

        toolkit.register_tool(get_ordered_pages, paginate=True, max_docs=4)

        # Collect documents from multiple pages using cursor
        all_collected = []
        cursor = None

        while True:
            result = await toolkit.invoke_tool("get_ordered_pages", {"cursor": cursor})
            if not result["results"]:
                break
            all_collected.extend(result["results"])
            cursor = result["next_cursor"]
            if cursor is None:
                break

        # Verify order is preserved
        for i, doc in enumerate(all_collected):
            expected_id = f"test/TextPage:ordered_{i:02d}@1"
            assert doc["uri"] == expected_id

    @pytest.mark.asyncio
    async def test_pagination_with_zero_max_docs(self) -> None:
        """Test pagination behavior with zero max_docs."""
        toolkit = MockRetrieverToolkit()

        async def get_pages() -> List[SimpleTestPage]:
            return create_test_pages(5, "test")

        # Zero max_docs should either raise an error or be handled gracefully
        with pytest.raises((ValueError, TypeError)):
            toolkit.register_tool(get_pages, paginate=True, max_docs=0)
