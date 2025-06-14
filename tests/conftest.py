"""Shared test fixtures and utilities for praga_core tests.

This module contains common test fixtures, helper classes, and utilities
that are used across multiple test files.
"""

from datetime import datetime
from typing import Any, List, Optional

import pytest

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.types import Document, TextDocument


class SimpleTestDocument(Document):
    """Test document implementation with customizable fields."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Auto-calculate token count based on content length
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


class MockRetrieverToolkit(RetrieverToolkit):
    """Mock RetrieverToolkit for testing purposes."""

    def __init__(self) -> None:
        super().__init__()
        self.call_count: int = 0
        self.cache_key_calls: List[str] = []

    def reset_counters(self) -> None:
        """Reset test counters."""
        self.call_count = 0
        self.cache_key_calls = []

    def increment_call_count(self) -> None:
        """Increment the call counter."""
        self.call_count += 1

    def get_document_by_id(self, document_id: str) -> Optional[Document]:
        """Get document by ID - mock implementation returns None."""
        return None


# Test data factories
def create_test_documents(
    count: int = 5, query: str = "test", content_prefix: str = "Content"
) -> List[SimpleTestDocument]:
    """Create a list of test documents."""
    return [
        SimpleTestDocument(
            id=f"doc_{i}",
            title=f"Document {i} - {query}",
            content=f"{content_prefix} about {query} in document {i}. " * 2,
        )
        for i in range(count)
    ]


def create_text_documents(count: int = 5, query: str = "test") -> List[TextDocument]:
    """Create a list of TextDocument instances."""
    docs: List[TextDocument] = []
    for i in range(count):
        doc = TextDocument(
            id=f"text_doc_{i}", content=f"Text content about {query} - document {i}"
        )
        # Add custom metadata for testing
        doc.metadata.index = i  # type: ignore[attr-defined]
        doc.metadata.query = query  # type: ignore[attr-defined]
        docs.append(doc)
    return docs


# Shared fixtures
@pytest.fixture
def sample_documents() -> List[SimpleTestDocument]:
    """Provide sample test documents."""
    return create_test_documents(10, "sample")


@pytest.fixture
def text_documents() -> List[TextDocument]:
    """Provide sample TextDocument instances."""
    return create_text_documents(5, "text_sample")


@pytest.fixture
def mock_toolkit() -> MockRetrieverToolkit:
    """Provide a fresh MockRetrieverToolkit for each test."""
    return MockRetrieverToolkit()


@pytest.fixture
def large_document_set() -> List[SimpleTestDocument]:
    """Provide a large set of test documents for pagination testing."""
    return create_test_documents(50, "large_set")


@pytest.fixture
def empty_document_list() -> List[SimpleTestDocument]:
    """Provide an empty document list for edge case testing."""
    return []


# Test helper functions
def create_timestamped_document(content: str = "test") -> List[TextDocument]:
    """Create a document with timestamp for cache testing."""
    return [
        TextDocument(
            id="timestamp_doc", content=f"{content} at {datetime.now().isoformat()}"
        )
    ]


def create_failing_function(error_type: str = "runtime"):
    """Create a function that raises specific errors for testing."""

    def failing_func(query: str) -> List[SimpleTestDocument]:
        if error_type == "no_results" or query == "no_results":
            raise ValueError("No matching documents found")
        elif error_type == "runtime":
            raise RuntimeError("Something went wrong")
        else:
            raise Exception("Generic error")

    return failing_func


def assert_valid_pagination_response(result: dict) -> None:
    """Assert that a result has valid pagination structure."""
    required_fields = {"documents", "page_number", "has_next_page", "total_documents"}
    assert all(field in result for field in required_fields)

    assert isinstance(result["documents"], list)
    assert isinstance(result["page_number"], int)
    assert isinstance(result["has_next_page"], bool)
    assert isinstance(result["total_documents"], int)
    assert result["page_number"] >= 0
    assert result["total_documents"] >= 0


def assert_valid_document_structure(document: dict) -> None:
    """Assert that a document has valid structure."""
    required_fields = {"id"}
    assert all(field in document for field in required_fields)

    assert isinstance(document["id"], str)
    assert len(document["id"]) > 0


# Test data constants
SAMPLE_QUERIES = ["python", "javascript", "machine learning", "AI", "test"]
SAMPLE_LIMITS = [1, 3, 5, 10, 20]
SAMPLE_PAGE_SIZES = [2, 3, 5, 10]
