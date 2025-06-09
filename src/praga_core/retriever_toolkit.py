"""
praga/retriever_toolkit.py
──────────────────────────
A **beginner‑friendly reference implementation** of the RetrieverToolkit.

 • Only the Python standard‑library is used        (no pydantic, no fancy hashes)
 • Each helper is broken into 5–15 line functions  (easy to read / step through)
 • Generous comments explain *why* every step exists.
"""

from __future__ import annotations

import json
from abc import ABC
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from hashlib import md5  # small but good‑enough hash
from typing import Any, Callable, Dict, List, Protocol, Tuple

from .types import Document, FunctionInvocation


class CacheInvalidator(Protocol):
    """Return True if a cached value is *still* valid."""

    def __call__(self, key: str, value: Any) -> bool: ...


def _create_method_stub(fn: Callable) -> Callable:
    """
    Create a method stub that preserves the original function's signature.

    This stub is added to the class at decorator time to make the method
    visible to static type checkers like mypy. At runtime, the actual
    wrapped method (with caching, pagination, etc.) replaces this stub.
    """

    def method_stub(self, *args, **kwargs):
        # This will be replaced at runtime by the actual wrapped function
        return fn(*args, **kwargs)

    method_stub.__name__ = fn.__name__
    method_stub.__doc__ = fn.__doc__
    method_stub.__annotations__ = fn.__annotations__
    return method_stub


