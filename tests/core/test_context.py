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
        uri=page_uri,
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
        context.route("document")(document_page_handler)

        # No error means success - handler is stored internally

    def test_register_multiple_handlers(self, context: ServerContext) -> None:
        """Test registering handlers for multiple page types."""
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)
        # No error means success

    def test_register_handler_duplicate_error(self, context: ServerContext) -> None:
        """Test error when registering duplicate handler."""
        context.route("document")(document_page_handler)
        with pytest.raises(RuntimeError, match="already registered"):
            context.route("document")(document_page_handler)


class TestGetPage:
    """Test get_page functionality."""

    def test_get_page_create_new(self, context: ServerContext) -> None:
        """Test creating new page via handler."""
        context.route("document")(document_page_handler)

        uri = PageURI(root="test", type="document", id="new_page", version=1)
        page = context.get_page(uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page new_page"

    def test_get_page_with_uri_from_reference(self, context: ServerContext) -> None:
        """Test getting page using URI from PageReference."""
        context.route("document")(document_page_handler)

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
        with pytest.raises(
            RuntimeError, match="No handler registered for type: unregistered"
        ):
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
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

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
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

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
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

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
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

        resolved_refs = context._resolve_references(sample_page_references)

        assert len(resolved_refs) == 3
        for ref in resolved_refs:
            assert ref._page is not None


class TestIntegration:
    """Test integration scenarios."""

    def test_full_workflow_with_decorator(self, context: ServerContext) -> None:
        """Test full workflow using decorator registration."""

        @context.route("test")
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
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

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


class TestValidatorIntegration:
    """Test validator integration with ServerContext."""

    class GoogleDocPage(Page):
        """Test Google Docs page with revision tracking."""

        title: str
        content: str
        revision: str = Field(exclude=True)

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    def test_get_page_validates_with_registered_validator(
        self, context: ServerContext
    ) -> None:
        """Test that getting a page properly uses the registered validator."""

        @context.route("gdoc")
        def handle_gdoc(page_uri: PageURI) -> TestValidatorIntegration.GoogleDocPage:
            """Handle Google Doc page."""
            # Return different revisions based on doc_id to test validation
            revision = "current" if page_uri.id != "old_doc" else "old"
            return TestValidatorIntegration.GoogleDocPage(
                uri=page_uri,
                title=f"Document {page_uri.id}",
                content=f"Content for {page_uri.id}",
                revision=revision,
            )

        @context.validator
        def validate_gdoc(page: TestValidatorIntegration.GoogleDocPage) -> bool:
            """Validate Google Doc page."""
            return page.revision == "current"

        # Get a page with "current" revision - should work
        page = context.get_page("test/gdoc:doc1")
        assert page is not None
        assert page.title == "Document doc1"

        # This demonstrates that the validator is working when pages are accessed


class TestStrictHandlerValidation:
    """Test strict handler signature validation functionality."""

    class ValidPage(Page):
        """Valid test page for handler validation tests."""

        title: str
        content: str

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)

    def test_decorator_with_proper_annotation_succeeds(
        self, context: ServerContext
    ) -> None:
        """Test that the decorator also enforces proper annotations."""

        @context.route("valid_decorator")
        def valid_handler(page_uri: PageURI) -> TestStrictHandlerValidation.ValidPage:
            return TestStrictHandlerValidation.ValidPage(
                uri=page_uri, title="Valid Decorator", content="Content"
            )

        assert "valid_decorator" in context._router._handlers

    def test_decorator_with_invalid_annotation_fails(
        self, context: ServerContext
    ) -> None:
        """Test that the decorator rejects invalid annotations."""

        with pytest.raises(RuntimeError, match="has a string return type annotation"):

            @context.route("invalid_decorator")
            def invalid_handler(
                page_uri: PageURI,
            ) -> "TestStrictHandlerValidation.ValidPage":
                return TestStrictHandlerValidation.ValidPage(
                    uri=page_uri, title="Invalid", content="Content"
                )

    def test_validation_happens_at_registration_not_runtime(
        self, context: ServerContext
    ) -> None:
        """Test that validation happens at registration time, not when get_page is called."""

        # This should fail immediately at registration
        with pytest.raises(RuntimeError, match="must have a return type annotation"):

            def invalid_handler(page_uri: PageURI):
                return TestStrictHandlerValidation.ValidPage(
                    uri=page_uri, title="Test", content="Content"
                )

            context.route("invalid")(invalid_handler)

        # Verify handler was not registered
        assert "invalid" not in context._router._handlers


