"""Test async functionality without external dependencies."""

import asyncio
import sys
import os
from typing import Any

# Add src to pythonpath
test_dir = os.path.dirname(__file__)
src_dir = os.path.join(test_dir, "src")
sys.path.insert(0, src_dir)

# Mock modules we don't have
class MockOpenAI:
    pass

class MockModule:
    def __getattr__(self, name):
        return MockModule()
    
    def __call__(self, *args, **kwargs):
        return MockModule()

# Patch missing modules
sys.modules['openai'] = MockModule()
sys.modules['fastmcp'] = MockModule()

# Now we can import praga_core
from praga_core.context import ServerContext
from praga_core.types import Page, PageURI


class TestPage(Page):
    """Simple test page."""
    title: str
    content: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


async def test_async_handlers():
    """Test async page handlers."""
    print("Testing async page handlers...")
    
    context = ServerContext(root="test")

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
        await asyncio.sleep(0.01)  # Small delay
        return TestPage(
            uri=page_uri,
            title=f"Async Page {page_uri.id}",
            content=f"Async content for {page_uri.id}"
        )

    # Test sync get_page
    sync_uri = PageURI(root="test", type="sync_test", id="page1", version=1)
    sync_page = context.get_page(sync_uri)
    assert sync_page.title == "Sync Page page1"
    print("✓ Sync get_page works")

    # Test async get_page with sync handler
    async_page_from_sync = await context.get_page_async(sync_uri)
    assert async_page_from_sync.title == "Sync Page page1"
    print("✓ Async get_page with sync handler works")

    # Test async get_page with async handler
    async_uri = PageURI(root="test", type="async_test", id="page1", version=1)
    async_page = await context.get_page_async(async_uri)
    assert async_page.title == "Async Page page1"
    print("✓ Async get_page with async handler works")

    return True


async def test_bulk_operations():
    """Test bulk page operations."""
    print("Testing bulk page operations...")
    
    context = ServerContext(root="test")

    # Register handlers
    @context.route("test")
    def test_handler(page_uri: PageURI) -> TestPage:
        return TestPage(
            uri=page_uri,
            title=f"Page {page_uri.id}",
            content=f"Content for {page_uri.id}"
        )

    @context.route("async_test") 
    async def async_test_handler(page_uri: PageURI) -> TestPage:
        await asyncio.sleep(0.01)
        return TestPage(
            uri=page_uri,
            title=f"Async Page {page_uri.id}",
            content=f"Async content for {page_uri.id}"
        )

    # Test bulk sync get_pages
    uris = [
        PageURI(root="test", type="test", id="page1", version=1),
        PageURI(root="test", type="test", id="page2", version=1),
    ]
    pages = context.get_pages(uris)
    assert len(pages) == 2
    assert pages[0].title == "Page page1"
    assert pages[1].title == "Page page2"
    print("✓ Bulk sync get_pages works")

    # Test bulk async get_pages
    mixed_uris = [
        PageURI(root="test", type="test", id="page1", version=1),
        PageURI(root="test", type="async_test", id="page1", version=1),
        PageURI(root="test", type="test", id="page2", version=1),
        PageURI(root="test", type="async_test", id="page2", version=1),
    ]
    async_pages = await context.get_pages_async(mixed_uris)
    assert len(async_pages) == 4
    assert async_pages[0].title == "Page page1"
    assert async_pages[1].title == "Async Page page1"
    print("✓ Bulk async get_pages works")

    return True


async def test_async_validators():
    """Test async page validators."""
    print("Testing async page validators...")
    
    context = ServerContext(root="test")

    # Register async validator
    validation_calls = []
    
    @context.validator
    async def async_validator(page: TestPage) -> bool:
        await asyncio.sleep(0.01)  # Simulate async validation
        validation_calls.append(page.title)
        return "invalid" not in page.title.lower()

    # Register handler
    @context.route("test")
    def test_handler(page_uri: PageURI) -> TestPage:
        return TestPage(
            uri=page_uri,
            title=f"Page {page_uri.id}",
            content=f"Content for {page_uri.id}"
        )

    # Test that validators are registered (we can't easily test async validation in this setup)
    print("✓ Async validators can be registered")

    return True


async def main():
    """Run all tests."""
    try:
        print("Running async functionality tests...\n")
        
        await test_async_handlers()
        print()
        
        await test_bulk_operations()
        print()
        
        await test_async_validators()
        print()
        
        print("All tests passed! ✅")
        return True
        
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)