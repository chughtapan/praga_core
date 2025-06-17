"""Tests for PaginatedResponse and Document classes.

This module tests the PaginatedResponse implementation and its Sequence protocol
behavior, along with basic Document functionality.
"""

import math
from collections.abc import Sequence
from typing import List

import pytest

from praga_core import Page, TextPage
from praga_core.agents import PaginatedResponse


class SimpleTestDocumentBasics:
    """Test basic Document and TextDocument functionality."""

    def test_text_document_creation(self) -> None:
        """Test basic TextDocument creation and auto-calculated fields."""
        doc = TextPage(id="test_id", content="test content")

        assert doc.id == "test_id"
        assert doc.content == "test content"
        assert doc.metadata.token_count is not None
        assert doc.metadata.token_count > 0

    def test_text_document_with_custom_metadata(self) -> None:
        """Test TextDocument with additional metadata fields."""
        doc = TextPage(id="test_id", content="test content")

        # Add custom fields to metadata (thanks to Config.extra = "allow")
        doc.metadata.custom_field = "custom_value"  # type: ignore[attr-defined]
        doc.metadata.count = 42  # type: ignore[attr-defined]

        assert doc.metadata.custom_field == "custom_value"  # type: ignore[attr-defined]
        assert doc.metadata.count == 42  # type: ignore[attr-defined]

    def test_document_token_count_calculation(self) -> None:
        """Test that token count is calculated correctly."""
        doc = TextPage(id="test_id", content="hello world test")

        # Should be approximately 3 words * 4/3 = 4 tokens
        expected_tokens = math.ceil(3 * 4 / 3)
        assert doc.metadata.token_count == expected_tokens


class TestPaginatedResponseSequenceProtocol:
    """Test that PaginatedResponse behaves like a Sequence."""

    @pytest.fixture
    def sample_documents(self) -> List[TextPage]:
        """Create sample documents for testing."""
        docs: List[TextPage] = []
        for i in range(1, 4):
            doc = TextPage(id=f"doc{i}", content=f"Content {i}")
            doc.metadata.index = i  # type: ignore[attr-defined]
            docs.append(doc)
        return docs

    @pytest.fixture
    def paginated_response(
        self, sample_documents: List[TextPage]
    ) -> PaginatedResponse[TextPage]:
        """Create a sample PaginatedResponse for testing."""
        return PaginatedResponse(
            results=sample_documents,
            page_number=0,
            has_next_page=True,
            total_results=10,
        )

    @pytest.fixture
    def empty_paginated_response(self) -> PaginatedResponse[TextPage]:
        """Create an empty PaginatedResponse for testing."""
        return PaginatedResponse(
            results=[], page_number=0, has_next_page=False, total_results=0
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
        sample_documents: List[TextPage],
    ) -> None:
        """Test __getitem__ method with integer indices."""
        # Test positive indices
        assert paginated_response[0] == sample_documents[0]
        assert paginated_response[1] == sample_documents[1]
        assert paginated_response[2] == sample_documents[2]

        # Test negative indices
        assert paginated_response[-1] == sample_documents[2]
        assert paginated_response[-2] == sample_documents[1]
        assert paginated_response[-3] == sample_documents[0]

    def test_slice_access(
        self,
        paginated_response: PaginatedResponse[TextPage],
        sample_documents: List[TextPage],
    ) -> None:
        """Test __getitem__ method with slice objects."""
        # Test basic slicing
        assert list(paginated_response[1:]) == sample_documents[1:]
        assert list(paginated_response[:2]) == sample_documents[:2]
        assert list(paginated_response[1:3]) == sample_documents[1:3]

        # Test step slicing
        assert list(paginated_response[::2]) == sample_documents[::2]

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
        sample_documents: List[TextPage],
    ) -> None:
        """Test __iter__ method and iteration patterns."""
        # Test basic iteration
        iterated_docs = list(paginated_response)
        assert iterated_docs == sample_documents

        # Test that we can iterate multiple times
        count = 0
        for _ in paginated_response:
            count += 1
        assert count == 3

        # Test reverse iteration
        reversed_docs = list(reversed(paginated_response))
        expected = list(reversed(sample_documents))
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
        sample_documents: List[TextPage],
    ) -> None:
        """Test __contains__ method."""
        # Test with documents that are in the response
        assert sample_documents[0] in paginated_response
        assert sample_documents[1] in paginated_response
        assert sample_documents[2] in paginated_response

        # Test with document that's not in the response
        other_doc = TextPage(id="other", content="Other content")
        assert other_doc not in paginated_response

    def test_membership_empty_response(
        self, empty_paginated_response: PaginatedResponse[TextPage]
    ) -> None:
        """Test __contains__ method with empty response."""
        doc = TextPage(id="test", content="Test content")
        assert doc not in empty_paginated_response