class TestEnhancedCaching:
    """Test enhanced caching functionality and handler signature validation."""

    class CacheTestPage(Page):
        """Test page for caching tests."""

        content: str
        call_count: int = Field(exclude=True, default=0)

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    def test_caching_enabled_by_default(self, context: ServerContext) -> None:
        """Test that caching is enabled by default and works correctly."""
        call_count = 0

        def handle_cached(page_uri: PageURI) -> TestEnhancedCaching.CacheTestPage:
            nonlocal call_count
            call_count += 1
            return TestEnhancedCaching.CacheTestPage(
                uri=page_uri, content=f"Content {call_count}", call_count=call_count
            )

        context.route("cached_test", cache=True)(handle_cached)

        # First call should invoke handler
        page1 = context.get_page("test/cached_test:doc1")
        assert page1.content == "Content 1"
        assert call_count == 1

        # Second call to same URI should use cache (handler not called again)
        page2 = context.get_page("test/cached_test:doc1")
        assert page2.content == "Content 1"  # Same content as first call
        assert call_count == 1  # Handler not called again

        # Different URI should call handler again
        page3 = context.get_page("test/cached_test:doc2")
        assert page3.content == "Content 2"
        assert call_count == 2

    def test_cache_disabled_calls_handler_every_time(
        self, context: ServerContext
    ) -> None:
        """Test that disabling cache calls handler every time."""
        call_count = 0

        def handle_uncached(page_uri: PageURI) -> TestEnhancedCaching.CacheTestPage:
            nonlocal call_count
            call_count += 1
            return TestEnhancedCaching.CacheTestPage(
                uri=page_uri, content=f"Content {call_count}", call_count=call_count
            )

        context.route("uncached_test", cache=False)(handle_uncached)

        # First call
        page1 = context.get_page("test/uncached_test:doc1")
        assert page1.content == "Content 1"
        assert call_count == 1

        # Second call to same URI should call handler again (no caching)
        page2 = context.get_page("test/uncached_test:doc1")
        assert page2.content == "Content 2"  # Different content
        assert call_count == 2  # Handler called again

    def test_cache_stores_after_handler_execution(self, context: ServerContext) -> None:
        """Test that pages are stored in cache after handler execution."""

        @context.route("storage_test", cache=True)
        def handle_for_storage(page_uri: PageURI) -> TestEnhancedCaching.CacheTestPage:
            """Handle for storage."""
            return TestEnhancedCaching.CacheTestPage(
                uri=page_uri, content="test content"
            )

        # Get a page to trigger handler and caching
        page_uri = PageURI.parse("test/storage_test:doc1@1")
        context.get_page(page_uri)

        # Verify the page was stored in cache by directly checking cache
        cached_page = context.page_cache.get(
            TestEnhancedCaching.CacheTestPage, page_uri
        )
        assert cached_page is not None
        assert cached_page.content == "test content"
        assert cached_page.uri == page_uri


class TestHandlerSignatureValidation:
    """Test strict handler signature validation."""

    class ValidTestPage(Page):
        """Valid test page for signature tests."""

        data: str

    def test_valid_handler_signature_accepted(self, context: ServerContext) -> None:
        """Test that valid handler signatures are accepted."""

        @context.route("valid_test")
        def valid_handler(
            page_uri: PageURI,
        ) -> TestHandlerSignatureValidation.ValidTestPage:
            return TestHandlerSignatureValidation.ValidTestPage(
                uri=page_uri, data="test"
            )

        # Should not raise any exception
        assert "valid_test" in context._router._handlers

    def test_missing_return_annotation_rejected(self, context: ServerContext) -> None:
        """Test that handlers without return annotations are rejected."""

        def invalid_handler(page_uri: PageURI):  # No return annotation
            return TestHandlerSignatureValidation.ValidTestPage(
                uri=page_uri, data="test"
            )

        with pytest.raises(RuntimeError, match="must have a return type annotation"):
            context.route("invalid_test")(invalid_handler)

    def test_string_return_annotation_rejected(self, context: ServerContext) -> None:
        """Test that string forward reference annotations are rejected."""

        def invalid_handler(
            page_uri: PageURI,
        ) -> "TestHandlerSignatureValidation.ValidTestPage":
            return TestHandlerSignatureValidation.ValidTestPage(
                uri=page_uri, data="test"
            )

        with pytest.raises(RuntimeError, match="has a string return type annotation"):
            context.route("invalid_test")(invalid_handler)

    def test_non_class_return_annotation_rejected(self, context: ServerContext) -> None:
        """Test that non-class return annotations are rejected."""

        def invalid_handler(page_uri: PageURI) -> str:  # str is not a Page subclass
            return "not a page"

        with pytest.raises(
            RuntimeError, match="return type annotation must be a Page subclass"
        ):
            context.route("invalid_test")(invalid_handler)

    def test_non_page_class_return_annotation_rejected(
        self, context: ServerContext
    ) -> None:
        """Test that non-Page class return annotations are rejected."""

        class NotAPage:
            pass

        def invalid_handler(page_uri: PageURI) -> NotAPage:
            return NotAPage()

        with pytest.raises(
            RuntimeError, match="return type annotation must be a Page subclass"
        ):
            context.route("invalid_test")(invalid_handler)

    def test_handler_validation_happens_at_registration(
        self, context: ServerContext
    ) -> None:
        """Test that handler validation happens at registration time, not usage time."""

        def invalid_handler(page_uri: PageURI) -> str:
            return "invalid"

        # The error should happen during registration, not when calling get_page
        with pytest.raises(
            RuntimeError, match="return type annotation must be a Page subclass"
        ):
            context.route("invalid_test")(invalid_handler)

        # The handler should not be registered
        assert "invalid_test" not in context._router._handlers


class TestCachingIntegration:
    """Test integration between caching and other features."""

    class IntegrationTestPage(Page):
        """Test page for integration tests."""

        value: str
        timestamp: str

    def test_caching_with_invalidator(self, context: ServerContext) -> None:
        """Test that caching works correctly with invalidators."""
        call_count = 0

        @context.route("integration_test", cache=True)
        def handle_with_invalidator(
            page_uri: PageURI,
        ) -> TestCachingIntegration.IntegrationTestPage:
            nonlocal call_count
            call_count += 1
            return TestCachingIntegration.IntegrationTestPage(
                uri=page_uri, value=f"value_{call_count}", timestamp="2024-01-01"
            )

        @context.validator
        def validate_page(page: TestCachingIntegration.IntegrationTestPage) -> bool:
            # Only pages with timestamp "2024-01-01" are valid
            return page.timestamp == "2024-01-01"

        # First call should invoke handler and cache the result
        page1 = context.get_page("test/integration_test:doc1")
        assert page1.value == "value_1"
        assert call_count == 1

        # Second call should use cache
        page2 = context.get_page("test/integration_test:doc1")
        assert page2.value == "value_1"
        assert call_count == 1  # Handler not called again
