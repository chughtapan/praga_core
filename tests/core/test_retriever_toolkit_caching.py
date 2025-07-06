"""Tests for RetrieverToolkit caching functionality.

This module focuses on testing the caching mechanisms in RetrieverToolkit,
including cache hits/misses, TTL behavior, and cache invalidation.
"""

import time
from datetime import timedelta
from typing import Any, Dict, Sequence

import pytest

from .conftest import (
    MockRetrieverToolkit,
    SimpleTestPage,
    create_test_pages,
    create_timestamped_page,
)


class TestRetrieverToolkitCaching:
    """Test caching functionality of the RetrieverToolkit."""

    @pytest.mark.asyncio
    async def test_cache_basic_hit_and_miss(self) -> None:
        """Test basic caching behavior - cache hits and misses."""
        toolkit = MockRetrieverToolkit()

        async def get_docs() -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(1, f"call_{toolkit.call_count}")

        # Register with caching enabled
        toolkit.register_tool(get_docs, cache=True)

        # First call should execute function
        result1 = await toolkit.get_docs()
        assert toolkit.call_count == 1
        assert "call_1" in result1[0].title

        # Second call should use cache
        result2 = await toolkit.get_docs()
        assert toolkit.call_count == 1  # No additional call
        assert "call_1" in result2[0].title  # Same content

        # Results should be identical
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_cache_disabled_always_executes(self) -> None:
        """Test that disabled cache always executes the function."""
        toolkit = MockRetrieverToolkit()

        async def get_docs() -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(1, f"call_{toolkit.call_count}")

        # Register with caching disabled
        toolkit.register_tool(get_docs, cache=False)

        # Each call should execute the function
        result1 = await toolkit.get_docs()
        result2 = await toolkit.get_docs()

        assert toolkit.call_count == 2
        assert "call_1" in result1[0].title
        assert "call_2" in result2[0].title

    @pytest.mark.asyncio
    async def test_cache_with_different_arguments(self) -> None:
        """Test that cache distinguishes between different arguments."""
        toolkit = MockRetrieverToolkit()

        async def get_docs_with_arg(name: str) -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(1, f"{name}_{toolkit.call_count}")

        toolkit.register_tool(get_docs_with_arg, cache=True)

        # Different arguments should result in different cache entries
        result1 = await toolkit.get_docs_with_arg("arg1")
        result2 = await toolkit.get_docs_with_arg("arg2")
        result3 = await toolkit.get_docs_with_arg("arg1")  # Should use cache

        assert toolkit.call_count == 2  # Only two actual function calls
        assert "arg1_1" in result1[0].title
        assert "arg2_2" in result2[0].title
        assert "arg1_1" in result3[0].title  # Cached result

    @pytest.mark.asyncio
    async def test_cache_with_complex_arguments(self) -> None:
        """Test caching with complex argument combinations."""
        toolkit = MockRetrieverToolkit()

        async def complex_tool(
            query: str, limit: int = 5, flag: bool = False
        ) -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(limit, f"{query}_{toolkit.call_count}")

        toolkit.register_tool(complex_tool, cache=True)

        # Same args should hit cache
        result1 = await toolkit.complex_tool("test", limit=3, flag=True)
        result2 = await toolkit.complex_tool("test", limit=3, flag=True)
        assert toolkit.call_count == 1
        assert result1 == result2

        # Different args should miss cache
        result3 = await toolkit.complex_tool("test", limit=3, flag=False)
        assert toolkit.call_count == 2
        assert result1 != result3

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self) -> None:
        """Test that cache entries expire after TTL."""
        toolkit = MockRetrieverToolkit()

        async def get_docs() -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(1, f"call_{toolkit.call_count}")

        # Register with very short TTL
        toolkit.register_tool(get_docs, cache=True, ttl=timedelta(milliseconds=100))
        # First call
        result1 = await toolkit.get_docs()
        assert toolkit.call_count == 1

        # Second call immediately - should use cache
        result2 = await toolkit.get_docs()
        assert toolkit.call_count == 1
        assert result1 == result2

        # Wait for TTL to expire
        time.sleep(0.15)  # 150ms > 100ms TTL

        # Third call should execute function again
        result3 = await toolkit.get_docs()
        assert toolkit.call_count == 2
        assert "call_2" in result3[0].title

    @pytest.mark.asyncio
    async def test_cache_ttl_different_durations(self) -> None:
        """Test different TTL durations work correctly."""
        toolkit = MockRetrieverToolkit()

        async def get_short_ttl() -> Sequence[SimpleTestPage]:
            return create_timestamped_page("short")

        async def get_long_ttl() -> Sequence[SimpleTestPage]:
            return create_timestamped_page("long")

        toolkit.register_tool(get_short_ttl, cache=True, ttl=timedelta(milliseconds=50))
        toolkit.register_tool(get_long_ttl, cache=True, ttl=timedelta(seconds=10))

        # Get initial results
        short_result1 = await toolkit.get_short_ttl()
        long_result1 = await toolkit.get_long_ttl()

        # Wait for short TTL to expire but not long TTL
        time.sleep(0.08)  # 80ms

        short_result2 = await toolkit.get_short_ttl()  # Should be different (new call)
        long_result2 = await toolkit.get_long_ttl()  # Should be same (cached)

        assert short_result1 != short_result2  # Different timestamps
        assert long_result1 == long_result2  # Same cached result

    @pytest.mark.asyncio
    async def test_cache_invalidator(self) -> None:
        """Test custom cache invalidation logic."""
        toolkit = MockRetrieverToolkit()

        async def get_docs() -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(1, f"call_{toolkit.call_count}")

        # Custom invalidator that always invalidates
        def always_invalidate(cache_key: str, cached_value: Dict[str, Any]) -> bool:
            return False  # Always invalidate

        toolkit.register_tool(get_docs, cache=True, invalidator=always_invalidate)

        # Each call should execute the function due to invalidation
        result1 = await toolkit.get_docs()
        result2 = await toolkit.get_docs()

        assert toolkit.call_count == 2
        assert "call_1" in result1[0].title
        assert "call_2" in result2[0].title

    @pytest.mark.asyncio
    async def test_cache_key_generation(self) -> None:
        """Test that cache keys are generated consistently."""
        toolkit = MockRetrieverToolkit()

        async def get_docs(arg1: str, arg2: int = 10) -> Sequence[SimpleTestPage]:
            return create_test_pages(1)

        # Test cache key generation directly
        key1 = toolkit.make_cache_key(get_docs, "hello", arg2=20)
        key2 = toolkit.make_cache_key(get_docs, "hello", arg2=20)
        key3 = toolkit.make_cache_key(get_docs, "hello", arg2=30)

        assert key1 == key2  # Same args should produce same key
        assert key1 != key3  # Different args should produce different key

    @pytest.mark.asyncio
    async def test_cache_with_invoke_tool(self) -> None:
        """Test that caching works with invoke_tool method."""
        toolkit = MockRetrieverToolkit()

        async def cached_tool(query: str) -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return create_test_pages(1, f"{query}_{toolkit.call_count}")

        toolkit.register_tool(cached_tool, cache=True)

        # First invoke should execute function
        result1 = await toolkit.invoke_tool("cached_tool", "test")
        assert toolkit.call_count == 1

        # Second invoke should use cache
        result2 = await toolkit.invoke_tool("cached_tool", "test")
        assert toolkit.call_count == 1
        assert result1 == result2