class TestPaginatedResponseUtilityMethods:
    """Test utility methods and advanced functionality of PaginatedResponse."""

    def test_equality_comparison(self) -> None:
        """Test equality between PaginatedResponse instances."""
        sample_docs = [TextPage(id="1", content="Content 1")]

        response1 = PaginatedResponse(
            results=sample_docs, page_number=0, has_next_page=True, total_results=5
        )
        response2 = PaginatedResponse(
            results=sample_docs, page_number=0, has_next_page=True, total_results=5
        )
        response3 = PaginatedResponse(
            results=sample_docs, page_number=1, has_next_page=True, total_results=5
        )

        assert response1 == response2  # Same content
        assert response1 != response3  # Different page number

    def test_sequence_methods_simulation(self) -> None:
        """Test sequence-like methods that can be simulated."""
        docs = [
            TextPage(id="1", content="First"),
            TextPage(id="2", content="Second"),
            TextPage(id="1", content="First"),  # Duplicate for testing
        ]
        response = PaginatedResponse(
            results=docs, page_number=0, has_next_page=False, total_results=3
        )

        # Test index-like functionality (finding position of document)
        def find_index(
            response: PaginatedResponse[TextPage], target_doc: TextPage
        ) -> int:
            for i, doc in enumerate(response):
                if doc == target_doc:
                    return i
            raise ValueError("Document not found")

        assert find_index(response, docs[0]) == 0
        assert find_index(response, docs[1]) == 1

        # Test with non-existent document
        other_doc = TextPage(id="other", content="Other")
        with pytest.raises(ValueError):
            find_index(response, other_doc)


class TestPaginatedResponseEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_document_response(self) -> None:
        """Test PaginatedResponse with single document."""
        doc = TextPage(id="single", content="Single document")
        response = PaginatedResponse(
            results=[doc], page_number=0, has_next_page=False, total_results=1
        )

        assert len(response) == 1
        assert response[0] == doc
        assert response[-1] == doc
        assert list(response) == [doc]
        assert bool(response) is True

    def test_large_response_performance(self) -> None:
        """Test PaginatedResponse with many documents."""
        docs = [TextPage(id=f"doc_{i}", content=f"Content {i}") for i in range(100)]
        response = PaginatedResponse(
            results=docs, page_number=0, has_next_page=True, total_results=1000
        )

        # Test that operations are efficient
        assert len(response) == 100
        assert response[50].id == "doc_50"
        assert response[-1].id == "doc_99"

        # Test slicing doesn't cause performance issues
        subset = list(response[25:75])
        assert len(subset) == 50
        assert subset[0].id == "doc_25"

    def test_response_with_complex_documents(self) -> None:
        """Test PaginatedResponse with documents containing complex metadata."""
        docs = []
        for i in range(3):
            doc = TextPage(id=f"complex_{i}", content=f"Complex content {i}")
            doc.metadata.tags = [f"tag_{i}", f"category_{i % 2}"]  # type: ignore[attr-defined]
            doc.metadata.score = i * 0.5  # type: ignore[attr-defined]
            doc.metadata.nested = {"level": i, "type": "test"}  # type: ignore[attr-defined]
            docs.append(doc)

        response = PaginatedResponse(
            results=docs, page_number=0, has_next_page=False, total_results=3
        )
        # Verify complex metadata is preserved
        assert response[0].metadata.tags == ["tag_0", "category_0"]  # type: ignore[attr-defined]
        assert response[1].metadata.score == 0.5  # type: ignore[attr-defined]
        assert response[2].metadata.nested["level"] == 2  # type: ignore[attr-defined]


