"""Tests for async functionality in ServerContext and related components.

This module tests the async capabilities including:
- Async page handlers
- Async page validators  
- Bulk page operations
- Mixed sync/async execution
"""

import asyncio
from typing import Any

import pytest

from praga_core.context import ServerContext
from praga_core.types import Page, PageURI


class AsyncTestPage(Page):
    """Test page for async testing."""
    
    title: str
    content: str
    
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class ValidatedPage(Page):
    """Test page for validation testing."""
    
    title: str
    status: str
    
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


# Async handler functions for testing
async def async_document_handler(page_uri: PageURI) -> AsyncTestPage:
    """Async test handler for AsyncTestPage."""
    # Simulate async I/O operation
    await asyncio.sleep(0.01)
    return AsyncTestPage(
        uri=page_uri,
        title=f"Async Test Page {page_uri.id}",
        content=f"Async content for page {page_uri.id}",
    )


def sync_document_handler(page_uri: PageURI) -> AsyncTestPage:
    """Sync test handler for AsyncTestPage."""
    return AsyncTestPage(
        uri=page_uri,
        title=f"Sync Test Page {page_uri.id}",
        content=f"Sync content for page {page_uri.id}",
    )


@pytest.fixture
def context() -> ServerContext:
    """Provide a fresh ServerContext for each test."""
    return ServerContext(root="test")


class TestAsyncHandlers:
    """Test async page handler functionality."""

    @pytest.mark.asyncio
    async def test_async_handler_registration_and_execution(self, context: ServerContext) -> None:
        """Test registering and executing async handlers."""
        context.route("async_test")(async_document_handler)
        
        uri = PageURI(root="test", type="async_test", id="page1", version=1)
        page = await context.get_page_async(uri)
        
        assert isinstance(page, AsyncTestPage)
        assert page.title == "Async Test Page page1"
        assert "Async content" in page.content

    @pytest.mark.asyncio
    async def test_sync_handler_in_async_context(self, context: ServerContext) -> None:
        """Test executing sync handlers from async context."""
        context.route("sync_test")(sync_document_handler)
        
        uri = PageURI(root="test", type="sync_test", id="page1", version=1)
        page = await context.get_page_async(uri)
        
        assert isinstance(page, AsyncTestPage)
        assert page.title == "Sync Test Page page1"
        assert "Sync content" in page.content

    def test_sync_handler_in_sync_context(self, context: ServerContext) -> None:
        """Test that sync handlers still work in sync context."""
        context.route("sync_test")(sync_document_handler)
        
        uri = PageURI(root="test", type="sync_test", id="page1", version=1)
        page = context.get_page(uri)
        
        assert isinstance(page, AsyncTestPage)
        assert page.title == "Sync Test Page page1"

    @pytest.mark.asyncio
    async def test_mixed_handlers_types(self, context: ServerContext) -> None:
        """Test mixing sync and async handlers in same context."""
        context.route("sync_test")(sync_document_handler)
        context.route("async_test")(async_document_handler)
        
        sync_uri = PageURI(root="test", type="sync_test", id="page1", version=1)
        async_uri = PageURI(root="test", type="async_test", id="page1", version=1)
        
        sync_page = await context.get_page_async(sync_uri)
        async_page = await context.get_page_async(async_uri)
        
        assert sync_page.title == "Sync Test Page page1"
        assert async_page.title == "Async Test Page page1"


class TestBulkOperations:
    """Test bulk page operations."""

    def test_bulk_sync_get_pages(self, context: ServerContext) -> None:
        """Test bulk synchronous page retrieval."""
        context.route("test")(sync_document_handler)
        
        uris = [
            PageURI(root="test", type="test", id="page1", version=1),
            PageURI(root="test", type="test", id="page2", version=1),
            PageURI(root="test", type="test", id="page3", version=1),
        ]
        
        pages = context.get_pages(uris)
        
        assert len(pages) == 3
        assert all(isinstance(page, AsyncTestPage) for page in pages)
        assert pages[0].title == "Sync Test Page page1"
        assert pages[1].title == "Sync Test Page page2"
        assert pages[2].title == "Sync Test Page page3"

    @pytest.mark.asyncio
    async def test_bulk_async_get_pages(self, context: ServerContext) -> None:
        """Test bulk asynchronous page retrieval."""
        context.route("async_test")(async_document_handler)
        
        uris = [
            PageURI(root="test", type="async_test", id="page1", version=1),
            PageURI(root="test", type="async_test", id="page2", version=1),
            PageURI(root="test", type="async_test", id="page3", version=1),
        ]
        
        # Time the async bulk operation
        import time
        start_time = time.time()
        pages = await context.get_pages_async(uris)
        end_time = time.time()
        
        # Should complete faster than sequential execution due to parallelism
        # (3 pages * 0.01s each should be ~0.01s with parallel execution vs ~0.03s sequential)
        assert (end_time - start_time) < 0.025  # Allow some overhead
        
        assert len(pages) == 3
        assert all(isinstance(page, AsyncTestPage) for page in pages)
        assert pages[0].title == "Async Test Page page1"
        assert pages[1].title == "Async Test Page page2"
        assert pages[2].title == "Async Test Page page3"

    @pytest.mark.asyncio
    async def test_bulk_mixed_handler_types(self, context: ServerContext) -> None:
        """Test bulk operations with mixed sync and async handlers."""
        context.route("sync_test")(sync_document_handler)
        context.route("async_test")(async_document_handler)
        
        uris = [
            PageURI(root="test", type="sync_test", id="page1", version=1),
            PageURI(root="test", type="async_test", id="page2", version=1),
            PageURI(root="test", type="sync_test", id="page3", version=1),
            PageURI(root="test", type="async_test", id="page4", version=1),
        ]
        
        pages = await context.get_pages_async(uris)
        
        assert len(pages) == 4
        assert pages[0].title == "Sync Test Page page1"
        assert pages[1].title == "Async Test Page page2"
        assert pages[2].title == "Sync Test Page page3"
        assert pages[3].title == "Async Test Page page4"

    @pytest.mark.asyncio
    async def test_bulk_with_string_uris(self, context: ServerContext) -> None:
        """Test bulk operations accept string URIs."""
        context.route("test")(sync_document_handler)
        
        uris = [
            "test/test:page1@1",
            "test/test:page2@1",
        ]
        
        pages = await context.get_pages_async(uris)
        
        assert len(pages) == 2
        assert pages[0].title == "Sync Test Page page1"
        assert pages[1].title == "Sync Test Page page2"


