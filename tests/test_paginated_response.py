"""Tests for PaginatedResponse and Document classes.

This module tests the PaginatedResponse implementation and its Sequence protocol
behavior, along with basic Document functionality.
"""

import math
from collections.abc import Sequence
from typing import List

import pytest

from praga_core.tool import PaginatedResponse
from praga_core.types import Document, TextDocument


class SimpleTestDocumentBasics:
    """Test basic Document and TextDocument functionality."""

    def test_text_document_creation(self) -> None:
        """Test basic TextDocument creation and auto-calculated fields."""
        doc = TextDocument(id="test_id", content="test content")

        assert doc.id == "test_id"
        assert doc.content == "test content"
        assert doc.metadata.token_count is not None
        assert doc.metadata.token_count > 0

    def test_text_document_with_custom_metadata(self) -> None:
        """Test TextDocument with additional metadata fields."""
        doc = TextDocument(id="test_id", content="test content")

        # Add custom fields to metadata (thanks to Config.extra = "allow")
        doc.metadata.custom_field = "custom_value"  # type: ignore[attr-defined]
        doc.metadata.count = 42  # type: ignore[attr-defined]

        assert doc.metadata.custom_field == "custom_value"  # type: ignore[attr-defined]
        assert doc.metadata.count == 42  # type: ignore[attr-defined]

    def test_document_token_count_calculation(self) -> None:
        """Test that token count is calculated correctly."""
        doc = TextDocument(id="test_id", content="hello world test")

        # Should be approximately 3 words * 4/3 = 4 tokens
        expected_tokens = math.ceil(3 * 4 / 3)
        assert doc.metadata.token_count == expected_tokens


