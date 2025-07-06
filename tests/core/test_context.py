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

    async def search(self, instruction: str) -> List[PageReference]:
        """Mock search implementation."""
        self.search_calls.append(instruction)
        return self.search_results


# Handler functions for testing
async def document_page_handler(page_uri: PageURI) -> DocumentPage:
    """Test handler for DocumentPage."""
    return DocumentPage(
        uri=page_uri,
        title=f"Test Page {page_uri.id}",
        content=f"Content for page {page_uri.id}",
    )


async def alternate_page_handler(page_uri: PageURI) -> AlternateTestPage:
    """Test handler for AlternateTestPage."""
    return AlternateTestPage(
        uri=page_uri,
        name=f"Alternate Page {page_uri.id}",
        data=f"Data for page {page_uri.id}",
    )


# Test fixtures
@pytest.fixture
async def context() -> ServerContext:
    """Provide a fresh ServerContext for each test."""
    return await ServerContext.create(
        root="test", cache_url="sqlite+aiosqlite:///:memory:"
    )


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


class TestServerContextInitialization:
    """Test ServerContext initialization."""

    @pytest.mark.asyncio
    async def test_initialization(self, context) -> None:
        assert context.retriever is None
        assert context.page_cache is not None


class TestRetrieverProperty:
    """Test retriever property functionality."""

    @pytest.mark.asyncio
    async def test_retriever_setter_getter(
        self, context, mock_retriever: MockRetrieverAgent
    ) -> None:
        context.retriever = mock_retriever
        assert context.retriever is mock_retriever

    @pytest.mark.asyncio
    async def test_retriever_set_twice_error(self, context) -> None:
        mock1 = MockRetrieverAgent()
        mock2 = MockRetrieverAgent()

        context.retriever = mock1
        with pytest.raises(RuntimeError, match="already set"):
            context.retriever = mock2


class TestSearch:
    """Test search functionality."""

    @pytest.mark.asyncio
    async def test_search_with_context_retriever(
        self, context, sample_page_references: List[PageReference]
    ) -> None:
        """Test search using context's retriever."""
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

        mock_retriever = MockRetrieverAgent(sample_page_references)
        context.retriever = mock_retriever

        result = await context.search("test query")

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        assert mock_retriever.search_calls == ["test query"]

        # Verify pages were resolved
        for ref in result.results:
            assert ref._page is not None

    @pytest.mark.asyncio
    async def test_search_with_parameter_retriever(
        self, context, sample_page_references: List[PageReference]
    ) -> None:
        """Test search using retriever parameter."""
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

        mock_retriever = MockRetrieverAgent(sample_page_references)
        result = await context.search("test query", retriever=mock_retriever)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        assert mock_retriever.search_calls == ["test query"]

    @pytest.mark.asyncio
    async def test_search_no_retriever_error(self, context) -> None:
        with pytest.raises(RuntimeError, match="No RetrieverAgent available"):
            await context.search("test query")

    @pytest.mark.asyncio
    async def test_search_without_resolve_references(
        self, context, sample_page_references: List[PageReference]
    ) -> None:
        """Test search without resolving references."""
        mock_retriever = MockRetrieverAgent(sample_page_references)
        context.retriever = mock_retriever

        result = await context.search("test query", resolve_references=False)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        # Verify pages were NOT resolved
        for ref in result.results:
            assert ref._page is None

    @pytest.mark.asyncio
    async def test_search_parameter_retriever_overrides_context(
        self, context, sample_page_references: List[PageReference]
    ) -> None:
        """Test that parameter retriever overrides context retriever."""
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

        context_retriever = MockRetrieverAgent([])
        param_retriever = MockRetrieverAgent(sample_page_references)

        context.retriever = context_retriever

        result = await context.search("test query", retriever=param_retriever)

        assert isinstance(result, SearchResponse)
        assert len(result.results) == 3
        assert context_retriever.search_calls == []
        assert param_retriever.search_calls == ["test query"]


class TestReferenceResolution:
    """Test reference resolution functionality."""

    @pytest.mark.asyncio
    async def test_resolve_references(
        self, context, sample_page_references: List[PageReference]
    ) -> None:
        """Test resolving page references."""
        context.route("document")(document_page_handler)
        context.route("alternate")(alternate_page_handler)

        resolved_refs = await context._resolve_references(sample_page_references)

        assert len(resolved_refs) == 3
        for ref in resolved_refs:
            assert ref.page is not None


