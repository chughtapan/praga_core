"""Tests for the ServerContext class.

This module contains comprehensive tests for the ServerContext class functionality,
including page handler registration, caching, search operations, and error handling.
"""

from typing import Any, List, Optional

import pytest

from praga_core.context import ServerContext
from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse


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
    return ServerContext(root="test")


@pytest.fixture
def mock_retriever() -> MockRetrieverAgent:
    """Provide a mock retriever agent."""
    return MockRetrieverAgent()


@pytest.fixture
def sample_page_references() -> List[PageReference]:
    """Provide sample page references for testing."""
    return [
        PageReference(uri=PageURI(root="test", type="document", id="page1", version=1)),
        PageReference(uri=PageURI(root="test", type="document", id="page2", version=1)),
        PageReference(
            uri=PageURI(root="test", type="alternate", id="page3", version=1)
        ),
    ]


# Handler functions for testing
def document_page_handler(page_id: str) -> DocumentPage:
    """Test handler for DocumentPage."""
    uri = PageURI(root="test", type="document", id=page_id, version=1)
    return DocumentPage(
        uri=uri,
        title=f"Test Page {page_id}",
        content=f"Content for page {page_id}",
    )


def alternate_page_handler(page_id: str) -> AlternateTestPage:
    """Test handler for AlternateTestPage."""
    uri = PageURI(root="test", type="alternate", id=page_id, version=1)
    return AlternateTestPage(
        uri=uri,
        name=f"Alternate Page {page_id}",
        data=f"Data for page {page_id}",
    )