class TestCachingEdgeCases:
    """Test edge cases and error conditions in caching."""

    @pytest.mark.asyncio
    async def test_cache_with_none_return(self) -> None:
        """Test caching behavior when function returns None or empty."""
        toolkit = MockRetrieverToolkit()

        async def empty_tool() -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            return []

        toolkit.register_tool(empty_tool, cache=True)

        # Empty results should still be cached
        result1 = await toolkit.empty_tool()
        result2 = await toolkit.empty_tool()

        assert toolkit.call_count == 1  # Only called once
        assert result1 == result2 == []

    @pytest.mark.asyncio
    async def test_cache_with_exceptions(self) -> None:
        """Test that exceptions are not cached."""
        toolkit = MockRetrieverToolkit()

        async def failing_tool(should_fail: bool) -> Sequence[SimpleTestPage]:
            toolkit.increment_call_count()
            if should_fail:
                raise ValueError("Tool failed")
            return create_test_pages(1, f"success_{toolkit.call_count}")

        toolkit.register_tool(failing_tool, cache=True)

        # First call fails - should not be cached
        with pytest.raises(ValueError):
            await toolkit.failing_tool(True)
        assert toolkit.call_count == 1

        # Second call fails - should execute again (not cached)
        with pytest.raises(ValueError):
            await toolkit.failing_tool(True)
        assert toolkit.call_count == 2

        # Successful call should work and be cached
        result1 = await toolkit.failing_tool(False)
        result2 = await toolkit.failing_tool(False)
        assert toolkit.call_count == 3  # One more call for success
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_cache_memory_behavior(self) -> None:
        """Test that cache doesn't hold onto objects unnecessarily."""
        toolkit = MockRetrieverToolkit()

        async def get_large_docs(size: int) -> Sequence[SimpleTestPage]:
            return create_test_pages(size, "large")

        toolkit.register_tool(get_large_docs, cache=True)

        # Create and cache a large result
        large_result = await toolkit.get_large_docs(100)
        small_result = await toolkit.get_large_docs(2)

        # Verify both are cached (different args)
        large_result2 = await toolkit.get_large_docs(100)
        small_result2 = await toolkit.get_large_docs(2)

        assert large_result == large_result2
        assert small_result == small_result2
        assert len(large_result) == 100
        assert len(small_result) == 2
