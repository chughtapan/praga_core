"""Tests for the ServerContext class.

This module contains comprehensive tests for the ServerContext class functionality,
including page handler registration, caching, search operations, and error handling.
"""

from typing import Any, List, Optional

import pytest

from praga_core.context import ServerContext
from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference


class DocumentPage(Page):
    """Test page implementation for testing."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


class AlternateTestPage(Page):
    """Another test page type for testing multiple handlers."""

    name: str
    data: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.name) + len(self.data)) // 4


class MockRetrieverAgent(RetrieverAgentBase):
    """Mock retriever agent for testing."""

    def __init__(self, search_results: Optional[List[PageReference]] = None):
        self.search_results = search_results or []
        self.search_calls: List[str] = []

    def search(self, instruction: str) -> List[PageReference]:
        """Mock search implementation."""
        self.search_calls.append(instruction)
        return self.search_results


# Test fixtures
@pytest.fixture
def context() -> ServerContext:
    """Provide a fresh ServerContext for each test."""
    return ServerContext()


@pytest.fixture
def mock_retriever() -> MockRetrieverAgent:
    """Provide a mock retriever agent."""
    return MockRetrieverAgent()


@pytest.fixture
def sample_page_references() -> List[PageReference]:
    """Provide sample page references for testing."""
    return [
        PageReference(id="page1", type="DocumentPage"),
        PageReference(id="page2", type="DocumentPage"),
        PageReference(id="page3", type="AlternateTestPage"),
    ]


# Handler functions for testing
def document_page_handler(page_id: str) -> DocumentPage:
    """Test handler for DocumentPage."""
    return DocumentPage(
        id=page_id,
        title=f"Test Page {page_id}",
        content=f"Content for page {page_id}",
    )


def alternate_page_handler(page_id: str) -> AlternateTestPage:
    """Test handler for AlternateTestPage."""
    return AlternateTestPage(
        id=page_id,
        name=f"Alternate Page {page_id}",
        data=f"Data for page {page_id}",
    )


class TestPageURI:
    """Test page URI generation functionality."""

    def test_get_page_uri_with_page_reference(self, context: ServerContext) -> None:
        """Test URI generation from PageReference."""
        ref = PageReference(id="test_id", type="DocumentPage")
        uri = context.get_page_uri(ref)
        assert uri == "DocumentPage:test_id"

    def test_get_page_uri_with_id_and_type_class(self, context: ServerContext) -> None:
        """Test URI generation from page ID and type class."""
        context.register_handler(document_page_handler, DocumentPage)
        uri = context.get_page_uri("test_id", DocumentPage)
        assert uri == "DocumentPage:test_id"

    def test_get_page_uri_with_id_and_type_string(self, context: ServerContext) -> None:
        """Test URI generation from page ID and type string."""
        context.register_handler(document_page_handler, DocumentPage)
        uri = context.get_page_uri("test_id", "DocumentPage")
        assert uri == "DocumentPage:test_id"

    def test_get_page_uri_special_characters(self, context: ServerContext) -> None:
        """Test URI generation with special characters."""
        ref = PageReference(id="test:id", type="Test:Page")
        uri = context.get_page_uri(ref)
        assert uri == "Test:Page:test:id"


class TestTypeResolution:
    """Test type resolution helper methods."""

    def test_resolve_page_type_from_string(self, context: ServerContext) -> None:
        """Test resolving page type from string."""
        context.register_handler(document_page_handler, DocumentPage)

        resolved_type = context._resolve_page_type("DocumentPage")
        assert resolved_type == DocumentPage

    def test_resolve_page_type_from_class(self, context: ServerContext) -> None:
        """Test resolving page type from class."""
        resolved_type = context._resolve_page_type(DocumentPage)
        assert resolved_type == DocumentPage

    def test_resolve_page_type_unregistered_error(self, context: ServerContext) -> None:
        """Test error when resolving unregistered page type."""
        with pytest.raises(
            RuntimeError, match="No page handler registered for type: UnknownPage"
        ):
            context._resolve_page_type("UnknownPage")


class TestServerContextInitialization:
    """Test ServerContext initialization."""

    def test_initialization(self, context: ServerContext) -> None:
        """Test ServerContext initialization."""
        assert context.retriever is None
        assert context._page_handlers == {}
        assert context._page_cache == {}


class TestPageHandlerRegistration:
    """Test page handler registration functionality."""

    def test_register_handler_programmatically(self, context: ServerContext) -> None:
        """Test programmatic handler registration."""
        context.register_handler(document_page_handler, DocumentPage)

        assert DocumentPage in context._page_handlers
        assert context._page_handlers[DocumentPage] == document_page_handler

    def test_register_handler_with_decorator(self, context: ServerContext) -> None:
        """Test handler registration using decorator."""

        @context.handler(DocumentPage)
        def handler(page_id: str) -> DocumentPage:
            return DocumentPage(
                id=page_id,
                title="Decorated Handler",
                content="Created by decorator",
            )

        assert DocumentPage in context._page_handlers
        assert context._page_handlers[DocumentPage] == handler

    def test_register_multiple_handlers(self, context: ServerContext) -> None:
        """Test registering handlers for multiple page types."""
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        assert len(context._page_handlers) == 2
        assert DocumentPage in context._page_handlers
        assert AlternateTestPage in context._page_handlers

    def test_register_handler_duplicate_error(self, context: ServerContext) -> None:
        """Test error when registering duplicate handler."""
        context.register_handler(document_page_handler, DocumentPage)

        with pytest.raises(RuntimeError, match="already registered"):
            context.register_handler(document_page_handler, DocumentPage)

    def test_register_handler_invalid_type_error(self, context: ServerContext) -> None:
        """Test error when registering handler for non-Page type."""

        def invalid_handler(page_id: str) -> str:
            return "not a page"

        with pytest.raises(RuntimeError, match="not a subclass of Page"):
            context.register_handler(invalid_handler, str)  # type: ignore


class TestPageCreation:
    """Test page creation functionality."""

    def test_create_page_success(self, context: ServerContext) -> None:
        """Test successful page creation."""
        context.register_handler(document_page_handler, DocumentPage)

        page = context._create_page("test123", DocumentPage)

        assert isinstance(page, DocumentPage)
        assert page.id == "test123"
        assert page.title == "Test Page test123"
        assert page.content == "Content for page test123"

    def test_create_page_no_handler_error(self, context: ServerContext) -> None:
        """Test error when no handler is registered."""

        with pytest.raises(RuntimeError, match="No page handler registered"):
            context._create_page("test123", DocumentPage)


class TestPageCaching:
    """Test page caching functionality."""

    def test_cache_set_and_get_page(self, context: ServerContext) -> None:
        """Test setting and getting pages from cache using URIs."""
        context.register_handler(document_page_handler, DocumentPage)
        page = DocumentPage(
            id="cache_test", title="Cached Page", content="Cached content"
        )

        # Cache the page
        context._cache_set_page(page)

        # Retrieve from cache using URI
        uri = context.get_page_uri("cache_test", "DocumentPage")
        cached_page = context._cache_get_page(uri)

        assert cached_page is page
        assert cached_page.id == "cache_test"

    def test_cache_get_page_not_found(self, context: ServerContext) -> None:
        """Test getting non-existent page from cache."""
        context.register_handler(document_page_handler, DocumentPage)
        uri = context.get_page_uri("nonexistent", "DocumentPage")
        result = context._cache_get_page(uri)
        assert result is None

    def test_cache_different_page_types(self, context: ServerContext) -> None:
        """Test caching pages of different types using URIs."""
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        test_page = DocumentPage(id="same_id", title="Test", content="Test content")
        alt_page = AlternateTestPage(id="same_id", name="Alt", data="Alt data")

        context._cache_set_page(test_page)
        context._cache_set_page(alt_page)

        # Should be able to retrieve both using same ID but different types
        test_uri = context.get_page_uri("same_id", "DocumentPage")
        alt_uri = context.get_page_uri("same_id", "AlternateTestPage")

        cached_test = context._cache_get_page(test_uri)
        cached_alt = context._cache_get_page(alt_uri)

        assert cached_test is test_page
        assert cached_alt is alt_page

    def test_cache_uri_consistency(self, context: ServerContext) -> None:
        """Test that caching and retrieval use consistent URIs."""
        context.register_handler(document_page_handler, DocumentPage)
        page = DocumentPage(id="test_id", title="Test", content="Test content")

        # Cache the page (should use URI internally)
        context._cache_set_page(page)

        # Generate URI manually and retrieve
        uri = context.get_page_uri("test_id", DocumentPage)
        cached_page = context._cache_get_page(uri)

        assert cached_page is page


class TestGetPage:
    """Test the get_page functionality with URIs."""

    def test_get_page_from_cache(self, context: ServerContext) -> None:
        """Test getting page from cache when available."""
        context.register_handler(document_page_handler, DocumentPage)

        # Pre-populate cache
        page = DocumentPage(id="cached", title="Cached", content="From cache")
        context._cache_set_page(page)

        # Get page using URI - should come from cache
        uri = context.get_page_uri("cached", DocumentPage)
        result = context.get_page(uri)

        assert result is page

    def test_get_page_create_and_cache(self, context: ServerContext) -> None:
        """Test getting page creates new one and caches it."""
        context.register_handler(document_page_handler, DocumentPage)

        # Get page using URI - should create new one
        uri = context.get_page_uri("new_page", DocumentPage)
        result = context.get_page(uri)

        assert isinstance(result, DocumentPage)
        assert result.id == "new_page"

        # Should now be in cache
        cached = context._cache_get_page(uri)
        assert cached is result

    def test_get_page_with_uri_from_reference(self, context: ServerContext) -> None:
        """Test getting page with URI generated from PageReference."""
        context.register_handler(document_page_handler, DocumentPage)

        ref = PageReference(id="ref_test", type="DocumentPage")
        uri = context.get_page_uri(ref)
        result = context.get_page(uri)

        assert isinstance(result, DocumentPage)
        assert result.id == "ref_test"

    def test_get_page_invalid_uri_error(self, context: ServerContext) -> None:
        """Test error with invalid URI format."""
        with pytest.raises(ValueError):
            context.get_page("invalid_uri_without_colon")

    def test_get_page_unregistered_type_error(self, context: ServerContext) -> None:
        """Test error when page type is not registered."""
        with pytest.raises(RuntimeError, match="No page handler registered"):
            context.get_page("UnknownType:test_id")


class TestRetrieverProperty:
    """Test retriever property functionality."""

    def test_retriever_setter_getter(
        self, context: ServerContext, mock_retriever: MockRetrieverAgent
    ) -> None:
        """Test setting and getting retriever."""
        context.retriever = mock_retriever
        assert context.retriever is mock_retriever

    def test_retriever_set_twice_error(self, context: ServerContext) -> None:
        """Test error when setting retriever twice."""
        context.retriever = MockRetrieverAgent()

        with pytest.raises(RuntimeError, match="already set"):
            context.retriever = MockRetrieverAgent()


class TestSearch:
    """Test search functionality."""

    def test_search_with_context_retriever(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test search using context's retriever."""
        mock_retriever = MockRetrieverAgent(sample_page_references)
        context.retriever = mock_retriever
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        results = context.search("test query")

        assert len(results) == 3
        assert mock_retriever.search_calls == ["test query"]

        # Check that references were resolved
        for ref in results:
            assert ref.page is not None

    def test_search_with_parameter_retriever(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test search using retriever parameter."""
        mock_retriever = MockRetrieverAgent(sample_page_references)
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        results = context.search("test query", retriever=mock_retriever)

        assert len(results) == 3
        assert mock_retriever.search_calls == ["test query"]

    def test_search_no_retriever_error(self, context: ServerContext) -> None:
        """Test error when no retriever is available."""

        with pytest.raises(RuntimeError, match="No RetrieverAgent available"):
            context.search("test query")

    def test_search_without_resolve_references(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test search without resolving references."""
        mock_retriever = MockRetrieverAgent(sample_page_references)
        context.retriever = mock_retriever

        results = context.search("test query", resolve_references=False)

        assert len(results) == 3
        # References should not be resolved
        for ref in results:
            assert ref._page is None

    def test_search_parameter_retriever_overrides_context(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test that parameter retriever overrides context retriever."""
        context_retriever = MockRetrieverAgent([])
        param_retriever = MockRetrieverAgent(sample_page_references)

        context.retriever = context_retriever
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        results = context.search("test query", retriever=param_retriever)

        # Should use parameter retriever, not context retriever
        assert len(results) == 3
        assert param_retriever.search_calls == ["test query"]
        assert context_retriever.search_calls == []


class TestReferenceResolution:
    """Test reference resolution functionality."""

    def test_resolve_references(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test resolving page references."""
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        resolved = context._resolve_references(sample_page_references)

        assert len(resolved) == 3
        for ref in resolved:
            assert ref.page is not None
            assert ref.page.id == ref.id

    def test_resolve_references_caches_pages(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test that resolving references caches the created pages."""
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        context._resolve_references(sample_page_references)

        # Pages should now be cached
        for ref in sample_page_references:
            uri = context.get_page_uri(ref)
            cached_page = context._cache_get_page(uri)
            assert cached_page is not None
            assert cached_page.id == ref.id


class TestIntegration:
    """Integration tests for ServerContext."""

    def test_full_workflow_with_decorator(self, context: ServerContext) -> None:
        """Test complete workflow using decorator pattern."""

        @context.handler(DocumentPage)
        def handle_test_page(page_id: str) -> DocumentPage:
            return DocumentPage(
                id=page_id,
                title=f"Integration Test {page_id}",
                content=f"Full workflow content for {page_id}",
            )

        # Create references
        references = [
            PageReference(id="int1", type="DocumentPage"),
            PageReference(id="int2", type="DocumentPage"),
        ]

        # Set up retriever
        mock_retriever = MockRetrieverAgent(references)
        context.retriever = mock_retriever

        # Perform search
        results = context.search("integration test")

        # Verify results
        assert len(results) == 2
        assert all(ref.page is not None for ref in results)
        assert results[0].page.title == "Integration Test int1"
        assert results[1].page.title == "Integration Test int2"

        # Verify caching worked - second call should use cache
        results2 = context.search("integration test")
        assert results2[0].page is results[0].page  # Same object from cache

    def test_mixed_page_types_workflow(self, context: ServerContext) -> None:
        """Test workflow with mixed page types."""
        context.register_handler(document_page_handler, DocumentPage)
        context.register_handler(alternate_page_handler, AlternateTestPage)

        references = [
            PageReference(id="mixed1", type="DocumentPage"),
            PageReference(id="mixed2", type="AlternateTestPage"),
            PageReference(id="mixed3", type="DocumentPage"),
        ]

        mock_retriever = MockRetrieverAgent(references)
        results = context.search("mixed types", retriever=mock_retriever)

        assert len(results) == 3
        assert isinstance(results[0].page, DocumentPage)
        assert isinstance(results[1].page, AlternateTestPage)
        assert isinstance(results[2].page, DocumentPage)