class TestPageURI:
    """Test PageURI functionality."""

    def test_page_uri_creation(self) -> None:
        """Test creating a PageURI."""
        uri = PageURI(root="test", type="Email", id="123", version=1)
        assert uri.root == "test"
        assert uri.type == "Email"
        assert uri.id == "123"
        assert uri.version == 1

    def test_page_uri_creation_default_version(self) -> None:
        """Test creating a PageURI with default version."""
        uri = PageURI(root="test", type="Email", id="123")
        assert uri.version == 1

    def test_page_uri_string_representation(self) -> None:
        """Test PageURI string representation."""
        uri = PageURI(root="myserver", type="Document", id="abc", version=2)
        assert str(uri) == "myserver/Document:abc@2"

    def test_page_uri_parsing(self) -> None:
        """Test parsing URI from string."""
        uri_str = "server/Email:msg123@5"
        uri = PageURI.parse(uri_str)
        assert uri.root == "server"
        assert uri.type == "Email"
        assert uri.id == "msg123"
        assert uri.version == 5

    def test_page_uri_parsing_with_empty_root(self) -> None:
        """Test parsing URI with empty root."""
        uri_str = "/Email:msg123@1"
        uri = PageURI.parse(uri_str)
        assert uri.root == ""
        assert uri.type == "Email"
        assert uri.id == "msg123"
        assert uri.version == 1

    def test_page_uri_validation_invalid_type(self) -> None:
        """Test validation of type field."""
        with pytest.raises(ValueError, match="Type cannot contain"):
            PageURI(root="test", type="Email:Bad", id="123", version=1)

    def test_page_uri_validation_invalid_id(self) -> None:
        """Test validation of id field."""
        with pytest.raises(ValueError, match="ID cannot contain"):
            PageURI(root="test", type="Email", id="123@bad", version=1)

    def test_page_uri_validation_invalid_version(self) -> None:
        """Test validation of version field."""
        with pytest.raises(ValueError, match="Version must be non-negative"):
            PageURI(root="test", type="Email", id="123", version=-1)

    def test_page_uri_parsing_invalid_format(self) -> None:
        """Test parsing invalid URI format."""
        with pytest.raises(ValueError, match="Invalid URI format"):
            PageURI.parse("invalid-format")

    def test_page_uri_hashable(self) -> None:
        """Test that PageURI is hashable."""
        uri1 = PageURI(root="test", type="Email", id="123", version=1)
        uri2 = PageURI(root="test", type="Email", id="123", version=1)
        uri3 = PageURI(root="test", type="Email", id="124", version=1)

        uri_set = {uri1, uri2, uri3}
        assert len(uri_set) == 2  # uri1 and uri2 should be the same

    def test_page_uri_equality(self) -> None:
        """Test PageURI equality comparison."""
        uri1 = PageURI(root="test", type="Email", id="123", version=1)
        uri2 = PageURI(root="test", type="Email", id="123", version=1)
        uri3 = PageURI(root="test", type="Email", id="124", version=1)

        assert uri1 == uri2
        assert uri1 != uri3
        assert uri1 != "not_a_uri"


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
        context.register_handler("document", document_page_handler)

        assert "document" in context._page_handlers
        assert context._page_handlers["document"] == document_page_handler

    def test_register_multiple_handlers(self, context: ServerContext) -> None:
        """Test registering handlers for multiple page types."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        assert len(context._page_handlers) == 2
        assert "document" in context._page_handlers
        assert "alternate" in context._page_handlers

    def test_register_handler_duplicate_error(self, context: ServerContext) -> None:
        """Test error when registering duplicate handler."""
        context.register_handler("document", document_page_handler)

        with pytest.raises(RuntimeError, match="already registered"):
            context.register_handler("document", document_page_handler)


class TestPageCreation:
    """Test page creation functionality."""

    def test_create_page_success(self, context: ServerContext) -> None:
        """Test successful page creation."""
        context.register_handler("document", document_page_handler)

        uri = PageURI(root="test", type="document", id="123", version=1)
        page = context._create_page(uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page 123"
        assert page.content == "Content for page 123"

    def test_create_page_no_handler_error(self, context: ServerContext) -> None:
        """Test error when creating page with no registered handler."""
        uri = PageURI(root="test", type="nonexistent", id="123", version=1)

        with pytest.raises(RuntimeError, match="No page handler registered"):
            context._create_page(uri)


class TestPageCaching:
    """Test page caching functionality."""

    def test_cache_set_and_get_page(self, context: ServerContext) -> None:
        """Test setting and getting pages from cache."""
        context.register_handler("document", document_page_handler)

        uri = PageURI(root="test", type="document", id="cached_page", version=1)
        page = DocumentPage(
            uri=uri,
            title="Cached Page",
            content="This page was cached",
        )

        context._cache_set_page(page)
        cached_page = context._cache_get_page(uri)

        assert cached_page is not None
        assert cached_page.title == "Cached Page"
        assert cached_page.content == "This page was cached"

    def test_cache_get_page_not_found(self, context: ServerContext) -> None:
        """Test getting page from cache when not found."""
        uri = PageURI(root="test", type="document", id="not_found", version=1)
        cached_page = context._cache_get_page(uri)

        assert cached_page is None

    def test_cache_different_page_types(self, context: ServerContext) -> None:
        """Test caching different page types."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        doc_uri = PageURI(root="test", type="document", id="doc1", version=1)
        alt_uri = PageURI(root="test", type="alternate", id="alt1", version=1)

        doc_page = DocumentPage(uri=doc_uri, title="Doc", content="Content")
        alt_page = AlternateTestPage(uri=alt_uri, name="Alt", data="Data")

        context._cache_set_page(doc_page)
        context._cache_set_page(alt_page)

        cached_doc = context._cache_get_page(doc_uri)
        cached_alt = context._cache_get_page(alt_uri)

        assert isinstance(cached_doc, DocumentPage)
        assert isinstance(cached_alt, AlternateTestPage)
        assert cached_doc.title == "Doc"
        assert cached_alt.name == "Alt"

    def test_cache_uri_consistency(self, context: ServerContext) -> None:
        """Test cache consistency with string and PageURI access."""
        uri = PageURI(root="test", type="document", id="consistent", version=1)
        uri_str = str(uri)
        page = DocumentPage(uri=uri, title="Consistent", content="Content")

        context._cache_set_page(page)

        cached_by_uri = context._cache_get_page(uri)
        cached_by_str = context._cache_get_page(uri_str)

        assert cached_by_uri is cached_by_str
        assert cached_by_uri.title == "Consistent"


