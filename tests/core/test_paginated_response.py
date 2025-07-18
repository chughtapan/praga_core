"""Tests for PaginatedResponse classes.

This module tests the PaginatedResponse implementation and its Sequence protocol
behavior.
"""

import math
from collections.abc import Sequence
from typing import List

import pytest

from praga_core import PageURI, TextPage
from praga_core.agents import PaginatedResponse


class SimpleTestPageBasics:
    """Test basic Page and TextPage functionality."""

    def test_text_document_creation(self) -> None:
        """Test basic TextPage creation and auto-calculated fields."""
        page = TextPage(
            uri=PageURI.parse("test/TextPage:test_id@1"), content="test content"
        )

        assert page.uri.id == "test_id"
        assert page.content == "test content"
        assert page.metadata.token_count is not None
        assert page.metadata.token_count > 0

    def test_text_document_with_custom_metadata(self) -> None:
        """Test TextPage with additional metadata fields."""
        page = TextPage(
            uri=PageURI.parse("test/TextPage:test_id@1"), content="test content"
        )

        # Add custom fields to metadata (thanks to Config.extra = "allow")
        page.metadata.custom_field = "custom_value"  # type: ignore[attr-defined]
        page.metadata.count = 42  # type: ignore[attr-defined]

        assert page.metadata.custom_field == "custom_value"  # type: ignore[attr-defined]
        assert page.metadata.count == 42  # type: ignore[attr-defined]

    def test_document_token_count_calculation(self) -> None:
        """Test that token count is calculated correctly."""
        page = TextPage(
            uri=PageURI.parse("test/TextPage:test_id@1"), content="hello world test"
        )

        # Should be approximately 3 words * 4/3 = 4 tokens
        expected_tokens = math.ceil(3 * 4 / 3)
        assert page.metadata.token_count == expected_tokens