class TestAsyncValidators:
    """Test async validator functionality."""

    @pytest.mark.asyncio
    async def test_async_validator_registration(self, context: ServerContext) -> None:
        """Test that async validators can be registered."""
        validation_calls = []
        
        @context.validator
        async def async_validator(page: ValidatedPage) -> bool:
            await asyncio.sleep(0.01)  # Simulate async validation
            validation_calls.append(page.title)
            return page.status == "valid"
        
        # Test that validator was registered (we test actual validation in PageValidator tests)
        assert context._page_cache._validator.has_validator(ValidatedPage)

    def test_sync_validator_still_works(self, context: ServerContext) -> None:
        """Test that sync validators still work."""
        validation_calls = []
        
        @context.validator
        def sync_validator(page: ValidatedPage) -> bool:
            validation_calls.append(page.title)
            return page.status == "valid"
        
        # Test that validator was registered
        assert context._page_cache._validator.has_validator(ValidatedPage)


class TestBackwardsCompatibility:
    """Test that async changes don't break existing functionality."""

    def test_existing_sync_handlers_unchanged(self, context: ServerContext) -> None:
        """Test that existing sync handler patterns still work exactly as before."""
        @context.route("document")
        def document_handler(page_uri: PageURI) -> AsyncTestPage:
            return AsyncTestPage(
                uri=page_uri,
                title=f"Document {page_uri.id}",
                content=f"Content for {page_uri.id}",
            )

        uri = PageURI(root="test", type="document", id="test_page", version=1)
        page = context.get_page(uri)

        assert isinstance(page, AsyncTestPage)
        assert page.title == "Document test_page"

    def test_existing_validator_patterns_unchanged(self, context: ServerContext) -> None:
        """Test that existing validator patterns still work."""
        @context.validator
        def document_validator(page: ValidatedPage) -> bool:
            return len(page.title) > 0

        # Should register without errors
        assert context._page_cache._validator.has_validator(ValidatedPage)


class TestErrorHandling:
    """Test error handling in async contexts."""

    @pytest.mark.asyncio
    async def test_async_handler_error_propagation(self, context: ServerContext) -> None:
        """Test that errors in async handlers are properly propagated."""
        @context.route("error_test")
        async def error_handler(page_uri: PageURI) -> AsyncTestPage:
            await asyncio.sleep(0.01)
            raise ValueError("Test error from async handler")

        uri = PageURI(root="test", type="error_test", id="page1", version=1)
        
        with pytest.raises(ValueError, match="Test error from async handler"):
            await context.get_page_async(uri)

    @pytest.mark.asyncio
    async def test_sync_handler_error_in_async_context(self, context: ServerContext) -> None:
        """Test that errors in sync handlers called from async context are propagated."""
        @context.route("sync_error_test")
        def sync_error_handler(page_uri: PageURI) -> AsyncTestPage:
            raise RuntimeError("Test error from sync handler")

        uri = PageURI(root="test", type="sync_error_test", id="page1", version=1)
        
        with pytest.raises(RuntimeError, match="Test error from sync handler"):
            await context.get_page_async(uri)

    @pytest.mark.asyncio
    async def test_bulk_operation_partial_failure(self, context: ServerContext) -> None:
        """Test that bulk operations handle partial failures appropriately."""
        context.route("good")(sync_document_handler)
        
        @context.route("bad")
        async def bad_handler(page_uri: PageURI) -> AsyncTestPage:
            await asyncio.sleep(0.01)
            raise ValueError("Handler failure")

        uris = [
            PageURI(root="test", type="good", id="page1", version=1),
            PageURI(root="test", type="bad", id="page2", version=1),
        ]
        
        # The gather operation should propagate the first exception
        with pytest.raises(ValueError, match="Handler failure"):
            await context.get_pages_async(uris)