class TestPaginatedResponseSequenceProtocol:
    """Test that PaginatedResponse behaves like a Sequence."""

    @pytest.fixture
    def sample_documents(self) -> List[Document]:
        """Create sample documents for testing."""
        docs: List[Document] = []
        for i in range(1, 4):
            doc = TextDocument(id=f"doc{i}", content=f"Content {i}")
            doc.metadata.index = i  # type: ignore[attr-defined]
            docs.append(doc)
        return docs

    @pytest.fixture
    def paginated_response(self, sample_documents: List[Document]) -> PaginatedResponse:
        """Create a sample PaginatedResponse for testing."""
        return PaginatedResponse(
            documents=sample_documents,
            page_number=0,
            has_next_page=True,
            total_documents=10,
        )

    @pytest.fixture
    def empty_paginated_response(self) -> PaginatedResponse:
        """Create an empty PaginatedResponse for testing."""
        return PaginatedResponse(
            documents=[], page_number=0, has_next_page=False, total_documents=0
        )

    def test_implements_sequence_protocol(
        self, paginated_response: PaginatedResponse
    ) -> None:
        """Test that PaginatedResponse implements the Sequence protocol."""
        assert isinstance(paginated_response, Sequence)

    def test_length_operations(
        self,
        paginated_response: PaginatedResponse,
        empty_paginated_response: PaginatedResponse,
    ) -> None:
        """Test __len__ method."""
        assert len(paginated_response) == 3
        assert len(empty_paginated_response) == 0

    def test_index_access(
        self, paginated_response: PaginatedResponse, sample_documents: List[Document]
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
        self, paginated_response: PaginatedResponse, sample_documents: List[Document]
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
        paginated_response: PaginatedResponse,
        empty_paginated_response: PaginatedResponse,
    ) -> None:
        """Test __getitem__ method raises IndexError for invalid indices."""
        with pytest.raises(IndexError):
            paginated_response[10]

        with pytest.raises(IndexError):
            paginated_response[-10]

        with pytest.raises(IndexError):
            empty_paginated_response[0]

    def test_iteration_behavior(
        self, paginated_response: PaginatedResponse, sample_documents: List[Document]
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

    def test_empty_iteration(self, empty_paginated_response: PaginatedResponse) -> None:
        """Test iteration over empty response."""
        iterated_docs = list(empty_paginated_response)
        assert iterated_docs == []

    def test_boolean_conversion(
        self,
        paginated_response: PaginatedResponse,
        empty_paginated_response: PaginatedResponse,
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
        self, paginated_response: PaginatedResponse, sample_documents: List[Document]
    ) -> None:
        """Test __contains__ method."""
        # Test with documents that are in the response
        assert sample_documents[0] in paginated_response
        assert sample_documents[1] in paginated_response
        assert sample_documents[2] in paginated_response

        # Test with document that's not in the response
        other_doc = TextDocument(id="other", content="Other content")
        assert other_doc not in paginated_response

    def test_membership_empty_response(
        self, empty_paginated_response: PaginatedResponse
    ) -> None:
        """Test __contains__ method with empty response."""
        doc = TextDocument(id="test", content="Test content")
        assert doc not in empty_paginated_response


class TestPaginatedResponseUtilityMethods:
    """Test utility methods and advanced functionality of PaginatedResponse."""

    def test_equality_comparison(self) -> None:
        """Test equality between PaginatedResponse instances."""
        sample_docs = [TextDocument(id="1", content="Content 1")]

        response1 = PaginatedResponse(
            documents=sample_docs, page_number=0, has_next_page=True, total_documents=5
        )
        response2 = PaginatedResponse(
            documents=sample_docs, page_number=0, has_next_page=True, total_documents=5
        )
        response3 = PaginatedResponse(
            documents=sample_docs, page_number=1, has_next_page=True, total_documents=5
        )

        assert response1 == response2  # Same content
        assert response1 != response3  # Different page number

    def test_sequence_methods_simulation(self) -> None:
        """Test sequence-like methods that can be simulated."""
        docs = [
            TextDocument(id="1", content="First"),
            TextDocument(id="2", content="Second"),
            TextDocument(id="1", content="First"),  # Duplicate for testing
        ]
        response = PaginatedResponse(
            documents=docs, page_number=0, has_next_page=False, total_documents=3
        )

        # Test index-like functionality (finding position of document)
        def find_index(response: PaginatedResponse, target_doc: Document) -> int:
            for i, doc in enumerate(response):
                if doc == target_doc:
                    return i
            raise ValueError("Document not found")

        assert find_index(response, docs[0]) == 0
        assert find_index(response, docs[1]) == 1

        # Test with non-existent document
        other_doc = TextDocument(id="other", content="Other")
        with pytest.raises(ValueError):
            find_index(response, other_doc)


class TestPaginatedResponseEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_single_document_response(self) -> None:
        """Test PaginatedResponse with single document."""
        doc = TextDocument(id="single", content="Single document")
        response = PaginatedResponse(
            documents=[doc], page_number=0, has_next_page=False, total_documents=1
        )

        assert len(response) == 1
        assert response[0] == doc
        assert response[-1] == doc
        assert list(response) == [doc]
        assert bool(response) is True

    def test_large_response_performance(self) -> None:
        """Test PaginatedResponse with many documents."""
        docs = [TextDocument(id=f"doc_{i}", content=f"Content {i}") for i in range(100)]
        response = PaginatedResponse(
            documents=docs, page_number=0, has_next_page=True, total_documents=1000
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
            doc = TextDocument(id=f"complex_{i}", content=f"Complex content {i}")
            doc.metadata.tags = [f"tag_{i}", f"category_{i % 2}"]  # type: ignore[attr-defined]
            doc.metadata.score = i * 0.5  # type: ignore[attr-defined]
            doc.metadata.nested = {"level": i, "type": "test"}  # type: ignore[attr-defined]
            docs.append(doc)

        response = PaginatedResponse(
            documents=docs, page_number=0, has_next_page=False, total_documents=3
        )

        # Verify complex metadata is preserved
        assert response[0].metadata.tags == ["tag_0", "category_0"]  # type: ignore[attr-defined]
        assert response[1].metadata.score == 0.5  # type: ignore[attr-defined]
        assert response[2].metadata.nested["level"] == 2  # type: ignore[attr-defined]
