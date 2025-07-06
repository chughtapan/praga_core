from __future__ import annotations

import abc
import json
from collections.abc import Sequence as ABCSequence
from datetime import datetime, timedelta
from functools import wraps
from hashlib import md5
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import BaseModel, Field

from praga_core.types import Page

from .tool import PaginatedResponse, Tool, ToolReturnType


class FunctionInvocation(BaseModel):
    """Represents a function invocation with tool name, arguments, and keyword arguments."""

    tool_name: str = Field(description="Name of the tool being invoked")
    args: Tuple[Any, ...] = Field(description="Positional arguments for the tool")
    kwargs: Dict[str, Any] = Field(description="Keyword arguments for the tool")

    def serialise(self) -> str:
        payload = {
            "tool": self.tool_name,
            "args": self.args,
            "kwargs": tuple(sorted(self.kwargs.items())),
        }
        return json.dumps(payload, sort_keys=True, default=str)


SequenceToolFunction = Callable[..., Awaitable[Sequence[Page]]]
PaginatedToolFunction = Callable[..., Awaitable[PaginatedResponse[Page]]]
ToolFunction = Callable[..., Awaitable[ToolReturnType]]
CacheInvalidator = Callable[[str, Dict[str, Any]], bool]


class RetrieverToolkitMeta(abc.ABC):
    """Base class that handles all the internal mechanics for retriever toolkits."""

    # Stash for decorator‑based (stateless) tools – stored at *class* level
    _PENDING_TOOLS = "_praga_pending_tools"

    def __init__(self) -> None:
        # Cache maps <key> -> (<value>, <timestamp>)
        self._cache: Dict[str, Tuple[Any, datetime]] = {}

        # Tool registry maps <public_name> -> <Tool>
        self._tools: Dict[str, Tool] = {}

        # Register any functions that were tagged with @RetrieverToolkit.tool
        self._register_pending_stateless_tools()

        # Register any methods that were tagged with @tool decorator
        self._register_decorated_tool_methods()

    # ========================================================
    # ================  Internal Tool Management  ===========
    # ========================================================

    def register_tool(
        self,
        method: ToolFunction,
        name: str | None = None,
        cache: bool = False,
        ttl: timedelta | None = None,
        invalidator: CacheInvalidator | None = None,
        paginate: bool = False,
        max_docs: int = 20,
        max_tokens: int = 2_048,
    ) -> None:
        """
        Register a tool with the toolkit.

        Args:
            method: The tool function to register.
            name: The name of the tool. If not provided, uses the function's __name__.
            cache: Whether to cache the tool.
            ttl: The time to live for the cache.
            invalidator: A function to invalidate the cache.
            paginate: Whether to paginate the tool via invoke method.
            max_docs: The maximum number of Pages to return per page.
            max_tokens: The maximum number of tokens to return per page.
        """
        # Use function name if no name is provided
        if name is None:
            name = method.__name__
        if not _is_page_sequence_type(method):
            raise TypeError(
                f"""Tool "{name}" must have return type annotation of either 
                "Sequence[Page]", "List[Page]', or "PaginatedResponse". 
                Got: {getattr(method, '__annotations__', {})}
            """
            )

        if paginate and _returns_paginated_response(method):
            raise TypeError(
                f"Cannot paginate tool '{name}' because it already returns a PaginatedResponse"
            )

        # Apply caching wrapper if requested
        if cache:
            method = self._wrap_with_cache(
                method,
                invalidator=invalidator,
                ttl=ttl,
            )

        # Create Tool wrapper with pagination handled internally
        page_size = max_docs if paginate else None
        max_tokens_param = max_tokens if paginate else None
        tool = Tool(
            func=method,
            name=name,
            description=method.__doc__ or f"Tool for {name}",
            page_size=page_size,
            max_tokens=max_tokens_param,
        )

        # Register the tool
        self._tools[name] = tool

        # Set the direct method on the toolkit instance (calls without pagination)
        setattr(self, name, method)

    def get_tool(self, name: str) -> Tool:
        """Get a tool by name."""
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found")
        return self._tools[name]

    async def invoke_tool(
        self, name: str, raw_input: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Invoke a tool by name with pagination support."""
        tool = self.get_tool(name)
        try:
            import chainlit as cl  # type: ignore[import-not-found]

            cl.user_session.get("id")
            with cl.Step(
                name=name, type="tool", show_input="python", language="python"
            ) as step:
                step.input = raw_input
                response = await tool.invoke(raw_input)
                step.output = response
                return response
        except (ImportError, AttributeError):
            pass
        return await tool.invoke(raw_input)

    @property
    def tools(self) -> Dict[str, Tool]:
        """Get all registered tools."""
        return self._tools.copy()

    def __getattr__(self, name: str) -> Any:
        """
        This allows mypy to understand that dynamically registered methods exist.
        """
        if name in self._tools:
            # Return the direct method (without pagination)
            return getattr(self, name, None)
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
        async def cached_tool(*args: Any, **kwargs: Any) -> ToolReturnType:
            cache_key = self.make_cache_key(tool_function, *args, **kwargs)

            # Check if we have a fresh cached result
            if cache_key in self._cache:
                cached_value, cached_timestamp = self._cache[cache_key]
                is_cache_fresh = True

                # Check TTL expiration
                if ttl and datetime.utcnow() - cached_timestamp > ttl:
                    is_cache_fresh = False

                # Check custom invalidation
                if invalidator and not invalidator(
                    cache_key, cast(Dict[str, Any], cached_value)
                ):
                    is_cache_fresh = False

                if is_cache_fresh:
                    return cast(ToolReturnType, cached_value)

            # Cache miss or stale - compute fresh result
            fresh_result = await tool_function(*args, **kwargs)
            self._cache[cache_key] = (fresh_result, datetime.utcnow())
            return fresh_result

        return cast(ToolFunction, cached_tool)

    # ========================================================
    # ==========  Stateless‑tool decorator support  ==========
    # ========================================================

    @classmethod
    def tool(cls, **cfg: Any) -> Callable[[ToolFunction], ToolFunction]:
        """
        Thin decorator for functions that **do not** use `self`.
        Example:
            @RetrieverToolkit.tool(cache=False)
            def get_docs() -> List[Page]: ...
        """

        def marker(fn: ToolFunction) -> ToolFunction:
            bucket = getattr(cls, cls._PENDING_TOOLS, [])
            bucket.append((fn, cfg))
            setattr(cls, cls._PENDING_TOOLS, bucket)

            # Add a method stub to the class for type checking
            # This allows mypy to see the method during static analysis
            if not hasattr(cls, fn.__name__):
                setattr(cls, fn.__name__, _create_method_stub(fn))

            return fn

        return marker

    def _register_pending_stateless_tools(self) -> None:
        """Gather and register any decorator‑tagged functions."""
        for fn, cfg in getattr(self.__class__, self._PENDING_TOOLS, []):
            self.register_tool(
                method=fn,
                name=cfg.get("name", None),
                cache=cfg.get("cache", False),
                ttl=cfg.get("ttl"),
                invalidator=cfg.get("invalidator"),
                paginate=cfg.get("paginate", False),
                max_docs=cfg.get("max_docs", 20),
                max_tokens=cfg.get("max_tokens", 2048),
            )

    def _register_decorated_tool_methods(self) -> None:
        """Register methods decorated with @tool decorator."""
        # Find all decorated methods in the class
        for attr_name in dir(self.__class__):
            if attr_name.startswith("_"):
                continue

            class_attr = getattr(self.__class__, attr_name, None)
            if not class_attr:
                continue

            # Check if it's a ToolDescriptor or has the @tool markers
            is_tool_descriptor = isinstance(class_attr, ToolDescriptor)
            has_tool_markers = hasattr(class_attr, "_praga_is_tool") and hasattr(
                class_attr, "_praga_tool_config"
            )

            if not (is_tool_descriptor or has_tool_markers):
                continue

            # Get the method to register and config
            if is_tool_descriptor:
                # For ToolDescriptor, use the original function but bind it to self
                method_to_register = class_attr.func.__get__(self, self.__class__)
                config = class_attr._praga_tool_config
            else:
                # For regular decorated methods
                bound_method = getattr(self, attr_name)
                method_to_register = bound_method
                config = class_attr._praga_tool_config

            self.register_tool(
                method=method_to_register,
                name=config.get("name"),
                cache=config.get("cache", False),
                ttl=config.get("ttl"),
                invalidator=config.get("invalidator"),
                paginate=config.get("paginate", False),
                max_docs=config.get("max_docs", 20),
                max_tokens=config.get("max_tokens", 2048),
            )

    # ========================================================
    # ================  Abstract Methods  ===================
    # ========================================================

    @abc.abstractmethod
    def make_cache_key(self, fn: ToolFunction, *args: Any, **kwargs: Any) -> str:
        pass


class RetrieverToolkit(RetrieverToolkitMeta):
    """Base class for retriever toolkits that use the global context pattern."""

    def __init__(self) -> None:
        super().__init__()

    def make_cache_key(self, fn: ToolFunction, *args: Any, **kwargs: Any) -> str:
        blob = json.dumps([fn.__qualname__, args, kwargs], default=str, sort_keys=True)
        return md5(blob.encode()).hexdigest()

    @property
    @abc.abstractmethod
    def name(self) -> str:
        pass


# ========================================================
# ================  Helper Functions  ===================
# ========================================================


def _create_method_stub(fn: ToolFunction) -> ToolFunction:
    """
    Create a method stub that preserves the original function's signature.

    This stub is added to the class at decorator time to make the method
    visible to static type checkers like mypy. At runtime, the actual
    wrapped method (with caching, pagination, etc.) replaces this stub.
    """

    async def method_stub(self: Any, *args: Any, **kwargs: Any) -> ToolReturnType:
        # This will be replaced at runtime by the actual wrapped function
        return await fn(*args, **kwargs)

    method_stub.__name__ = fn.__name__
    method_stub.__doc__ = fn.__doc__
    method_stub.__annotations__ = fn.__annotations__
    return method_stub


def _is_page_sequence_type(tool_function: ToolFunction) -> bool:
    """
    Check if a function returns Awaitable[Sequence[Page]] or its subclass.
    Accepts any type that implements collections.abc.Sequence.
    """
    try:
        type_hints = get_type_hints(tool_function)
        return_annotation = type_hints.get("return", None)
        # print(return_annotation)

        if return_annotation is None:
            return False

        # Determine the actual return type (unwrap Awaitable if present)
        origin_type = get_origin(return_annotation)
        if origin_type is Awaitable:
            # e.g., Awaitable[Sequence[Page]]
            inner_type = get_args(return_annotation)[0]
        else:
            # e.g., Sequence[Page]
            inner_type = return_annotation

        inner_origin = get_origin(inner_type) or inner_type

        # Accept any type that implements collections.abc.Sequence
        if isinstance(inner_origin, type) and issubclass(inner_origin, ABCSequence):
            type_args = get_args(inner_type)
            if len(type_args) == 1:
                Page_type = type_args[0]
                # Check if it's Page or a subclass of Page
                if Page_type is Page:
                    return True
                if isinstance(Page_type, type) and issubclass(Page_type, Page):
                    return True

        return False
    except Exception:
        return False


def _returns_paginated_response(tool_function: ToolFunction) -> bool:
    """Check if a function returns Awaitable[PaginatedResponse]."""
    try:
        type_hints = get_type_hints(tool_function)
        return_annotation = type_hints.get("return", None)
        if return_annotation is None:
            return False

        # Get the outer type (should be Awaitable)
        origin = get_origin(return_annotation)
        if origin is Awaitable:
            # Unwrap Awaitable
            inner_type = get_args(return_annotation)[0]
        else:
            inner_type = return_annotation

        inner_origin = get_origin(inner_type)

        # Handle generic PaginatedResponse[T]
        if inner_origin is PaginatedResponse:
            return True

        return False
    except Exception:
        return False


# ========================================================
# ================  Global Tool Decorator  ==============
# ========================================================


class ToolDescriptor:
    """Descriptor that validates @tool usage and provides the original function."""

    def __init__(self, func: ToolFunction, config: Dict[str, Any]):
        self.func = func
        self.config = config
        self.name: Optional[str] = None
        self.__name__: str = func.__name__
        self.__doc__: Optional[str] = func.__doc__
        self.__annotations__: Dict[str, Any] = getattr(func, "__annotations__", {})

    def __set_name__(self, owner: type, name: str) -> None:
        """Called when the descriptor is assigned to a class attribute."""
        self.name = name

        # Check if the owner class inherits from RetrieverToolkitMeta
        try:
            is_retriever_toolkit_subclass = issubclass(owner, RetrieverToolkitMeta)
        except TypeError:
            # owner is not a class
            is_retriever_toolkit_subclass = False

        if not is_retriever_toolkit_subclass:
            raise TypeError(
                f"@tool decorator can only be used on RetrieverToolkit classes. "
                f"Method '{name}' in class '{owner.__name__}' uses @tool "
                f"but the class does not inherit from RetrieverToolkit."
            )

    def __get__(self, instance: Any, owner: type) -> Any:
        """Return the bound method when accessed on an instance."""
        if instance is None:
            return self
        return self.func.__get__(instance, owner)


def tool(
    *,
    name: str | None = None,
    cache: bool = False,
    ttl: timedelta | None = None,
    invalidator: CacheInvalidator | None = None,
    paginate: bool = False,
    max_docs: int = 20,
    max_tokens: int = 2048,
) -> Callable[[ToolFunction], ToolFunction]:
    """
    Global @tool decorator for methods within RetrieverToolkit classes.

    This decorator can be applied to methods within classes that inherit from
    RetrieverToolkit. It will automatically register the tool when the class
    is instantiated.

    Args:
        name: The name of the tool. If not provided, uses the method's __name__.
        cache: Whether to cache the tool.
        ttl: The time to live for the cache.
        invalidator: A function to invalidate the cache.
        paginate: Whether to paginate the tool via invoke method.
        max_docs: The maximum number of Pages to return per page.
        max_tokens: The maximum number of tokens to return per page.

    Raises:
        TypeError: If the decorator is applied to a method in a class that
                  does not inherit from RetrieverToolkit.

    Example:
        class MyToolkit(RetrieverToolkit):
            @tool(cache=True, paginate=True)
            def search_docs(self, query: str) -> List[Page]:
                return []
    """

    def decorator(func: ToolFunction) -> ToolFunction:
        config = {
            "name": name,
            "cache": cache,
            "ttl": ttl,
            "invalidator": invalidator,
            "paginate": paginate,
            "max_docs": max_docs,
            "max_tokens": max_tokens,
        }

        # Create a descriptor that validates class inheritance
        descriptor = ToolDescriptor(func, config)

        # Store the configuration and mark as tool for later registration
        descriptor._praga_tool_config = config  # type: ignore[attr-defined]
        descriptor._praga_is_tool = True  # type: ignore[attr-defined]

        return descriptor  # type: ignore[return-value]

    return decorator
