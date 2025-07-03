"""Tests for global context management."""

import pytest

from praga_core import (
    ContextMixin,
    ServerContext,
    clear_global_context,
    get_global_context,
    set_global_context,
)
from praga_core.types import Page, PageURI


class TestPage(Page):
    """Test page for global context tests."""

    title: str
    content: str


class MockService(ContextMixin):
    """Test service that uses ContextMixin."""

    def create_test_page(self, page_id: str) -> TestPage:
        """Create a test page using global context."""
        uri = self.context.create_page_uri(TestPage, "test", page_id)
        return TestPage(uri=uri, title=f"Test {page_id}", content="Test content")

    def get_page_from_context(self, uri: str) -> Page:
        """Get a page using global context."""
        return self.context.get_page(uri)


def test_global_context_basic():
    """Test basic global context functionality."""
    # Clear any existing context
    clear_global_context()

    # No context should raise error
    with pytest.raises(RuntimeError, match="Global context not set"):
        get_global_context()

    # Set context
    context = ServerContext(root="test")
    set_global_context(context)

    # Should be able to retrieve it
    retrieved = get_global_context()
    assert retrieved is context
    assert retrieved.root == "test"

    # Clear for cleanup
    clear_global_context()


def test_context_mixin():
    """Test ContextMixin functionality."""
    clear_global_context()

    # Create service before context - should fail
    service = MockService()
    with pytest.raises(RuntimeError, match="Global context not set"):
        service.context

    # Set up context
    context = ServerContext(root="test")
    set_global_context(context)

    # Register handler
    @context.route("test")
    def handle_test_page(page_uri: PageURI) -> TestPage:
        return TestPage(
            uri=page_uri, title=f"Test {page_uri.id}", content="Test content"
        )

    # Now service should work
    assert service.context is context

    # Service can create pages
    page = service.create_test_page("123")
    assert page.title == "Test 123"
    assert page.uri.id == "123"

    # Service can get pages
    retrieved_page = service.get_page_from_context(str(page.uri))
    assert retrieved_page.title == "Test 123"

    clear_global_context()


def test_manual_context_setup():
    """Test manual context setup without PragaApp."""
    clear_global_context()

    # Create and set context manually
    context = ServerContext(root="manual")
    set_global_context(context)

    # Should be able to access it
    retrieved_context = get_global_context()
    assert retrieved_context is context
    assert retrieved_context.root == "manual"

    # Can register handlers manually
    @context.route("mytype")
    def handle_my_type(page_uri: PageURI) -> TestPage:
        return TestPage(uri=page_uri, title=f"My {page_uri.id}", content="My content")

    # Handler should be registered
    assert "mytype" in context._router._handlers

    # Can use services with the context
    service = MockService()
    # Service should be able to access the global context
    assert service.context is context

    clear_global_context()


def test_context_set_twice_error():
    """Test error when setting global context twice."""
    clear_global_context()

    # Set up initial context
    initial_context = ServerContext(root="initial")
    set_global_context(initial_context)

    # Try to set another context
    new_context = ServerContext(root="new")
    with pytest.raises(RuntimeError, match="Global context is already set"):
        set_global_context(new_context)

    clear_global_context()


def test_multiple_services_same_context():
    """Test multiple services using the same global context."""
    clear_global_context()

    # Set up context and handlers manually
    context = ServerContext(root="shared")
    set_global_context(context)

    # Register handlers for both types
    @context.route("shared")
    def handle_shared(page_uri: PageURI) -> TestPage:
        return TestPage(
            uri=page_uri, title=f"Shared {page_uri.id}", content="Shared content"
        )

    @context.route("test")
    def handle_test(page_uri: PageURI) -> TestPage:
        return TestPage(
            uri=page_uri, title=f"Test {page_uri.id}", content="Test content"
        )

    # Create multiple services
    service1 = MockService()
    service2 = MockService()

    # Both should access same context
    assert service1.context is service2.context
    assert service1.context is context

    # Both can create pages
    page1 = service1.create_test_page("from_service1")
    page2 = service2.create_test_page("from_service2")

    # Both should be accessible from either service
    retrieved1 = service2.get_page_from_context(str(page1.uri))
    retrieved2 = service1.get_page_from_context(str(page2.uri))

    assert retrieved1.title == "Test from_service1"
    assert retrieved2.title == "Test from_service2"

    clear_global_context()


def test_error_handling():
    """Test error handling in global context."""
    clear_global_context()

    # Setting context twice should fail
    context1 = ServerContext(root="first")
    context2 = ServerContext(root="second")

    set_global_context(context1)

    with pytest.raises(RuntimeError, match="Global context is already set"):
        set_global_context(context2)

    clear_global_context()
