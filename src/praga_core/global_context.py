"""Global context management for Praga Core.

This module provides global context access patterns similar to Flask's application context
or FastAPI's dependency injection, allowing services and other components to access
the ServerContext without explicit dependency injection.
"""

from __future__ import annotations

from typing import Any, Optional

# Import only what we need to avoid circular dependencies
from .context import ServerContext
from .page_cache import PageCache
from .service import Service

# Global context storage
_global_context: Optional[ServerContext] = None


def set_global_context(context: ServerContext) -> None:
    """Set the global ServerContext instance.

    Args:
        context: ServerContext instance to set as global

    Raises:
        RuntimeError: If global context is already set
    """
    global _global_context
    if _global_context is not None:
        raise RuntimeError(
            "Global context is already set. Create a new app instance instead."
        )
    _global_context = context


def get_global_context() -> ServerContext:
    """Get the global ServerContext instance.

    Returns:
        The global ServerContext instance

    Raises:
        RuntimeError: If global context is not set
    """
    if _global_context is None:
        raise RuntimeError(
            "Global context not set. Create a PragaApp instance or call set_global_context() first."
        )
    return _global_context


def clear_global_context() -> None:
    """Clear the global context. Useful for testing."""
    global _global_context
    _global_context = None


def has_global_context() -> bool:
    """Check if global context is set."""
    return _global_context is not None


class ContextMixin:
    """Mixin class that provides access to the global ServerContext with auto-registration.

    Classes that inherit from this mixin can access the global context
    via the `context` property without needing explicit dependency injection.

    Example:
        class MyService(ContextMixin):
            def do_something(self):
                page = self.context.get_page("some://uri")
                return page
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @property
    def context(self) -> ServerContext:
        """Access the global ServerContext instance.

        Returns:
            The global ServerContext instance

        Raises:
            RuntimeError: If global context is not set
        """
        return get_global_context()


class ServiceContext(Service, ContextMixin):
    """Convenience class that combines Service and ContextMixin with auto-registration."""

    def __init__(self, api_client: Any = None, *args: Any, **kwargs: Any) -> None:
        self.api_client = api_client
        super().__init__(*args, **kwargs)
        self.context.register_service(self.name, self)

    @property
    def page_cache(self) -> PageCache:
        """Access the context's PageCache directly."""
        return self.context.page_cache