class TestPaginatedResponseSerialization:
    """Test JSON serialization behavior of PaginatedResponse."""

    def test_to_json_dict_with_all_fields(self) -> None:
        """Test to_json_dict includes all fields when they have values."""
        docs = [TextPage(id="test", content="Test content")]
        response = PaginatedResponse(
            results=docs,
            page_number=0,
            has_next_page=True,
            total_results=10,
            token_count=42,
        )

        result = response.to_json_dict()

        # Should include all fields
        expected_keys = {
            "documents",
            "page_number",
            "has_next_page",
            "total_documents",
            "token_count",
        }
        assert set(result.keys()) == expected_keys
        assert result["page_number"] == 0
        assert result["has_next_page"] is True
        assert result["total_documents"] == 10
        assert result["token_count"] == 42
        assert len(result["documents"]) == 1

    def test_to_json_dict_without_total_documents(self) -> None:
        """Test to_json_dict excludes total_documents when None."""
        docs = [TextPage(id="test", content="Test content")]
        response = PaginatedResponse(
            results=docs,
            page_number=0,
            has_next_page=False,
            total_results=None,  # Explicitly None
            token_count=42,
        )

        result = response.to_json_dict()

        # Should NOT include total_documents
        expected_keys = {"documents", "page_number", "has_next_page", "token_count"}
        assert set(result.keys()) == expected_keys
        assert "total_documents" not in result
        assert result["token_count"] == 42

    def test_to_json_dict_without_token_count(self) -> None:
        """Test to_json_dict excludes token_count when None."""
        docs = [TextPage(id="test", content="Test content")]
        response = PaginatedResponse(
            results=docs,
            page_number=1,
            has_next_page=True,
            total_results=100,
            token_count=None,  # Explicitly None
        )

        result = response.to_json_dict()

        # Should NOT include token_count
        expected_keys = {"documents", "page_number", "has_next_page", "total_documents"}
        assert set(result.keys()) == expected_keys
        assert "token_count" not in result
        assert result["total_documents"] == 100

    def test_to_json_dict_minimal_fields(self) -> None:
        """Test to_json_dict with only required fields."""
        docs = [TextPage(id="test", content="Test content")]
        response = PaginatedResponse(
            results=docs,
            page_number=2,
            has_next_page=False,
            # Both optional fields are None by default
        )

        result = response.to_json_dict()

        # Should only include required fields
        expected_keys = {"documents", "page_number", "has_next_page"}
        assert set(result.keys()) == expected_keys
        assert "total_documents" not in result
        assert "token_count" not in result
        assert result["page_number"] == 2
        assert result["has_next_page"] is False

    def test_to_json_dict_excludes_zero_values(self) -> None:
        """Test to_json_dict excludes zero values for optional fields."""
        docs = [TextPage(id="test", content="Test content")]
        response = PaginatedResponse(
            results=docs,
            page_number=0,
            has_next_page=False,
            total_results=0,  # Zero - should be excluded
            token_count=0,  # Zero - should be excluded
        )

        result = response.to_json_dict()

        # Should NOT include zero values for optional fields
        expected_keys = {"documents", "page_number", "has_next_page"}
        assert set(result.keys()) == expected_keys
        assert "total_documents" not in result
        assert "token_count" not in result

    def test_to_json_dict_empty_documents(self) -> None:
        """Test to_json_dict works with empty document list."""
        response: PaginatedResponse[Page] = PaginatedResponse(
            results=[],
            page_number=0,
            has_next_page=False,
            total_results=0,  # Zero - will be excluded
            token_count=0,  # Zero - will be excluded
        )

        result = response.to_json_dict()

        # Should only include core fields since optional fields are zero
        expected_keys = {"documents", "page_number", "has_next_page"}
        assert set(result.keys()) == expected_keys
        assert result["documents"] == []
        assert "total_documents" not in result
        assert "token_count" not in result

    def test_to_json_dict_includes_positive_values(self) -> None:
        """Test to_json_dict includes positive values for optional fields."""
        docs = [TextPage(id="test", content="Test content")]
        response = PaginatedResponse(
            results=docs,
            page_number=0,
            has_next_page=True,
            total_results=1,  # Positive - should be included
            token_count=15,  # Positive - should be included
        )

        result = response.to_json_dict()

        # Should include all fields since optional fields have positive values
        expected_keys = {
            "documents",
            "page_number",
            "has_next_page",
            "total_documents",
            "token_count",
        }
        assert set(result.keys()) == expected_keys
        assert result["total_documents"] == 1
        assert result["token_count"] == 15
