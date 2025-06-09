from collections.abc import Sequence

import pytest

from praga_core.types import Document, PageMetadata, PaginatedResponse


class TestDocument:
    """Test the Document dataclass."""

    def test_document_creation(self):
        """Test basic document creation."""
        doc = Document(id="test_id", content="test content")
        assert doc.id == "test_id"
        assert doc.content == "test content"
        assert doc.metadata is None

    def test_document_with_metadata(self):
        """Test document creation with metadata."""
        metadata = {"key": "value", "count": 42}
        doc = Document(id="test_id", content="test content", metadata=metadata)
        assert doc.metadata == metadata


class TestPageMetadata:
    """Test the PageMetadata dataclass."""

    def test_page_metadata_creation(self):
        """Test basic PageMetadata creation."""
        metadata = PageMetadata(page_number=1, has_next_page=True)
        assert metadata.page_number == 1
        assert metadata.has_next_page is True
        assert metadata.total_documents is None
        assert metadata.token_count is None

    def test_page_metadata_with_optional_fields(self):
        """Test PageMetadata creation with optional fields."""
        metadata = PageMetadata(
            page_number=2, has_next_page=False, total_documents=100, token_count=500
        )
        assert metadata.page_number == 2
        assert metadata.has_next_page is False
        assert metadata.total_documents == 100
        assert metadata.token_count == 500


