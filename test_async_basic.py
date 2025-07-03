#!/usr/bin/env python3
"""Basic test to verify async functionality works."""

import asyncio
import sys
import os

# Add src to path so we can import directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src/praga_core'))

# Import directly to avoid modules that need openai
from page_cache.core import PageCache
from page_router import PageRouter
from types import Page, PageURI
from typing import Any


class TestPage(Page):
    """Simple test page."""
    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class TestContext:
    """Minimal context for testing."""
    def __init__(self):
        self._page_cache = PageCache("sqlite:///:memory:")
        self._router = PageRouter(self._page_cache)
    
    def route(self, path: str, cache: bool = True):
        return self._router.route(path, cache)
    
    def get_page(self, page_uri):
        return self._router.get_page(page_uri)
        
    async def get_page_async(self, page_uri):
        return await self._router.get_page_async(page_uri)
        
    async def get_pages_async(self, page_uris):
        return await self._router.get_pages_async(page_uris)


async def main():
    """Test basic async functionality."""
    print("Creating test context...")
    context = TestContext()

    # Register sync handler
    @context.route("sync_test")
    def sync_handler(page_uri: PageURI) -> TestPage:
        return TestPage(
            uri=page_uri,
            title=f"Sync Page {page_uri.id}",
            content=f"Content for {page_uri.id}"
        )

    # Register async handler
    @context.route("async_test")
    async def async_handler(page_uri: PageURI) -> TestPage:
        # Simulate async work
        await asyncio.sleep(0.1)
        return TestPage(
            uri=page_uri,
            title=f"Async Page {page_uri.id}",
            content=f"Async content for {page_uri.id}"
        )

    # Test sync page retrieval
    print("Testing sync get_page...")
    sync_uri = PageURI(root="test", type="sync_test", id="page1", version=1)
    sync_page = context.get_page(sync_uri)
    print(f"Sync page title: {sync_page.title}")

    # Test async page retrieval with sync handler
    print("Testing async get_page with sync handler...")
    async_page_from_sync = await context.get_page_async(sync_uri)
    print(f"Async page from sync handler: {async_page_from_sync.title}")

    # Test async page retrieval with async handler
    print("Testing async get_page with async handler...")
    async_uri = PageURI(root="test", type="async_test", id="page1", version=1)
    async_page = await context.get_page_async(async_uri)
    print(f"Async page title: {async_page.title}")

    # Test bulk operations
    print("Testing bulk get_pages...")
    uris = [
        PageURI(root="test", type="sync_test", id="page1", version=1),
        PageURI(root="test", type="sync_test", id="page2", version=1),
        PageURI(root="test", type="async_test", id="page1", version=1),
        PageURI(root="test", type="async_test", id="page2", version=1),
    ]
    
    pages = await context.get_pages_async(uris)
    print(f"Retrieved {len(pages)} pages in bulk:")
    for page in pages:
        print(f"  - {page.title}")

    print("All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())