from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from hashlib import md5
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Sequence,
    Tuple,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from .types import Document, PageMetadata, PaginatedResponse


@dataclass
class FunctionInvocation:
    tool_name: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]

    def serialise(self) -> str:
        payload = {
            "tool": self.tool_name,
            "args": self.args,
            "kwargs": tuple(sorted(self.kwargs.items())),
        }
        return json.dumps(payload, sort_keys=True, default=str)


ToolReturnType = Union[Sequence[Document], PaginatedResponse]
ToolFunction = Callable[..., ToolReturnType]
DocumentSequenceFunction = Callable[..., Sequence[Document]]
PaginatedFunction = Callable[..., PaginatedResponse]
CacheInvalidator = Callable[[str, Dict[str, Any]], bool]


class RetrieverToolkitMeta(abc.ABC):
    """Base class that handles all the internal mechanics for retriever toolkits."""

    # Stash for decorator‑based (stateless) tools – stored at *class* level
    _PENDING_TOOLS = "_praga_pending_tools"

    def __init__(self) -> None:
        # Cache maps <key> -> (<value>, <timestamp>)
        self._cache: Dict[str, Tuple[Any, datetime]] = {}

        # Tool registry maps <public_name> -> <callable>
        self._tools: Dict[str, ToolFunction] = {}

        # Register any functions that were tagged with @RetrieverToolkit.tool
        self._register_pending_stateless_tools()

    # ========================================================
    # ================  Internal Tool Management  ===========
    # ========================================================

    def register_tool(
        self,
        method: ToolFunction,
        name: str,
        cache: bool = False,
        ttl: timedelta | None = None,
        invalidator: CacheInvalidator | None = None,
        paginate: bool = False,
        max_docs: int = 20,
        max_tokens: int = 2_048,
    ):
        """
        Register a tool with the toolkit.

        Args:
            method: The tool function to register.
            name: The name of the tool.
            cache: Whether to cache the tool.
            ttl: The time to live for the cache.
            invalidator: A function to invalidate the cache.
            paginate: Whether to paginate the tool.
            max_docs: The maximum number of documents to return.
            max_tokens: The maximum number of tokens to return.
        """
        if not _has_valid_tool_return_annotation(method):
            raise TypeError(
                f"""Tool "{name}" must have return type annotation of either 
                "Sequence[Document]", "List[Document]', or "PaginatedResponse". 
                Got: {getattr(method, '__annotations__', {})}
            """
            )

        if cache:
            method = self._wrap_with_cache(
                method,
                invalidator=invalidator,
                ttl=ttl,
            )

        if paginate:
            if not _returns_document_sequence(method):
                raise TypeError(
                    f"Tool '{name}' with pagination=True must return Sequence[Document] or List[Document], "
                    f"not PaginatedResponse (pagination wrapper will create the PaginatedResponse)"
                )

            paginated_tool = self._wrap_with_pagination(
                cast(DocumentSequenceFunction, method),
                max_docs=max_docs,
                max_tokens=max_tokens,
            )

            method = cast(ToolFunction, paginated_tool)

        self._tools[name] = method
        setattr(self, name, method)

    def __getattr__(self, name: str) -> ToolFunction:
        """
        This allows mypy to understand that dynamically registered methods exist.
        """
        if name in self._tools:
            return self._tools[name]
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'"
        )

    # ========================================================
    # ================  Internal Wrapper Methods  ===========
    # ========================================================

    def _wrap_with_cache(
        self,
        tool_function: ToolFunction,
        *,
        invalidator: CacheInvalidator | None,
        ttl: timedelta | None,
    ) -> ToolFunction:
        """Return a cached version of the tool function."""

        @wraps(tool_function)
        def cached_tool(*args, **kwargs) -> ToolReturnType:
            cache_key = self.make_cache_key(tool_function, *args, **kwargs)

            # Check if we have a fresh cached result
            if cache_key in self._cache:
                cached_value, cached_timestamp = self._cache[cache_key]
                is_cache_fresh = True

                # Check TTL expiration
                if ttl and datetime.utcnow() - cached_timestamp > ttl:
                    is_cache_fresh = False

                # Check custom invalidation
                if invalidator and not invalidator(cache_key, cached_value):
                    is_cache_fresh = False

                if is_cache_fresh:
                    return cached_value

            # Cache miss or stale - compute fresh result
            fresh_result = tool_function(*args, **kwargs)
            self._cache[cache_key] = (fresh_result, datetime.utcnow())
            return fresh_result

        return cast(ToolFunction, cached_tool)

    def _wrap_with_pagination(
        self, method: DocumentSequenceFunction, *, max_docs: int, max_tokens: int
    ) -> PaginatedFunction:
        """
        Converts a function that returns Sequence[Document] into one that
        accepts a `page` parameter and returns a PaginatedResponse.
        """

        @wraps(method)
        def paginated_tool(*args, page: int = 0, **kwargs) -> PaginatedResponse:
            # Get all documents from the underlying function
            all_documents: Sequence[Document] = method(*args, **kwargs)

            # Calculate page slice boundaries
            page_start = page * max_docs
            page_end = page_start + max_docs
            page_documents = all_documents[page_start:page_end]

            # Apply token budget limit within the page
            final_documents: List[Document] = []
            total_tokens = 0

            for document in page_documents:
                doc_metadata = document.metadata or {}
                doc_tokens = doc_metadata.get("token_count", 0)

                if total_tokens + doc_tokens > max_tokens:
                    break

                final_documents.append(document)
                total_tokens += doc_tokens

            return PaginatedResponse(
                documents=final_documents,
                metadata=PageMetadata(
                    page_number=page,
                    has_next_page=page_end < len(all_documents),
                    total_documents=len(all_documents),
                    token_count=total_tokens,
                ),
            )

        return paginated_tool

    # ========================================================
    # ==========  Stateless‑tool decorator support  ==========
    # ========================================================

    @classmethod
    def tool(cls, **cfg):
        """
        Thin decorator for functions that **do not** use `self`.
        Example:
            @RetrieverToolkit.tool(cache=False)
            def get_docs() -> List[Document]: ...
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

    def _register_pending_stateless_tools(self):
        """Gather and register any decorator‑tagged functions."""
        for fn, cfg in getattr(self.__class__, self._PENDING_TOOLS, []):
            self.register_tool(
                method=fn,
                name=fn.__name__,
                cache=cfg.get("cache", False),
                ttl=cfg.get("ttl"),
                invalidator=cfg.get("invalidator"),
                paginate=cfg.get("paginate", False),
                max_docs=cfg.get("max_docs", 20),
                max_tokens=cfg.get("max_tokens", 2048),
            )

    # ========================================================
    # ================  Abstract Methods  ===================
    # ========================================================

    @abc.abstractmethod
    def make_cache_key(self, fn: Callable, *args, **kwargs) -> str:
        pass

    @abc.abstractmethod
    def speculate(self, query: str) -> List[Tuple[FunctionInvocation, List[Document]]]:
        pass


class RetrieverToolkit(RetrieverToolkitMeta):

    def make_cache_key(self, fn: Callable, *args, **kwargs) -> str:
        blob = json.dumps([fn.__qualname__, args, kwargs], default=str, sort_keys=True)
        return md5(blob.encode()).hexdigest()

    def speculate(self, query: str) -> List[Tuple[FunctionInvocation, List[Document]]]:
        return []


# ========================================================
# ================  Helper Functions  ===================
# ========================================================


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


def _has_valid_tool_return_annotation(tool_function: Callable) -> bool:
    """Check if a function has a valid return type annotation for a retriever tool."""
    try:
        type_hints = get_type_hints(tool_function)
        return_annotation = type_hints.get("return", None)

        if return_annotation is None:
            return False

        if return_annotation is PaginatedResponse:
            return True

        return _returns_document_sequence(tool_function)
    except Exception:
        return False


def _returns_document_sequence(tool_function: ToolFunction) -> bool:
    """
    Check if a function returns Sequence[Document] or List[Document].

    This is used for pagination validation - functions that will be paginated
    must return document sequences, not PaginatedResponse (since pagination
    wrapper will produce the PaginatedResponse).
    """
    try:
        type_hints = get_type_hints(tool_function)
        return_annotation = type_hints.get("return", None)

        if return_annotation is None:
            return False

        # PaginatedResponse is not allowed for functions that will be paginated
        if return_annotation is PaginatedResponse:
            return False

        # Must be a sequence type with Document elements
        origin_type = get_origin(return_annotation)
        if origin_type is None:
            return False

        if origin_type in (Sequence, list, List):
            type_args = get_args(return_annotation)
            if len(type_args) == 1 and type_args[0] is Document:
                return True

        return False
    except Exception:
        return False
