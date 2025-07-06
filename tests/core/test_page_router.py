"""Tests for the PageRouter class.

This module contains comprehensive tests for the PageRouter functionality,
including route registration, handler validation, page retrieval, caching,
and error handling.
"""

import asyncio
import logging
import tempfile
from typing import Any, Awaitable, Union
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import Field

from praga_core.page_cache import PageCache
from praga_core.page_router import PageRouterMixin
from praga_core.types import Page, PageReference, PageURI, TextPage

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("praga_core.page_cache").setLevel(logging.DEBUG)
logging.getLogger("praga_core.page_router").setLevel(logging.DEBUG)


# Test page classes
class SamplePage(Page):
    """Sample page for basic functionality."""

    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


class SecondSamplePage(Page):
    """Second sample page for multiple handler testing."""

    name: str
    data: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.name) + len(self.data)) // 4


class CountingPage(Page):
    """Test page that tracks how many times it's created."""

    value: str
    call_count: int = Field(exclude=True, default=0)

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = len(self.value) // 4


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


# Concrete PageRouter implementation for testing
class PageRouter(PageRouterMixin):
    """Concrete PageRouter implementation for testing."""

    def __init__(self, page_cache: PageCache, root: str = "test") -> None:
        super().__init__()
        self._page_cache = page_cache
        self._root = root

    @property
    def root(self) -> str:
        return self._root

    @property
    def page_cache(self) -> PageCache:
        return self._page_cache


# Test fixtures
@pytest.fixture
def temp_db_url() -> str:
    """Provide a temporary database URL for testing."""
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    return f"sqlite+aiosqlite:///{temp_file.name}"


@pytest.fixture
async def page_cache(temp_db_url: str) -> PageCache:
    """Provide a fresh PageCache instance for each test."""
    return await PageCache.create(temp_db_url, drop_previous=True)


@pytest.fixture
def page_router(page_cache: PageCache) -> PageRouter:
    """Provide a fresh PageRouter instance for each test."""
    return PageRouter(page_cache)


@pytest.fixture
def mock_page_cache() -> MagicMock:
    """Provide a mock PageCache for testing."""
    mock = MagicMock(spec=PageCache)
    mock.get = AsyncMock(return_value=None)
    mock.store = MagicMock(return_value=True)
    mock.get_latest_version = MagicMock(return_value=None)
    mock._storage = MagicMock()
    mock._storage._registry = MagicMock()
    mock._storage._registry.ensure_registered = MagicMock()
    return mock


@pytest.fixture
def page_router_with_mock(mock_page_cache: MagicMock) -> PageRouter:
    """Provide a PageRouter with mock cache for testing."""
    return PageRouter(mock_page_cache)


# Handler functions for testing
async def sample_handler(page_uri: PageURI) -> SamplePage:
    """Sample handler for SamplePage."""
    return SamplePage(
        uri=page_uri,
        title=f"Test Page {page_uri.id}",
        content=f"Content for {page_uri.id}",
    )


async def second_handler(page_uri: PageURI) -> SecondSamplePage:
    """Test handler for SecondSamplePage."""
    return SecondSamplePage(
        uri=page_uri,
        name=f"Second Page {page_uri.id}",
        data=f"Data for {page_uri.id}",
    )


# Handler functions for testing (from test_context.py)
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


async def counting_handler(page_uri: PageURI) -> CountingPage:
    """Handler that creates counting pages."""
    return CountingPage(
        uri=page_uri,
        value=f"Value {page_uri.id}",
        call_count=1,
    )


# Invalid handler functions for testing
def invalid_handler_no_annotation(page_uri: PageURI):
    """Invalid handler without return annotation."""


def invalid_handler_string_annotation(page_uri: PageURI) -> "SamplePage":
    """Invalid handler with string annotation."""


def invalid_handler_wrong_type(page_uri: PageURI) -> str:
    """Invalid handler with wrong return type."""


class NotAPage:
    """Not a Page subclass."""