class TestPaginatedResponseSequenceProtocol:
    """Test that PaginatedResponse behaves like a Sequence."""

    @pytest.fixture
    def sample_pages(self) -> List[TextPage]:
        """Create sample pages for testing."""
        pages: List[TextPage] = []
        for i in range(1, 4):
            page = TextPage(
                uri=PageURI.parse(f"test/TextPage:doc{i}@1"), content=f"Content {i}"
            )
            page.metadata.index = i  # type: ignore[attr-defined]
            pages.append(page)
        return pages

    @pytest.fixture
    def paginated_response(
        self, sample_pages: List[TextPage]
    ) -> PaginatedResponse[TextPage]:
        """Create a sample PaginatedResponse for testing."""
        return PaginatedResponse(
            results=sample_pages,
            next_cursor="next_cursor_token",
        )

    @pytest.fixture
    def empty_paginated_response(self) -> PaginatedResponse[TextPage]:
        """Create an empty PaginatedResponse for testing."""
        return PaginatedResponse(
            results=[],
            next_cursor=None,
        )

    def test_implements_sequence_protocol(
        self, paginated_response: PaginatedResponse[TextPage]
    ) -> None:
        """Test that PaginatedResponse implements the Sequence protocol."""
        assert isinstance(paginated_response, Sequence)

    def test_length_operations(
        self,
        paginated_response: PaginatedResponse[TextPage],
        empty_paginated_response: PaginatedResponse[TextPage],
    ) -> None:
        """Test __len__ method."""
        assert len(paginated_response) == 3
        assert len(empty_paginated_response) == 0

    def test_index_access(
        self,
        paginated_response: PaginatedResponse[TextPage],
        sample_pages: List[TextPage],
    ) -> None:
        """Test __getitem__ method with integer indices."""
        # Test positive indices
        assert paginated_response[0] == sample_pages[0]
        assert paginated_response[1] == sample_pages[1]
        assert paginated_response[2] == sample_pages[2]

        # Test negative indices
        assert paginated_response[-1] == sample_pages[2]
        assert paginated_response[-2] == sample_pages[1]
        assert paginated_response[-3] == sample_pages[0]

    def test_slice_access(
        self,
        paginated_response: PaginatedResponse[TextPage],
        sample_pages: List[TextPage],
    ) -> None:
        """Test __getitem__ method with slice objects."""
        # Test basic slicing
        assert list(paginated_response[1:]) == sample_pages[1:]
        assert list(paginated_response[:2]) == sample_pages[:2]
        assert list(paginated_response[1:3]) == sample_pages[1:3]

        # Test step slicing
        assert list(paginated_response[::2]) == sample_pages[::2]

    def test_index_errors(
        self,
        paginated_response: PaginatedResponse[TextPage],
        empty_paginated_response: PaginatedResponse[TextPage],
    ) -> None:
        """Test __getitem__ method raises IndexError for invalid indices."""
        with pytest.raises(IndexError):
            paginated_response[10]

        with pytest.raises(IndexError):
            paginated_response[-10]

        with pytest.raises(IndexError):
            empty_paginated_response[0]

    def test_iteration_behavior(
        self,
        paginated_response: PaginatedResponse[TextPage],
        sample_pages: List[TextPage],
    ) -> None:
        """Test __iter__ method and iteration patterns."""
        # Test basic iteration
        iterated_docs = list(paginated_response)
        assert iterated_docs == sample_pages

        # Test that we can iterate multiple times
        count = 0
        for _ in paginated_response:
            count += 1
        assert count == 3

        # Test reverse iteration
        reversed_docs = list(reversed(paginated_response))
        expected = list(reversed(sample_pages))
        assert reversed_docs == expected

    def test_empty_iteration(
        self, empty_paginated_response: PaginatedResponse[TextPage]
    ) -> None:
        """Test iteration over empty response."""
        iterated_docs = list(empty_paginated_response)
        assert iterated_docs == []

    def test_boolean_conversion(
        self,
        paginated_response: PaginatedResponse[TextPage],
        empty_paginated_response: PaginatedResponse[TextPage],
    ) -> None:
        """Test __bool__ method and truthiness."""
        assert bool(paginated_response) is True
        assert bool(empty_paginated_response) is False

        # Test in conditional contexts
        if paginated_response:
            assert True
        else:
            pytest.fail("Non-empty response should be truthy")

        if empty_paginated_response:
            pytest.fail("Empty response should be falsy")
        else:
            assert True

    def test_membership_testing(
        self,
        paginated_response: PaginatedResponse[TextPage],
        sample_pages: List[TextPage],
    ) -> None:
        """Test __contains__ method."""
        # Test with pages that are in the response
        assert sample_pages[0] in paginated_response
        assert sample_pages[1] in paginated_response
        assert sample_pages[2] in paginated_response

        # Test with page that's not in the response
        not_in_response = TextPage(
            uri=PageURI.parse("test/TextPage:not_in_response@1"),
            content="Different content",
        )
        assert not_in_response not in paginated_response

    def test_membership_empty_response(
        self, empty_paginated_response: PaginatedResponse[TextPage]
    ) -> None:
        """Test __contains__ method with empty response."""
        page = TextPage(
            uri=PageURI.parse("test/TextPage:test@1"), content="Test content"
        )
        assert page not in empty_paginated_response


class TestPaginatedResponseUtilityMethods:
    """Test utility methods and advanced functionality of PaginatedResponse."""

    def test_equality_comparison(self) -> None:
        """Test equality between PaginatedResponse instances."""
        sample_pages = [
            TextPage(uri=PageURI.parse("test/TextPage:doc1@1"), content="Content 1")
        ]

        response1 = PaginatedResponse(results=sample_pages, next_cursor="cursor1")
        response2 = PaginatedResponse(results=sample_pages, next_cursor="cursor1")
        response3 = PaginatedResponse(results=sample_pages, next_cursor="cursor2")

        assert response1 == response2  # Same content
        assert response1 != response3  # Different cursor

    def test_sequence_methods_simulation(self) -> None:
        """Test sequence-like methods that can be simulated."""
        pages = [
            TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="First"),
            TextPage(uri=PageURI.parse("test/TextPage:2@1"), content="Second"),
            TextPage(
                uri=PageURI.parse("test/TextPage:1@1"), content="First"
            ),  # Duplicate for testing
        ]
        response = PaginatedResponse(results=pages, next_cursor=None)

        # Test index-like functionality (finding position of page)
        def find_index(
            response: PaginatedResponse[TextPage], target_page: TextPage
        ) -> int:
            for i, page in enumerate(response):
                if page == target_page:
                    return i
            raise ValueError("Page not found")

        assert find_index(response, pages[0]) == 0
        assert find_index(response, pages[1]) == 1

        # Test with non-existent page
        other_page = TextPage(
            uri=PageURI.parse("test/TextPage:other@1"), content="Other"
        )
        with pytest.raises(ValueError):
            find_index(response, other_page)


class TestPaginatedResponseEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_page_response(self) -> None:
        """Test PaginatedResponse with a single page."""
        page = TextPage(
            uri=PageURI.parse("test/TextPage:single@1"), content="Single page"
        )
        response = PaginatedResponse(results=[page], next_cursor=None)

        assert len(response) == 1
        assert response[0] == page
        assert response[-1] == page
        assert list(response) == [page]
        assert bool(response) is True

    def test_large_response_performance(self) -> None:
        """Test PaginatedResponse with many pages."""
        pages = [
            TextPage(
                uri=PageURI.parse(f"test/TextPage:doc{i}@1"), content=f"Content {i}"
            )
            for i in range(100)
        ]
        response = PaginatedResponse(results=pages, next_cursor="large_cursor")

        # Test that operations are efficient
        assert len(response) == 100
        assert response[50].uri.id == "doc50"
        assert response[-1].uri.id == "doc99"

        # Test slicing doesn't cause performance issues
        subset = list(response[25:75])
        assert len(subset) == 50
        assert subset[0].uri.id == "doc25"

    def test_response_with_complex_pages(self) -> None:
        """Test PaginatedResponse with pages containing complex metadata."""
        pages = []
        for i in range(3):
            page = TextPage(
                uri=PageURI.parse(f"test/TextPage:complex{i}@1"),
                content=f"Complex content {i}",
            )
            page.metadata.tags = [f"tag_{i}", f"category_{i % 2}"]  # type: ignore[attr-defined]
            page.metadata.score = i * 0.5  # type: ignore[attr-defined]
            page.metadata.nested = {"level": i, "type": "test"}  # type: ignore[attr-defined]
            pages.append(page)

        response = PaginatedResponse(results=pages, next_cursor="complex_cursor")
        # Verify complex metadata is preserved
        assert response[0].metadata.tags == ["tag_0", "category_0"]  # type: ignore[attr-defined]
        assert response[1].metadata.score == 0.5  # type: ignore[attr-defined]
        assert response[2].metadata.nested["level"] == 2  # type: ignore[attr-defined]


class TestPaginatedResponseSerialization:
    """Test JSON serialization behavior of PaginatedResponse."""

    def test_to_json_dict_with_cursor(self) -> None:
        """Test to_json_dict includes next_cursor when it has a value."""
        pages = [
            TextPage(uri=PageURI.parse("test/TextPage:test@1"), content="Test content")
        ]
        response = PaginatedResponse(
            results=pages,
            next_cursor="cursor_token_123",
        )

        result = response.to_json_dict()

        # Should include next_cursor
        expected_keys = {"results", "next_cursor"}
        assert set(result.keys()) == expected_keys
        assert result["next_cursor"] == "cursor_token_123"
        assert len(result["results"]) == 1

    def test_to_json_dict_without_cursor(self) -> None:
        """Test to_json_dict includes next_cursor as None when no next page."""
        pages = [
            TextPage(uri=PageURI.parse("test/TextPage:test@1"), content="Test content")
        ]
        response = PaginatedResponse(
            results=pages,
            next_cursor=None,
        )

        result = response.to_json_dict()

        # Should include next_cursor as None
        expected_keys = {"results", "next_cursor"}
        assert set(result.keys()) == expected_keys
        assert result["next_cursor"] is None

    def test_to_json_dict_empty_pages(self) -> None:
        """Test to_json_dict works with empty page list."""
        response = PaginatedResponse(
            results=[],
            next_cursor=None,
        )

        result = response.to_json_dict()

        # Should include both fields
        expected_keys = {"results", "next_cursor"}
        assert set(result.keys()) == expected_keys
        assert result["results"] == []
        assert result["next_cursor"] is None

    def test_to_json_dict_empty_pages_with_cursor(self) -> None:
        """Test to_json_dict works with empty page list but with cursor."""
        response = PaginatedResponse(
            results=[],
            next_cursor="empty_cursor",
        )

        result = response.to_json_dict()

        # Should include both fields
        expected_keys = {"results", "next_cursor"}
        assert set(result.keys()) == expected_keys
        assert result["results"] == []
        assert result["next_cursor"] == "empty_cursor"