class TestPaginatedResponseSequenceBehavior:
    """Test that PaginatedResponse behaves like a Sequence."""

    @pytest.fixture
    def sample_documents(self):
        """Create sample documents for testing."""
        return [
            Document(id="doc1", content="Content 1", metadata={"index": 1}),
            Document(id="doc2", content="Content 2", metadata={"index": 2}),
            Document(id="doc3", content="Content 3", metadata={"index": 3}),
        ]

    @pytest.fixture
    def paginated_response(self, sample_documents):
        """Create a sample PaginatedResponse for testing."""
        metadata = PageMetadata(page_number=0, has_next_page=True, total_documents=10)
        return PaginatedResponse(documents=sample_documents, metadata=metadata)

    @pytest.fixture
    def empty_paginated_response(self):
        """Create an empty PaginatedResponse for testing."""
        metadata = PageMetadata(page_number=0, has_next_page=False, total_documents=0)
        return PaginatedResponse(documents=[], metadata=metadata)

    def test_implements_sequence_protocol(self, paginated_response):
        """Test that PaginatedResponse implements the Sequence protocol."""
        # Check that it's considered a Sequence
        assert isinstance(paginated_response, Sequence)

    def test_len(self, paginated_response, empty_paginated_response):
        """Test __len__ method."""
        assert len(paginated_response) == 3
        assert len(empty_paginated_response) == 0

    def test_getitem_by_index(self, paginated_response, sample_documents):
        """Test __getitem__ method with integer indices."""
        # Test positive indices
        assert paginated_response[0] == sample_documents[0]
        assert paginated_response[1] == sample_documents[1]
        assert paginated_response[2] == sample_documents[2]

        # Test negative indices
        assert paginated_response[-1] == sample_documents[2]
        assert paginated_response[-2] == sample_documents[1]
        assert paginated_response[-3] == sample_documents[0]

    def test_getitem_by_slice(self, paginated_response, sample_documents):
        """Test __getitem__ method with slice objects."""
        # Test basic slicing
        slice_result = paginated_response[1:]
        assert list(slice_result) == sample_documents[1:]

        slice_result = paginated_response[:2]
        assert list(slice_result) == sample_documents[:2]

        slice_result = paginated_response[1:3]
        assert list(slice_result) == sample_documents[1:3]

        # Test step slicing
        slice_result = paginated_response[::2]
        assert list(slice_result) == sample_documents[::2]

    def test_getitem_index_error(self, paginated_response, empty_paginated_response):
        """Test __getitem__ method raises IndexError for invalid indices."""
        with pytest.raises(IndexError):
            paginated_response[10]

        with pytest.raises(IndexError):
            paginated_response[-10]

        with pytest.raises(IndexError):
            empty_paginated_response[0]

    def test_iteration(self, paginated_response, sample_documents):
        """Test __iter__ method."""
        iterated_docs = list(paginated_response)
        assert iterated_docs == sample_documents

        # Test that we can iterate multiple times
        count = 0
        for doc in paginated_response:
            count += 1
        assert count == 3

    def test_empty_iteration(self, empty_paginated_response):
        """Test iteration over empty response."""
        iterated_docs = list(empty_paginated_response)
        assert iterated_docs == []

    def test_bool_conversion(self, paginated_response, empty_paginated_response):
        """Test __bool__ method."""
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

    def test_contains(self, paginated_response, sample_documents):
        """Test __contains__ method."""
        # Test with documents that are in the response
        assert sample_documents[0] in paginated_response
        assert sample_documents[1] in paginated_response
        assert sample_documents[2] in paginated_response

        # Test with document that's not in the response
        other_doc = Document(id="other", content="Other content")
        assert other_doc not in paginated_response

    def test_contains_empty_response(self, empty_paginated_response):
        """Test __contains__ method with empty response."""
        doc = Document(id="test", content="Test content")
        assert doc not in empty_paginated_response

    def test_sequence_like_operations(self, paginated_response, sample_documents):
        """Test various sequence-like operations."""
        # Test slicing behavior (if getitem supports it)
        try:
            _ = paginated_response[1:]
        except TypeError:
            pytest.fail("Slicing should be supported")

        # Test with enumerate
        for i, doc in enumerate(paginated_response):
            assert doc == sample_documents[i]

        # Test with zip
        indices = [0, 1, 2]
        for index, doc in zip(indices, paginated_response):
            assert doc == sample_documents[index]

    def test_count_method_via_sequence(self, paginated_response, sample_documents):
        """Test count method inherited from Sequence ABC."""
        # Since PaginatedResponse doesn't override count, it should use
        # the default implementation from Sequence ABC

        # This should work since PaginatedResponse implements Sequence protocol
        count = sum(1 for doc in paginated_response if doc == sample_documents[0])
        assert count == 1

        # Test counting non-existent document
        other_doc = Document(id="other", content="Other")
        count = sum(1 for doc in paginated_response if doc == other_doc)
        assert count == 0

    def test_index_method_simulation(self, paginated_response, sample_documents):
        """Test index-like functionality (finding position of document)."""

        # Since we implement __iter__ and __getitem__, we can simulate index
        def find_index(response, target_doc):
            for i, doc in enumerate(response):
                if doc == target_doc:
                    return i
            raise ValueError("Document not found")

        assert find_index(paginated_response, sample_documents[0]) == 0
        assert find_index(paginated_response, sample_documents[1]) == 1
        assert find_index(paginated_response, sample_documents[2]) == 2

        other_doc = Document(id="other", content="Other")
        with pytest.raises(ValueError):
            find_index(paginated_response, other_doc)

    def test_reverse_iteration(self, paginated_response, sample_documents):
        """Test reverse iteration."""
        reversed_docs = list(reversed(paginated_response))
        expected = list(reversed(sample_documents))
        assert reversed_docs == expected

    def test_equality_comparison(self, sample_documents):
        """Test equality between PaginatedResponse instances."""
        metadata1 = PageMetadata(page_number=0, has_next_page=True)
        metadata2 = PageMetadata(page_number=0, has_next_page=True)

        response1 = PaginatedResponse(documents=sample_documents, metadata=metadata1)
        response2 = PaginatedResponse(documents=sample_documents, metadata=metadata2)

        # Note: This tests structural equality of the dataclass
        assert response1 == response2

        # Test with different documents
        other_docs = [Document(id="other", content="Other")]
        response3 = PaginatedResponse(documents=other_docs, metadata=metadata1)
        assert response1 != response3


class TestPaginatedResponseEdgeCases:
    """Test edge cases for PaginatedResponse."""

    def test_single_document(self):
        """Test with single document."""
        doc = Document(id="single", content="Single doc")
        metadata = PageMetadata(page_number=0, has_next_page=False)
        response = PaginatedResponse(documents=[doc], metadata=metadata)

        assert len(response) == 1
        assert response[0] == doc
        assert doc in response
        assert bool(response) is True
        assert list(response) == [doc]

    def test_large_response(self):
        """Test with many documents."""
        docs = [Document(id=f"doc_{i}", content=f"Content {i}") for i in range(100)]
        metadata = PageMetadata(page_number=0, has_next_page=True, total_documents=1000)
        response = PaginatedResponse(documents=docs, metadata=metadata)

        assert len(response) == 100
        assert response[0].id == "doc_0"
        assert response[99].id == "doc_99"
        assert response[-1].id == "doc_99"

        # Test iteration doesn't exhaust
        count1 = sum(1 for _ in response)
        count2 = sum(1 for _ in response)
        assert count1 == count2 == 100