def invalid_handler_non_page(page_uri: PageURI) -> NotAPage:
    """Invalid handler returning non-Page class."""


class TestPageRouterInitialization:
    """Test PageRouter initialization."""

    def test_initialization_with_cache(self, page_cache: PageCache) -> None:
        """Test PageRouter initialization with cache."""
        router = PageRouter(page_cache)
        assert router._page_cache is page_cache
        assert router._handlers == {}
        assert router._cache_enabled == {}

    def test_initialization_with_mock_cache(self, mock_page_cache: MagicMock) -> None:
        """Test PageRouter initialization with mock cache."""
        router = PageRouter(mock_page_cache)
        assert router._page_cache is mock_page_cache
        assert router._handlers == {}
        assert router._cache_enabled == {}


class TestRouteDecorator:
    """Test the route decorator functionality."""

    def test_route_decorator_basic(self, page_router: PageRouter) -> None:
        """Test basic route decorator usage."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        assert "test" in page_router._handlers
        assert page_router._handlers["test"] == handler
        assert page_router._cache_enabled["test"] is True

    def test_route_decorator_with_cache_disabled(self, page_router: PageRouter) -> None:
        """Test route decorator with cache disabled."""

        @page_router.route("test", cache=False)
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        assert "test" in page_router._handlers
        assert page_router._cache_enabled["test"] is False

    def test_route_decorator_multiple_handlers(self, page_router: PageRouter) -> None:
        """Test registering multiple handlers."""

        @page_router.route("test1")
        async def handler1(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test1", content="Content1")

        @page_router.route("test2")
        async def handler2(page_uri: PageURI) -> SecondSamplePage:
            return SecondSamplePage(uri=page_uri, name="Test2", data="Data2")

        assert "test1" in page_router._handlers
        assert "test2" in page_router._handlers
        assert page_router._handlers["test1"] == handler1
        assert page_router._handlers["test2"] == handler2

    def test_route_decorator_duplicate_path_error(
        self, page_router: PageRouter
    ) -> None:
        """Test error when registering duplicate paths."""

        @page_router.route("test")
        async def handler1(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        with pytest.raises(
            RuntimeError, match="Handler already registered for path: test"
        ):

            @page_router.route("test")
            async def handler2(page_uri: PageURI) -> SamplePage:
                return SamplePage(uri=page_uri, title="Test2", content="Content2")

    def test_route_decorator_handler_validation(self, page_router: PageRouter) -> None:
        """Test handler validation during registration."""
        with pytest.raises(RuntimeError, match="must have a return type annotation"):

            @page_router.route("test")
            def handler(page_uri: PageURI):
                pass

    def test_route_decorator_wrong_type_error(self, page_router: PageRouter) -> None:
        """Test error for wrong return type."""
        with pytest.raises(RuntimeError, match="must be a Page subclass"):

            @page_router.route("test")
            def handler(page_uri: PageURI) -> str:
                pass

    def test_route_decorator_non_page_class_error(
        self, page_router: PageRouter
    ) -> None:
        """Test error for non-Page class return type."""
        with pytest.raises(RuntimeError, match="must be a Page subclass"):

            @page_router.route("test")
            def handler(page_uri: PageURI) -> NotAPage:
                pass


class TestHandlerRetrieval:
    """Test handler retrieval functionality."""

    def test_get_handler_existing(self, page_router: PageRouter) -> None:
        """Test getting an existing handler."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        retrieved_handler = page_router.get_handler("test")
        assert retrieved_handler == handler

    def test_get_handler_nonexistent(self, page_router: PageRouter) -> None:
        """Test getting a nonexistent handler raises KeyError."""
        with pytest.raises(KeyError):
            page_router.get_handler("nonexistent")

    def test_is_cache_enabled_existing(self, page_router: PageRouter) -> None:
        """Test checking cache enabled for existing path."""

        @page_router.route("test", cache=False)
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        assert page_router.is_cache_enabled("test") is False

    def test_is_cache_enabled_nonexistent(self, page_router: PageRouter) -> None:
        """Test checking cache enabled for nonexistent path returns default."""
        assert page_router.is_cache_enabled("nonexistent") is True


