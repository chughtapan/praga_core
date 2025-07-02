"""Tests for the ServerContext class.

This module contains comprehensive tests for the ServerContext functionality,
including page creation, caching, retrieval, and search functionality.
"""

from typing import Any, List, Optional

import pytest
from pydantic import Field

from praga_core.context import ServerContext
from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference, PageURI, SearchResponse


class DocumentPage(Page):
    """Test page implementation for testing."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class AlternateTestPage(Page):
    """Another test page type for testing multiple handlers."""

    name: str
    data: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


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
def document_page_handler(page_uri: PageURI) -> DocumentPage:
    """Test handler for DocumentPage."""
    return DocumentPage(
        uri=str(page_uri),
        title=f"Test Page {page_uri.id}",
        content=f"Content for page {page_uri.id}",
    )


def alternate_page_handler(page_uri: PageURI) -> AlternateTestPage:
    """Test handler for AlternateTestPage."""
    return AlternateTestPage(
        uri=page_uri,
        name=f"Alternate Page {page_uri.id}",
        data=f"Data for page {page_uri.id}",
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

    def test_page_uri_creation_none_version_default(self) -> None:
        """Test creating a PageURI with None version (default)."""
        uri = PageURI(root="test", type="Email", id="123")
        assert uri.version is None

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

    def test_page_uri_soft_parsing_without_version(self) -> None:
        """Test soft parsing of URI without version (should default to None)."""
        uri_str = "server/Email:msg123"
        uri = PageURI.parse(uri_str)
        assert uri.root == "server"
        assert uri.type == "Email"
        assert uri.id == "msg123"
        assert uri.version is None

    def test_page_uri_soft_parsing_with_empty_root(self) -> None:
        """Test soft parsing of URI with empty root and no version."""
        uri_str = "/Email:msg123"
        uri = PageURI.parse(uri_str)
        assert uri.root == ""
        assert uri.type == "Email"
        assert uri.id == "msg123"
        assert uri.version is None

    def test_page_uri_parsing_strict_still_works(self) -> None:
        """Test that strict parsing with version still works."""
        uri_str = "server/Email:msg123@5"
        uri = PageURI.parse(uri_str)
        assert uri.root == "server"
        assert uri.type == "Email"
        assert uri.id == "msg123"
        assert uri.version == 5

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


class TestVersionFunctionality:
    """Test version functionality in context."""

    def test_create_page_uri_defaults_to_version_1(
        self, context: ServerContext
    ) -> None:
        """Test that create_page_uri resolves None version to version 1 when no existing versions."""
        # We need to use a real page class for this test
        from praga_core.types import TextPage

        uri = context.create_page_uri(TextPage, "text", "test123")
        assert uri.version == 1

    def test_create_page_uri_explicit_version_overrides_default(
        self, context: ServerContext
    ) -> None:
        """Test that explicit version parameter overrides the default behavior."""
        from praga_core.types import TextPage

        # Explicit version
        uri = context.create_page_uri(TextPage, "text", "test123", version=5)
        assert uri.version == 5

        # Explicit None version (latest)
        uri2 = context.create_page_uri(TextPage, "text", "test123", version=None)
        assert (
            uri2.version == 1
        )  # Should resolve to version 1 when no existing versions


class TestServerContextInitialization:
    """Test ServerContext initialization."""

    def test_initialization(self, context: ServerContext) -> None:
        """Test ServerContext initialization."""
        assert context.retriever is None
        assert context.page_cache is not None


class TestPageHandlerRegistration:
    """Test page handler registration functionality."""

    def test_register_handler_programmatically(self, context: ServerContext) -> None:
        """Test programmatic handler registration."""
        context.register_handler("document", document_page_handler)
        # No error means success - handler is stored internally

    def test_register_multiple_handlers(self, context: ServerContext) -> None:
        """Test registering handlers for multiple page types."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)
        # No error means success

    def test_register_handler_duplicate_error(self, context: ServerContext) -> None:
        """Test error when registering duplicate handler."""
        context.register_handler("document", document_page_handler)
        with pytest.raises(RuntimeError, match="already registered"):
            context.register_handler("document", document_page_handler)