# ╔══════════════════════════════════════════════════════════╗
# ║                    RetrieverToolkit                      ║
# ╚══════════════════════════════════════════════════════════╝
class RetrieverToolkit(ABC):
    """
    A toolbox that holds **retriever functions** plus:
        • A per‑instance in‑memory cache
        • Optional pagination & cache wrappers
        • A context manager for query‑level logging
        • A speculation hook (override in subclasses)
    """

    # Stash for decorator‑based (stateless) tools – stored at *class* level
    _PENDING_TOOLS = "_praga_pending_tools"

    # ─────────────────────────────────────────────────────────
    #  Constructor
    # ─────────────────────────────────────────────────────────
    def __init__(self) -> None:
        # Cache maps <key> -> (<value>, <timestamp>)
        self._cache: Dict[str, Tuple[Any, datetime]] = {}

        # Tool registry maps <public_name> -> <callable>
        self._tools: Dict[str, Callable] = {}

        # Register any functions that were tagged with @RetrieverToolkit.tool
        self._register_pending_stateless_tools()

    # ========================================================
    # ================  Public helper methods  ================
    # ========================================================
    # These are the pieces most users will touch or override.
    # --------------------------------------------------------

    def make_cache_key(self, fn: Callable, *args, **kwargs) -> str:
        """
        A stable key made of:
        1) the function's *fully qualified* name
        2) the positional & keyword arguments (JSON‑serialised)

        md5 is simple, available everywhere, and fine for cache keys.
        """
        blob = json.dumps(
            [fn.__qualname__, args, kwargs],
            default=str,  # fall back to str() for non‑JSON types
            sort_keys=True,  # ensures the same kwargs order every time
        )
        return md5(blob.encode()).hexdigest()

    @contextmanager
    def logging_context(self, query: str):
        """
        Gives the agent a harmless place to attach per‑query logs.
        The base class does *nothing* – advanced users can override.
        """
        query_id = self.make_cache_key(lambda x: x, query)
        try:
            yield query_id
        finally:
            pass  # plug in your DB / stdout / OpenTelemetry here

    # Pure‑python token guess: 1.3 × word count  —— good enough
    @staticmethod
    def estimate_tokens(text: str) -> int:
        return int(len(text.split()) * 1.3)

    # ---------------- speculation ---------------------------
    # Override this for BM25 / embeddings etc.
    def speculate(
        self, query: str, *, top_k: int = 10
    ) -> List[Tuple[FunctionInvocation, List[Document]]]:
        return []  # no‑op default

    # ========================================================
    # ===============  Wrapping utilities  ===================
    # ========================================================
    # Keep each wrapper short so it’s easy to follow.

    # ---- caching ------------------------------------------
    def _wrap_with_cache(
        self,
        fn: Callable,
        *,
        invalidator: CacheInvalidator | None,
        ttl: timedelta | None,
    ) -> Callable:
        """Return a new function that consults & updates self._cache."""

        @wraps(fn)
        def cached_fn(*args, **kwargs):
            key = self.make_cache_key(fn, *args, **kwargs)

            if key in self._cache:
                value, timestamp = self._cache[key]
                is_fresh = True

                if ttl and datetime.utcnow() - timestamp > ttl:
                    is_fresh = False
                if invalidator and not invalidator(key, value):
                    is_fresh = False

                if is_fresh:
                    return value

            # Cache miss or stale
            value = fn(*args, **kwargs)
            self._cache[key] = (value, datetime.utcnow())
            return value

        return cached_fn

    # ---- pagination ---------------------------------------
    def _wrap_with_pagination(
        self, fn: Callable, *, max_docs: int, max_tokens: int
    ) -> Callable:
        """
        Turns a *flat* retriever (List[Document]) into one that accepts
        `page=N` and returns a dict with docs + metadata.
        """

        @wraps(fn)
        def paginated_fn(*args, page: int = 0, **kwargs):
            full_docs: List[Document] = fn(*args, **kwargs)

            # Step 1 – slice by document count
            doc_start = page * max_docs
            doc_end = doc_start + max_docs
            docs_slice = full_docs[doc_start:doc_end]

            # Step 2 – respect token budget
            result_docs: List[Document] = []
            running_tokens = 0
            for doc in docs_slice:
                metadata = doc.metadata or {}
                running_tokens += metadata.get("token_count", 0)
                if running_tokens > max_tokens:
                    break
                result_docs.append(doc)

            return {
                "docs": result_docs,
                "page": page,
                "has_next": doc_end < len(full_docs),
                "token_est": running_tokens,
            }

        return paginated_fn

    # ========================================================
    # ================  Tool registration  ===================
    # ========================================================
    def _register_tool(
        self,
        *,
        method: Callable,
        name: str,
        cache: bool = False,
        ttl: timedelta | None = None,
        invalidator: CacheInvalidator | None = None,
        paginate: bool = False,
        max_docs: int = 20,
        max_tokens: int = 2_048,
    ):
        """
        Common entry point used from __init__.

        1) Wrap method with cache and/or pagination.
        2) Add to `. _tools` (visible to the agent).
        3) Replace self.<name> so you can still call it directly.
        """
        wrapped = method

        if cache:
            wrapped = self._wrap_with_cache(
                wrapped,
                invalidator=invalidator,
                ttl=ttl,
            )

        if paginate:
            wrapped = self._wrap_with_pagination(
                wrapped,
                max_docs=max_docs,
                max_tokens=max_tokens,
            )

        self._tools[name] = wrapped
        setattr(self, name, wrapped)  # keeps instance attribute useful

    def __getattr__(self, name: str) -> Callable[..., Any]:
        """
        Enable dynamic attribute access for registered tools.
        This allows mypy to understand that dynamically registered methods exist.
        """
        if name in self._tools:
            return self._tools[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    # ========================================================
    # ==========  Stateless‑tool decorator support  ==========
    # ========================================================
    @classmethod
    def tool(cls, **cfg):
        """
        Thin decorator for functions that **do not** use `self`.
        Example:
            @RetrieverToolkit.tool(cache=False)
            def utc_time(): ...
        """

        def marker(fn: Callable):
            bucket = getattr(cls, cls._PENDING_TOOLS, [])
            bucket.append((fn, cfg))
            setattr(cls, cls._PENDING_TOOLS, bucket)

            # Add a method stub to the class for type checking
            # This allows mypy to see the method during static analysis
            if not hasattr(cls, fn.__name__):
                setattr(cls, fn.__name__, _create_method_stub(fn))

            return fn

        return marker

    # Gather and register any decorator‑tagged functions
    def _register_pending_stateless_tools(self):
        for fn, cfg in getattr(self.__class__, self._PENDING_TOOLS, []):
            self._register_tool(
                method=fn,
                name=fn.__name__,
                cache=cfg.get("cache", False),
                ttl=cfg.get("ttl"),
                invalidator=cfg.get("invalidator"),
                paginate=cfg.get("paginate", False),
                max_docs=cfg.get("max_docs", 20),
                max_tokens=cfg.get("max_tokens", 2048),
            )