class TestGetPage:
    """Test get_page functionality."""

    def test_get_page_from_cache(self, context: ServerContext) -> None:
        """Test getting page from cache when available."""
        context.register_handler("document", document_page_handler)

        uri = PageURI(root="test", type="document", id="cached", version=1)
        original_page = DocumentPage(uri=uri, title="Original", content="Content")
        context._cache_set_page(original_page)

        retrieved_page = context.get_page(uri)

        assert retrieved_page is original_page
        assert retrieved_page.title == "Original"

    def test_get_page_create_and_cache(self, context: ServerContext) -> None:
        """Test creating and caching page when not in cache."""
        context.register_handler("document", document_page_handler)

        uri = PageURI(root="test", type="document", id="new_page", version=1)
        page = context.get_page(uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page new_page"

        # Verify it was cached
        cached_page = context._cache_get_page(uri)
        assert cached_page is page

    def test_get_page_with_uri_from_reference(self, context: ServerContext) -> None:
        """Test getting page using URI from PageReference."""
        context.register_handler("document", document_page_handler)

        reference = PageReference(
            uri=PageURI(root="test", type="document", id="ref_page", version=1)
        )
        page = context.get_page(reference.uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page ref_page"

    def test_get_page_invalid_uri_error(self, context: ServerContext) -> None:
        """Test error when getting page with invalid URI string."""
        with pytest.raises(ValueError):
            context.get_page("invalid-uri-format")

    def test_get_page_unregistered_type_error(self, context: ServerContext) -> None:
        """Test error when getting page for unregistered type."""
        uri = PageURI(root="test", type="unregistered", id="123", version=1)
        with pytest.raises(RuntimeError, match="No page handler registered"):
            context.get_page(uri)


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
        mock1 = MockRetrieverAgent()
        mock2 = MockRetrieverAgent()

        context.retriever = mock1
        with pytest.raises(RuntimeError, match="already set"):
            context.retriever = mock2


class TestSearch:
    """Test search functionality."""

    def test_search_with_context_retriever(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test search using context's retriever."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        mock_retriever = MockRetrieverAgent(sample_page_references)
        context.retriever = mock_retriever

        result = context.search("test query")

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        assert mock_retriever.search_calls == ["test query"]

        # Verify pages were resolved
        for ref in result.results:
            assert ref._page is not None

    def test_search_with_parameter_retriever(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test search using retriever parameter."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        mock_retriever = MockRetrieverAgent(sample_page_references)
        result = context.search("test query", retriever=mock_retriever)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
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

        result = context.search("test query", resolve_references=False)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        # Verify pages were NOT resolved
        for ref in result.results:
            assert ref._page is None

    def test_search_parameter_retriever_overrides_context(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test that parameter retriever overrides context retriever."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        context_retriever = MockRetrieverAgent([])
        param_retriever = MockRetrieverAgent(sample_page_references)

        context.retriever = context_retriever

        result = context.search("test query", retriever=param_retriever)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        assert context_retriever.search_calls == []
        assert param_retriever.search_calls == ["test query"]


class TestReferenceResolution:
    """Test reference resolution functionality."""

    def test_resolve_references(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test resolving page references."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        resolved_refs = context._resolve_references(sample_page_references)

        assert len(resolved_refs) == 3
        for ref in resolved_refs:
            assert ref._page is not None

    def test_resolve_references_caches_pages(
        self, context: ServerContext, sample_page_references: List[PageReference]
    ) -> None:
        """Test that resolving references caches the pages."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        context._resolve_references(sample_page_references)

        # Verify pages were cached
        for ref in sample_page_references:
            cached_page = context._cache_get_page(ref.uri)
            assert cached_page is not None


class TestIntegration:
    """Test integration scenarios."""

    def test_full_workflow_with_decorator(self, context: ServerContext) -> None:
        """Test full workflow using decorator registration."""

        def handle_test_page(page_id: str) -> DocumentPage:
            uri = PageURI(root="test", type="testdoc", id=page_id, version=1)
            return DocumentPage(
                uri=uri,
                title=f"Decorated Page {page_id}",
                content=f"Content for {page_id}",
            )

        # Register handler
        context.register_handler("testdoc", handle_test_page)

        # Create test data
        test_refs = [
            PageReference(
                uri=PageURI(root="test", type="testdoc", id="test1", version=1)
            ),
            PageReference(
                uri=PageURI(root="test", type="testdoc", id="test2", version=1)
            ),
        ]

        # Set up retriever and search
        mock_retriever = MockRetrieverAgent(test_refs)
        context.retriever = mock_retriever

        result = context.search("find test pages")

        # Verify results
        assert isinstance(result, SearchResponse)
        assert len(result.results) == 2
        assert all(isinstance(ref.page, DocumentPage) for ref in result.results)
        assert result.results[0].page.title == "Decorated Page test1"
        assert result.results[1].page.title == "Decorated Page test2"

    def test_mixed_page_types_workflow(self, context: ServerContext) -> None:
        """Test workflow with mixed page types."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        mixed_refs = [
            PageReference(
                uri=PageURI(root="test", type="document", id="doc1", version=1)
            ),
            PageReference(
                uri=PageURI(root="test", type="alternate", id="alt1", version=1)
            ),
            PageReference(
                uri=PageURI(root="test", type="document", id="doc2", version=1)
            ),
        ]

        mock_retriever = MockRetrieverAgent(mixed_refs)
        result = context.search("mixed search", retriever=mock_retriever)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        assert isinstance(result.results[0].page, DocumentPage)
        assert isinstance(result.results[1].page, AlternateTestPage)
        assert isinstance(result.results[2].page, DocumentPage)