class TestGetPage:
    """Test page retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_page_basic(self, page_router: PageRouter) -> None:
        """Test basic page retrieval."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        page = await page_router.get_page(page_uri)

        assert isinstance(page, SamplePage)
        assert page.uri == page_uri
        assert page.title == "Test"
        assert page.content == "Content"

    @pytest.mark.asyncio
    async def test_get_page_no_handler_error(self, page_router: PageRouter) -> None:
        """Test error when no handler is registered."""
        page_uri = PageURI(root="test", type="nonexistent", id="page1", version=1)

        with pytest.raises(
            RuntimeError, match="No handler registered for type: nonexistent"
        ):
            await page_router.get_page(page_uri)

    @pytest.mark.asyncio
    async def test_get_page_with_cache_hit(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page retrieval with cache hit."""
        # Setup mock to return cached page
        cached_page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Cached",
            content="From cache",
        )
        page_router_with_mock._page_cache.get.return_value = cached_page

        @page_router_with_mock.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Fresh", content="From handler")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        page = await page_router_with_mock.get_page(page_uri)

        assert page == cached_page
        assert page.title == "Cached"
        page_router_with_mock._page_cache.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_page_with_cache_miss(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page retrieval with cache miss."""
        # Setup mock to return None (cache miss)
        page_router_with_mock._page_cache.get.return_value = None

        @page_router_with_mock.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Fresh", content="From handler")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        page = await page_router_with_mock.get_page(page_uri)

        assert page.title == "Fresh"
        # get() is called twice - once for initial cache check, once in _store_in_cache
        assert page_router_with_mock._page_cache.get.call_count == 2
        page_router_with_mock._page_cache.store.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_page_cache_disabled(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page retrieval with cache disabled."""

        @page_router_with_mock.route("test", cache=False)
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Fresh", content="From handler")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        page = await page_router_with_mock.get_page(page_uri)

        assert page.title == "Fresh"
        # Cache store should not be called when disabled
        page_router_with_mock._page_cache.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_page_cache_error_handled(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test cache error is handled gracefully."""
        # Setup mock to raise exception
        page_router_with_mock._page_cache.get.side_effect = Exception("Cache error")

        @page_router_with_mock.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Fresh", content="From handler")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        page = await page_router_with_mock.get_page(page_uri)

        # Should still work despite cache error
        assert page.title == "Fresh"

    @pytest.mark.asyncio
    async def test_get_page_version_creation(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page URI version creation when version is None."""

        @page_router_with_mock.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        # Create URI without version
        page_uri = PageURI(root="test", type="test", id="page1", version=None)
        page = await page_router_with_mock.get_page(page_uri)

        # Check that handler was called with versioned URI
        assert page.uri.version == 1

    @pytest.mark.asyncio
    async def test_get_page_version_increment(self, page_router: PageRouter) -> None:
        """Test page URI version increment when cache has latest version."""
        # Store a page with version=3 in the real cache
        page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=3),
            title="Test v3",
            content="Content v3",
        )
        await page_router._page_cache.store(page)

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        page_uri = PageURI(root="test", type="test", id="page1", version=None)
        page = await page_router.get_page(page_uri)

        # Version should not be incremented
        assert page.uri.version == 3

    @pytest.mark.asyncio
    async def test_store_increments_version(self, page_router: PageRouter) -> None:
        """Test that storing a new page with version=None after existing version=3 results in version=4."""
        # Store a page with version=3 in the real cache
        page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=3),
            title="Test v3",
            content="Content v3",
        )
        await page_router._page_cache.store(page)

        # Simulate logic for storing a new page with version=None after existing version=3
        uri = await page_router._create_page_uri(SamplePage, "test", "test", "page1")
        new_page = SamplePage(uri=uri, title="Test v4", content="Content v4")
        await page_router._page_cache.store(new_page)

        # Now the latest version should be 4
        latest = await page_router._page_cache.get(
            SamplePage, PageURI(root="test", type="test", id="page1", version=None)
        )
        assert latest.uri.version == 4
        assert latest.title == "Test v4"


class TestGetPages:
    """Test bulk page retrieval functionality."""

    @pytest.mark.asyncio
    async def test_get_pages_basic(self, page_router: PageRouter) -> None:
        """Test basic bulk page retrieval."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(
                uri=page_uri,
                title=f"Test {page_uri.id}",
                content=f"Content {page_uri.id}",
            )

        page_uris = [
            PageURI(root="test", type="test", id="page1", version=1),
            PageURI(root="test", type="test", id="page2", version=1),
            PageURI(root="test", type="test", id="page3", version=1),
        ]

        pages = await page_router.get_pages(page_uris)

        assert len(pages) == 3
        assert all(isinstance(page, SamplePage) for page in pages)
        assert pages[0].title == "Test page1"
        assert pages[1].title == "Test page2"
        assert pages[2].title == "Test page3"

    @pytest.mark.asyncio
    async def test_get_pages_empty_list(self, page_router: PageRouter) -> None:
        """Test bulk page retrieval with empty list."""
        pages = await page_router.get_pages([])
        assert pages == []

    @pytest.mark.asyncio
    async def test_get_pages_mixed_types(self, page_router: PageRouter) -> None:
        """Test bulk page retrieval with mixed page types."""

        @page_router.route("test")
        async def test_handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        @page_router.route("second")
        async def second_handler(page_uri: PageURI) -> SecondSamplePage:
            return SecondSamplePage(uri=page_uri, name="Second", data="Data")

        page_uris = [
            PageURI(root="test", type="test", id="page1", version=1),
            PageURI(root="test", type="second", id="page2", version=1),
        ]

        pages = await page_router.get_pages(page_uris)

        assert len(pages) == 2
        assert isinstance(pages[0], SamplePage)
        assert isinstance(pages[1], SecondSamplePage)

    @pytest.mark.asyncio
    async def test_get_pages_parallel_execution(self, page_router: PageRouter) -> None:
        """Test that get_pages executes requests in parallel."""
        call_times = []

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            import time

            call_times.append(time.time())
            await asyncio.sleep(0.1)  # Simulate async work
            return SamplePage(uri=page_uri, title="Test", content="Content")

        page_uris = [
            PageURI(root="test", type="test", id="page1", version=1),
            PageURI(root="test", type="test", id="page2", version=1),
        ]

        start_time = asyncio.get_event_loop().time()
        pages = await page_router.get_pages(page_uris)
        end_time = asyncio.get_event_loop().time()

        # Should complete in roughly 0.1 seconds (parallel) rather than 0.2 (sequential)
        assert len(pages) == 2
        assert end_time - start_time < 0.15  # Allow some margin for test timing


class TestPrivateMethods:
    """Test private methods of PageRouter."""

    @pytest.mark.asyncio
    async def test_get_from_cache_success(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test successful cache retrieval."""
        cached_page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Cached",
            content="From cache",
        )
        page_router_with_mock._page_cache.get.return_value = cached_page

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        result = await page_router_with_mock._get_from_cache(SamplePage, page_uri)

        assert result == cached_page

    @pytest.mark.asyncio
    async def test_get_from_cache_miss(self, page_router_with_mock: PageRouter) -> None:
        """Test cache miss returns None."""
        page_router_with_mock._page_cache.get.return_value = None

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        result = await page_router_with_mock._get_from_cache(SamplePage, page_uri)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_from_cache_error_handled(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test cache error is handled gracefully."""
        page_router_with_mock._page_cache.get.side_effect = Exception("Cache error")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        result = await page_router_with_mock._get_from_cache(SamplePage, page_uri)

        assert result is None

    @pytest.mark.asyncio
    async def test_call_handler_async(self, page_router: PageRouter) -> None:
        """Test calling async handler."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        page = await page_router._call_handler_async(handler, page_uri)

        assert isinstance(page, SamplePage)
        assert page.uri == page_uri

    @pytest.mark.asyncio
    async def test_store_in_cache_success(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test successful cache storage."""
        page_router_with_mock._page_cache.get.return_value = None  # Not already cached

        page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Test",
            content="Content",
        )
        page_uri = page.uri

        await page_router_with_mock._store_in_cache(page, page_uri)

        page_router_with_mock._page_cache.store.assert_called_once_with(page)

    @pytest.mark.asyncio
    async def test_store_in_cache_already_cached(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test cache storage when page is already cached."""
        existing_page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Existing",
            content="Existing content",
        )
        page_router_with_mock._page_cache.get.return_value = existing_page

        page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Test",
            content="Content",
        )
        page_uri = page.uri

        await page_router_with_mock._store_in_cache(page, page_uri)

        # Should not call store when already cached
        page_router_with_mock._page_cache.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_store_in_cache_error_handled(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test cache storage error is handled gracefully."""
        page_router_with_mock._page_cache.get.side_effect = Exception("Cache error")

        page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Test",
            content="Content",
        )
        page_uri = page.uri

        # Should not raise exception
        await page_router_with_mock._store_in_cache(page, page_uri)

    @pytest.mark.asyncio
    async def test_create_page_uri_cache_disabled(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page URI creation when cache is disabled."""
        page_router_with_mock._cache_enabled["test"] = False

        uri = await page_router_with_mock._create_page_uri(
            SamplePage, "test", "test", "page1"
        )

        assert uri.root == "test"
        assert uri.type == "test"
        assert uri.id == "page1"
        assert uri.version == 1

    @pytest.mark.asyncio
    async def test_create_page_uri_cache_enabled_no_existing(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page URI creation when cache is enabled but no existing versions."""
        page_router_with_mock._cache_enabled["test"] = True
        page_router_with_mock._page_cache.get_latest_version.return_value = None

        uri = await page_router_with_mock._create_page_uri(
            SamplePage, "test", "test", "page1"
        )

        assert uri.version == 1

    @pytest.mark.asyncio
    async def test_create_page_uri_cache_enabled_with_existing(
        self, page_router: PageRouter
    ) -> None:
        """Test page URI creation when cache has existing versions."""
        # Store a page with version=3 in the real cache
        page = SamplePage(
            uri=PageURI(root="test", type="test", id="page1", version=3),
            title="Test v3",
            content="Content v3",
        )
        await page_router._page_cache.store(page)

        uri = await page_router._create_page_uri(SamplePage, "test", "test", "page1")

        assert uri.version == 4

    @pytest.mark.asyncio
    async def test_create_page_uri_cache_error_handled(
        self, page_router_with_mock: PageRouter
    ) -> None:
        """Test page URI creation when cache access fails."""
        page_router_with_mock._cache_enabled["test"] = True
        page_router_with_mock._page_cache.get_latest_version.side_effect = Exception(
            "Cache error"
        )

        uri = await page_router_with_mock._create_page_uri(
            SamplePage, "test", "test", "page1"
        )

        # Should default to version 1 when cache access fails
        assert uri.version == 1

    def test_get_handler_return_type_valid(self, page_router: PageRouter) -> None:
        """Test getting handler return type for valid handler."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        return_type = PageRouter._get_handler_return_type(handler, "test")
        assert return_type == SamplePage

    def test_get_handler_return_type_awaitable(self, page_router: PageRouter) -> None:
        """Test getting handler return type for Awaitable annotation."""

        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        # Manually set the annotation to Awaitable[SamplePage]
        handler.__annotations__ = {"return": Awaitable[SamplePage]}

        return_type = PageRouter._get_handler_return_type(handler, "test")
        assert return_type == SamplePage

    def test_get_handler_return_type_union(self, page_router: PageRouter) -> None:
        """Test getting handler return type for Union annotation."""

        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(uri=page_uri, title="Test", content="Content")

        # Manually set the annotation to Union[SamplePage, None]
        handler.__annotations__ = {"return": Union[SamplePage, None]}

        return_type = PageRouter._get_handler_return_type(handler, "test")
        assert return_type == SamplePage

    def test_get_handler_return_type_no_annotation_error(
        self, page_router: PageRouter
    ) -> None:
        """Test error when handler has no return annotation."""

        def handler(page_uri: PageURI):
            pass

        with pytest.raises(RuntimeError, match="must have a return type annotation"):
            PageRouter._get_handler_return_type(handler, "test")

    def test_get_handler_return_type_string_annotation_error(
        self, page_router: PageRouter
    ) -> None:
        """Test error for string return type annotation."""
        # This is no longer an error: get_type_hints resolves string annotations if the class is available.

    def test_get_handler_return_type_invalid_type_error(
        self, page_router: PageRouter
    ) -> None:
        """Test error when handler has invalid return type."""

        def handler(page_uri: PageURI) -> str:
            pass

        with pytest.raises(RuntimeError, match="must be a Page subclass"):
            PageRouter._get_handler_return_type(handler, "test")


class TestComplexScenarios:
    """Test complex scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_multiple_versions_same_page(self, page_router: PageRouter) -> None:
        """Test handling multiple versions of the same page."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            return SamplePage(
                uri=page_uri, title=f"Test v{page_uri.version}", content="Content"
            )

        # Create pages with different versions
        page1 = await page_router.get_page(
            PageURI(root="test", type="test", id="page1", version=1)
        )
        page2 = await page_router.get_page(
            PageURI(root="test", type="test", id="page1", version=2)
        )

        assert page1.title == "Test v1"
        assert page2.title == "Test v2"
        assert page1.uri.version == 1
        assert page2.uri.version == 2

    @pytest.mark.asyncio
    async def test_concurrent_page_requests(self, page_router: PageRouter) -> None:
        """Test concurrent requests for the same page."""
        call_count = 0

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> CountingPage:
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Simulate async work
            return CountingPage(
                uri=page_uri, value=f"Value {call_count}", call_count=call_count
            )

        # Make concurrent requests for the same page
        page_uri = PageURI(root="test", type="test", id="page1", version=1)
        tasks = [page_router.get_page(page_uri) for _ in range(3)]
        pages = await asyncio.gather(*tasks)

        # All should be valid pages
        assert len(pages) == 3
        assert all(isinstance(page, CountingPage) for page in pages)

    @pytest.mark.asyncio
    async def test_error_in_handler_propagated(self, page_router: PageRouter) -> None:
        """Test that errors in handlers are propagated."""

        @page_router.route("test")
        async def handler(page_uri: PageURI) -> SamplePage:
            raise ValueError("Handler error")

        page_uri = PageURI(root="test", type="test", id="page1", version=1)

        with pytest.raises(ValueError, match="Handler error"):
            await page_router.get_page(page_uri)


class TestAllowStaleFunctionality:
    @pytest.mark.asyncio
    async def test_get_page_allow_stale(self, page_router: PageRouter):
        class StalePage(Page):
            value: int

        async def validator(page: StalePage) -> bool:
            return page.value > 0

        page_router._page_cache.register_validator(StalePage, validator)

        @page_router.route("stale")
        async def handler(page_uri: PageURI) -> StalePage:
            # Handler always returns value -999
            return StalePage(uri=page_uri, value=-999)

        page_uri = PageURI(root="test", type="stale", id="p1", version=1)
        # Store a page with value -1 (invalid)
        cached_page = StalePage(uri=page_uri, value=-1)
        await page_router._page_cache.store(cached_page)
        # With allow_stale=True, should get the cached invalid page (value -1)
        result = await page_router.get_page(page_uri, allow_stale=True)
        assert result.value == -1
        # With allow_stale=False, should get the handler's page (value -999)
        result = await page_router.get_page(page_uri, allow_stale=False)
        assert result.value == -999

    @pytest.mark.asyncio
    async def test_get_pages_allow_stale(self, page_router: PageRouter):
        class StalePage(Page):
            value: int

        async def validator(page: StalePage) -> bool:
            return page.value > 0

        page_router._page_cache.register_validator(StalePage, validator)

        @page_router.route("stale")
        async def handler(page_uri: PageURI) -> StalePage:
            return StalePage(uri=page_uri, value=-999)

        uris = [
            PageURI(root="test", type="stale", id=f"p{i}", version=1) for i in range(3)
        ]
        for uri in uris:
            await page_router._page_cache.store(StalePage(uri=uri, value=-1))
        # With allow_stale, all are returned from cache (value -1)
        results = await page_router.get_pages(uris, allow_stale=True)
        assert all(page.value == -1 for page in results)
        # With allow_stale=False, all are returned from handler (value -999)
        results = await page_router.get_pages(uris, allow_stale=False)
        assert all(page.value == -999 for page in results)


# Migrated tests from test_context.py
class TestPageHandlerRegistration:
    """Test page handler registration functionality."""

    @pytest.mark.asyncio
    async def test_register_handler_programmatically(
        self, page_router: PageRouter
    ) -> None:
        page_router.route("document")(document_page_handler)

    @pytest.mark.asyncio
    async def test_register_multiple_handlers(self, page_router: PageRouter) -> None:
        page_router.route("document")(document_page_handler)
        page_router.route("alternate")(alternate_page_handler)

    @pytest.mark.asyncio
    async def test_register_handler_duplicate_error(
        self, page_router: PageRouter
    ) -> None:
        page_router.route("document")(document_page_handler)
        with pytest.raises(RuntimeError, match="already registered"):
            page_router.route("document")(document_page_handler)


class TestGetPageExtended:
    """Test get_page functionality (extended from test_context.py)."""

    @pytest.mark.asyncio
    async def test_get_page_create_new(self, page_router: PageRouter) -> None:
        page_router.route("document")(document_page_handler)

        uri = PageURI(root="test", type="document", id="new_page", version=1)
        page = await page_router.get_page(uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page new_page"

    @pytest.mark.asyncio
    async def test_get_page_with_uri_from_reference(
        self, page_router: PageRouter
    ) -> None:
        page_router.route("document")(document_page_handler)

        reference = PageReference(
            uri=PageURI(root="test", type="document", id="ref_page", version=1)
        )
        page = await page_router.get_page(reference.uri)

        assert isinstance(page, DocumentPage)
        assert page.title == "Test Page ref_page"

    @pytest.mark.asyncio
    async def test_get_page_invalid_uri_error(self, page_router: PageRouter) -> None:
        with pytest.raises(ValueError):
            await page_router.get_page("invalid-uri-format")

    @pytest.mark.asyncio
    async def test_get_page_unregistered_type_error(
        self, page_router: PageRouter
    ) -> None:
        uri = PageURI(root="test", type="unregistered", id="123", version=1)
        with pytest.raises(
            RuntimeError, match="No handler registered for type: unregistered"
        ):
            await page_router.get_page(uri)


class TestVersionFunctionality:
    """Test version functionality in page router."""

    @pytest.mark.asyncio
    async def test_create_page_uri_defaults_to_version_1(
        self, page_router: PageRouter
    ) -> None:
        uri = await page_router.create_page_uri(TextPage, "text", "test123")
        assert uri.version == 1

    @pytest.mark.asyncio
    async def test_create_page_uri_explicit_version_overrides_default(
        self, page_router: PageRouter
    ) -> None:
        uri = await page_router.create_page_uri(TextPage, "text", "test123", version=5)
        assert uri.version == 5
        uri2 = await page_router.create_page_uri(
            TextPage, "text", "test123", version=None
        )
        assert uri2.version == 1