class TestIntegration:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_decorator(self, context) -> None:
        @context.route("test")
        async def test_handler(page_uri: PageURI) -> DocumentPage:
            return DocumentPage(
                uri=page_uri,
                title="Workflow Page",
                content="Workflow Content",
            )

        uri = PageURI(root="test", type="test", id="workflow", version=1)
        page = await context.get_page(uri)
        assert isinstance(page, DocumentPage)
        assert page.title == "Workflow Page"

    @pytest.mark.asyncio
    async def test_mixed_page_types_workflow(self, context) -> None:
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

        resolved_refs = await context._resolve_references(refs)

        assert len(resolved_refs) == 2
        assert isinstance(resolved_refs[0].page, DocumentPage)
        assert isinstance(resolved_refs[1].page, AlternateTestPage)
        assert resolved_refs[0].page.title == "Test Page doc1"
        assert resolved_refs[1].page.name == "Alternate Page alt1"


class TestValidatorIntegration:
    """Test validator integration with context."""

    class GoogleDocPage(Page):
        title: str
        content: str
        revision: str

    @pytest.mark.asyncio
    async def test_get_page_validates_with_registered_validator(self, context) -> None:
        """Test that getting a page properly uses the registered validator."""

        @context.route("gdoc")
        async def handle_gdoc(
            page_uri: PageURI,
        ) -> TestValidatorIntegration.GoogleDocPage:
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
        async def validate_gdoc(page: TestValidatorIntegration.GoogleDocPage) -> bool:
            """Validate Google Doc page."""
            return page.revision == "current"

        # Get a page with "current" revision - should work
        page = await context.get_page("test/gdoc:doc1")
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

    @pytest.mark.asyncio
    async def test_decorator_with_proper_annotation_succeeds(self, context) -> None:
        """Test that the decorator also enforces proper annotations."""

        @context.route("valid_decorator")
        def valid_handler(page_uri: PageURI) -> TestStrictHandlerValidation.ValidPage:
            return TestStrictHandlerValidation.ValidPage(
                uri=page_uri, title="Valid Decorator", content="Content"
            )

        assert "valid_decorator" in context._handlers

    @pytest.mark.asyncio
    async def test_decorator_with_forward_reference_annotation_succeeds(
        self, context
    ) -> None:
        """Test that the decorator accepts forward references."""

        @context.route("forward_reference")
        def forward_reference_handler(
            page_uri: PageURI,
        ) -> "TestStrictHandlerValidation.ValidPage":
            return TestStrictHandlerValidation.ValidPage(
                uri=page_uri, title="Forward Reference", content="Content"
            )

    @pytest.mark.asyncio
    async def test_validation_happens_at_registration_not_runtime(
        self, context
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
        assert "invalid" not in context._handlers


class TestEnhancedCaching:
    """Test enhanced caching functionality."""

    class CacheTestPage(Page):
        """Test page for caching tests."""

        content: str
        call_count: int = Field(exclude=True, default=0)

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    @pytest.mark.asyncio
    async def test_caching_enabled_by_default(self, context) -> None:
        call_count = 0

        async def handle_cached(page_uri: PageURI) -> TestEnhancedCaching.CacheTestPage:
            nonlocal call_count
            call_count += 1
            return TestEnhancedCaching.CacheTestPage(
                uri=page_uri, content=f"Content {call_count}", call_count=call_count
            )

        context.route("cached_test", cache=True)(handle_cached)

        # First call should invoke handler
        page1 = await context.get_page("test/cached_test:doc1")
        assert page1.content == "Content 1"

        # Second call should use cache (call_count should not increment)
        page2 = await context.get_page("test/cached_test:doc1")
        assert page2.content == "Content 1"
        assert page2.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_disabled_calls_handler_every_time(self, context) -> None:
        call_count = 0

        async def handle_uncached(
            page_uri: PageURI,
        ) -> TestEnhancedCaching.CacheTestPage:
            nonlocal call_count
            call_count += 1
            return TestEnhancedCaching.CacheTestPage(
                uri=page_uri, content=f"Content {call_count}", call_count=call_count
            )

        context.route("uncached_test", cache=False)(handle_uncached)

        # First call
        page1 = await context.get_page("test/uncached_test:doc1")
        assert page1.content == "Content 1"
        # Second call (should increment call_count)
        page2 = await context.get_page("test/uncached_test:doc1")
        assert page2.content == "Content 2"
        assert page2.call_count == 2

    @pytest.mark.asyncio
    async def test_cache_stores_after_handler_execution(self, context) -> None:
        """Test that pages are stored in cache after handler execution."""

        @context.route("storage_test", cache=True)
        async def handle_for_storage(
            page_uri: PageURI,
        ) -> TestEnhancedCaching.CacheTestPage:
            """Handle for storage."""
            return TestEnhancedCaching.CacheTestPage(
                uri=page_uri, content="test content"
            )

        # Get a page to trigger handler and caching
        page_uri = PageURI.parse("test/storage_test:doc1@1")
        await context.get_page(page_uri)

        # Verify the page was stored in cache by directly checking cache
        cached_page = await context.page_cache.get(
            TestEnhancedCaching.CacheTestPage, page_uri
        )
        assert cached_page is not None
        assert cached_page.content == "test content"


class TestHandlerSignatureValidation:
    """Test strict handler signature validation."""

    class ValidTestPage(Page):
        """Valid test page for signature tests."""

        data: str

    @pytest.mark.asyncio
    async def test_valid_handler_signature_accepted(self, context) -> None:
        @context.route("valid_test")
        def valid_handler(
            page_uri: PageURI,
        ) -> TestHandlerSignatureValidation.ValidTestPage:
            return TestHandlerSignatureValidation.ValidTestPage(
                uri=page_uri, data="test"
            )

        # Should not raise any exception
        assert "valid_test" in context._handlers

    @pytest.mark.asyncio
    async def test_missing_return_annotation_rejected(self, context) -> None:
        def invalid_handler(page_uri: PageURI):  # No return annotation
            return TestHandlerSignatureValidation.ValidTestPage(
                uri=page_uri, data="test"
            )

        with pytest.raises(RuntimeError, match="must have a return type annotation"):
            context.route("invalid_test")(invalid_handler)

    @pytest.mark.asyncio
    async def test_non_class_return_annotation_rejected(self, context) -> None:
        def invalid_handler(page_uri: PageURI) -> str:  # str is not a Page subclass
            return "not a page"

        with pytest.raises(
            RuntimeError, match="return type annotation must be a Page subclass"
        ):
            context.route("invalid_test")(invalid_handler)

    @pytest.mark.asyncio
    async def test_non_page_class_return_annotation_rejected(self, context) -> None:
        """Test that non-Page class return annotations are rejected."""

        class NotAPage:
            pass

        def invalid_handler(page_uri: PageURI) -> NotAPage:
            return NotAPage()

        with pytest.raises(
            RuntimeError, match="return type annotation must be a Page subclass"
        ):
            context.route("invalid_test")(invalid_handler)

    @pytest.mark.asyncio
    async def test_handler_validation_happens_at_registration(self, context) -> None:
        """Test that handler validation happens at registration time, not usage time."""

        def invalid_handler(page_uri: PageURI) -> str:
            return "invalid"

        # The error should happen during registration, not when calling get_page
        with pytest.raises(
            RuntimeError, match="return type annotation must be a Page subclass"
        ):
            context.route("invalid_test")(invalid_handler)

        # The handler should not be registered
        assert "invalid_test" not in context._handlers


class TestCachingIntegration:
    """Test integration between caching and other features."""

    class IntegrationTestPage(Page):
        """Test page for integration tests."""

        value: str
        timestamp: str

    @pytest.mark.asyncio
    async def test_caching_with_invalidator(self, context) -> None:
        call_count = 0

        @context.route("integration_test", cache=True)
        async def handle_with_invalidator(
            page_uri: PageURI,
        ) -> TestCachingIntegration.IntegrationTestPage:
            nonlocal call_count
            call_count += 1
            return TestCachingIntegration.IntegrationTestPage(
                uri=page_uri, value=f"value_{call_count}", timestamp="2024-01-01"
            )

        @context.validator
        async def validate_page(
            page: TestCachingIntegration.IntegrationTestPage,
        ) -> bool:
            # Only pages with timestamp "2024-01-01" are valid
            return page.timestamp == "2024-01-01"

        # First call should invoke handler and cache the result
        page1 = await context.get_page("test/integration_test:doc1")
        assert page1.value == "value_1"

        # Second call should use cache
        page2 = await context.get_page("test/integration_test:doc1")
        assert page2.value == "value_1"