class TestGetPage:
    """Test get_page functionality."""

    def test_get_page_create_new(self, context: ServerContext) -> None:
        """Test creating new page via handler."""
        context.register_handler("document", document_page_handler)

        uri = PageURI(root="test", type="document", id="new_page", version=1)
        page = context.get_page(uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page new_page"

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


class TestIntegration:
    """Test integration scenarios."""

    def test_full_workflow_with_decorator(self, context: ServerContext) -> None:
        """Test full workflow using decorator registration."""

        @context.handler("test")
        def handle_test_page(page_uri: PageURI) -> DocumentPage:
            return document_page_handler(page_uri)

        # Create some test references
        refs = [
            PageReference(uri=PageURI(root="test", type="test", id="1", version=1)),
            PageReference(uri=PageURI(root="test", type="test", id="2", version=1)),
        ]

        # Set up mock retriever
        mock_retriever = MockRetrieverAgent(refs)
        context.retriever = mock_retriever

        # Perform search
        result = context.search("find test pages")

        assert len(result.results) == 2
        for ref in result.results:
            assert isinstance(ref.page, DocumentPage)
            assert ref.page.title.startswith("Test Page")

    def test_mixed_page_types_workflow(self, context: ServerContext) -> None:
        """Test workflow with multiple page types."""
        context.register_handler("document", document_page_handler)
        context.register_handler("alternate", alternate_page_handler)

        # Create mixed references
        refs = [
            PageReference(
                uri=PageURI(root="test", type="document", id="doc1", version=1)
            ),
            PageReference(
                uri=PageURI(root="test", type="alternate", id="alt1", version=1)
            ),
        ]

        resolved_refs = context._resolve_references(refs)

        assert len(resolved_refs) == 2
        assert isinstance(resolved_refs[0].page, DocumentPage)
        assert isinstance(resolved_refs[1].page, AlternateTestPage)
        assert resolved_refs[0].page.title == "Test Page doc1"
        assert resolved_refs[1].page.name == "Alternate Page alt1"


class TestInvalidatorIntegration:
    """Test invalidator integration with ServerContext."""

    class GoogleDocPage(Page):
        """Test Google Docs page with revision tracking."""

        title: str
        content: str
        revision: str = Field(exclude=True)

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    def test_register_handler_with_invalidator(self, context: ServerContext) -> None:
        """Test registering a handler with an invalidator function."""

        def handle_gdoc(page_uri: PageURI) -> "TestInvalidatorIntegration.GoogleDocPage":
            # Mock handler that creates a document
            return TestInvalidatorIntegration.GoogleDocPage(
                uri=page_uri,
                title=f"Document {page_uri.id}",
                content=f"Content for {page_uri.id}",
                revision="current",
            )

        def validate_gdoc(page: "TestInvalidatorIntegration.GoogleDocPage") -> bool:
            # Mock validator - only "current" revision is valid
            return page.revision == "current"

        # Register handler with invalidator
        context.register_handler("gdoc", handle_gdoc, validate_gdoc)

        # Verify both handler and invalidator are registered
        assert "gdoc" in context._page_handlers
        assert "gdoc" in context._page_invalidators

    def test_invalidator_decorator_syntax(self, context: ServerContext) -> None:
        """Test using invalidator with decorator syntax."""

        def validate_gdoc(page: "TestInvalidatorIntegration.GoogleDocPage") -> bool:
            return page.revision == "current"

        @context.handler("gdoc", invalidator=validate_gdoc)
        def handle_gdoc(page_uri: PageURI) -> "TestInvalidatorIntegration.GoogleDocPage":
            return TestInvalidatorIntegration.GoogleDocPage(
                uri=page_uri,
                title=f"Document {page_uri.id}",
                content=f"Content for {page_uri.id}",
                revision="current",
            )

        # Verify both handler and invalidator are registered
        assert "gdoc" in context._page_handlers
        assert "gdoc" in context._page_invalidators

    def test_get_page_validates_with_registered_invalidator(
        self, context: ServerContext
    ) -> None:
        """Test that getting a page properly uses the registered validator."""

        def handle_gdoc(page_uri: PageURI) -> "TestInvalidatorIntegration.GoogleDocPage":
            # Return different revisions based on doc_id to test validation
            revision = "current" if page_uri.id != "old_doc" else "old"
            return TestInvalidatorIntegration.GoogleDocPage(
                uri=page_uri,
                title=f"Document {page_uri.id}",
                content=f"Content for {page_uri.id}",
                revision=revision,
            )

        def validate_gdoc(page: "TestInvalidatorIntegration.GoogleDocPage") -> bool:
            return page.revision == "current"

        context.register_handler("gdoc", handle_gdoc, validate_gdoc)

        # Get a page with "current" revision - should work
        page = context.get_page("test/gdoc:doc1")
        assert page is not None
        assert page.title == "Document doc1"

        # This demonstrates that the validator is working when pages are accessed
