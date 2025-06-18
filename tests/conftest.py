"""Shared test fixtures and utilities for praga_core tests.

This module contains common test fixtures, helper classes, and utilities
that are used across multiple test files.
"""

from datetime import datetime
from typing import Any, List, Optional

import pytest

from praga_core.agents.toolkit import RetrieverToolkit
from praga_core.types import Page, PageURI, TextPage


class SimpleTestPage(Page):
    """Test page implementation with customizable fields."""

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

    def get_page_by_id(self, page_id: str) -> Optional[Page]:
        """Get page by ID - mock implementation returns None."""
        return None

    @property
    def name(self) -> str:
        """Return the name of the toolkit."""
        return "MockRetrieverToolkit"


# Test data factories
def create_test_pages(
    count: int = 5, query: str = "test", content_prefix: str = "Content"
) -> List[SimpleTestPage]:
    """Create a list of test pages."""
    return [
        SimpleTestPage(
            uri=PageURI.parse(f"test/SimpleTestPage:doc_{i}@1"),
            title=f"page {i} - {query}",
            content=f"{content_prefix} about {query} in page {i}. " * 2,
        )
        for i in range(count)
    ]


def create_text_pages(count: int = 5, query: str = "test") -> List[TextPage]:
    """Create a list of Textpage instances."""
    docs: List[TextPage] = []
    for i in range(count):
        doc = TextPage(
            uri=PageURI.parse(f"test/TextPage:text_doc_{i}@1"),
            content=f"Text content about {query} - page {i}",
        )
        # Add custom metadata for testing
        doc.metadata.index = i  # type: ignore[attr-defined]
        doc.metadata.query = query  # type: ignore[attr-defined]
        docs.append(doc)
    return docs


# Shared fixtures
@pytest.fixture
def sample_pages() -> List[SimpleTestPage]:
    """Provide sample test pages."""
    return create_test_pages(10, "sample")


@pytest.fixture
def text_pages() -> List[TextPage]:
    """Provide sample Textpage instances."""
    return create_text_pages(5, "text_sample")


@pytest.fixture
def mock_toolkit() -> MockRetrieverToolkit:
    """Provide a fresh MockRetrieverToolkit for each test."""
    return MockRetrieverToolkit()


@pytest.fixture
def large_page_set() -> List[SimpleTestPage]:
    """Provide a large set of test pages for pagination testing."""
    return create_test_pages(50, "large_set")


@pytest.fixture
def empty_page_list() -> List[SimpleTestPage]:
    """Provide an empty page list for edge case testing."""
    return []


# Test helper functions
def create_timestamped_page(content: str = "test") -> List[TextPage]:
    """Create a page with timestamp for cache testing."""
    return [
        TextPage(
            uri=PageURI.parse("test/TextPage:timestamp_doc@1"),
            content=f"{content} at {datetime.now().isoformat()}",
        )
    ]


def create_failing_function(error_type: str = "runtime") -> Any:
    """Create a function that raises specific errors for testing."""

    def failing_func(query: str) -> List[SimpleTestPage]:
        if error_type == "no_results" or query == "no_results":
            raise ValueError("No matching pages found")
        elif error_type == "runtime":
            raise RuntimeError("Something went wrong")
        else:
            raise Exception("Generic error")

    return failing_func


# Test data constants
SAMPLE_QUERIES = ["python", "javascript", "machine learning", "AI", "test"]
SAMPLE_LIMITS = [1, 3, 5, 10, 20]
SAMPLE_PAGE_SIZES = [2, 3, 5, 10]
