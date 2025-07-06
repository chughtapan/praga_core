import asyncio
import logging
from abc import ABC, abstractmethod
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)

from praga_core.types import Page, PageURI

from .page_cache import PageCache

logger = logging.getLogger(__name__)

HandlerFn = Callable[..., Awaitable[Page]]
P = TypeVar("P", bound=Page)

__all__ = ["PageRouterMixin", "HandlerFn"]


class PageRouterMixin(ABC):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._handlers: Dict[str, HandlerFn] = {}
        self._cache_enabled: Dict[str, bool] = {}

    @property
    @abstractmethod
    def root(self) -> str:
        """Abstract property that must be implemented by classes using this mixin."""
        ...

    @property
    @abstractmethod
    def page_cache(self) -> PageCache:
        """Abstract property that must be implemented by classes using this mixin."""
        ...

    def route(self, path: str, cache: bool = True) -> Callable[[HandlerFn], HandlerFn]:
        def decorator(func: HandlerFn) -> HandlerFn:
            try:
                annotations = get_type_hints(func)
            except Exception as e:
                raise RuntimeError(
                    f"Handler for page type '{path}' has invalid type annotations: {e}"
                )
            if "return" not in annotations:
                raise RuntimeError(
                    f"Handler for page type '{path}' must have a return type annotation."
                )
            return_type = annotations["return"]

            # Only check for Page subclass
            if not issubclass(return_type, Page):
                raise RuntimeError(
                    f"Handler for page type '{path}' return type annotation must be a Page subclass, "
                    f"got {getattr(return_type, '__name__', repr(return_type))}"
                )

            if path in self._handlers:
                raise RuntimeError(f"Handler already registered for path: {path}")
            self._handlers[path] = func
            self._cache_enabled[path] = cache
            return func

        return decorator

    async def create_page_uri(
        self,
        page_type: Type[Page],
        type_path: str,
        id: str,
        version: Optional[int] = None,
    ) -> PageURI:
        """Create a PageURI with this context's root.

        When version is None, determines the next version number by checking
        the cache for the latest existing version and incrementing it.

        Args:
            page_type: The Page class type
            type_path: String path for the page type (e.g., "email", "calendar_event")
            id: Unique identifier
            version: Version number (defaults to None for auto-increment)

        Returns:
            PageURI object with resolved version number
        """
        if version is None:
            return await self._create_page_uri(page_type, self.root, type_path, id)
        return PageURI(root=self.root, type=type_path, id=id, version=version)

    def validator(
        self, func: Callable[[P], Awaitable[bool]]
    ) -> Callable[[P], Awaitable[bool]]:
        """Decorator to register an async page validator.

        All validators must be async:

        Example:
            @context.validator
            async def validate_email(page: EmailPage) -> bool:
                # Could make API calls, DB queries, etc.
                return await some_async_validation(page.email)
        """
        hints = {
            name: typ for name, typ in get_type_hints(func).items() if name != "return"
        }
        if len(hints) != 1:
            raise RuntimeError("Validator function must have exactly one argument.")
        page_type = next(iter(hints.values()))
        if not isinstance(page_type, type) or not issubclass(page_type, Page):
            raise RuntimeError("Validator function's argument must be a Page subclass.")

        # Create a wrapper that handles the type cast safely
        async def validator_wrapper(page: Page) -> bool:
            if not isinstance(page, page_type):
                return False
            return await func(page)  # type: ignore

        self.page_cache.register_validator(page_type, validator_wrapper)
        return func

    def get_handler(self, path: str) -> HandlerFn:
        return self._handlers[path]

    def is_cache_enabled(self, path: str) -> bool:
        return self._cache_enabled.get(path, True)

    async def get_page(
        self, page_uri: str | PageURI, allow_stale: bool = False
    ) -> Page:
        """Retrieve a page by routing to the appropriate handler.

        First checks cache if caching is enabled for the page type.
        If not cached or caching disabled, calls the handler to generate the page.
        If allow_stale is True, will return a cached page even if it is invalid.
        """
        if isinstance(page_uri, str):
            page_uri = PageURI.parse(page_uri)
        if page_uri.type not in self._handlers:
            raise RuntimeError(f"No handler registered for type: {page_uri.type}")

        cache_enabled = self.is_cache_enabled(page_uri.type)
        handler = self._handlers[page_uri.type]
        page_type = self._get_handler_return_type(handler, page_uri.type)

        # Try cache first if enabled
        cached_page = await self._get_from_cache(
            page_type, page_uri, allow_stale=allow_stale
        )
        if cached_page:
            return cached_page
        # Not in cache or caching disabled - call handler
        page = await self._call_handler_async(handler, page_uri)

        # Store in cache if enabled and not already cached
        if cache_enabled:
            await self._store_in_cache(page, page_uri)

        return page

    async def get_pages(
        self, page_uris: Sequence[str | PageURI], allow_stale: bool = False
    ) -> List[Page]:
        """Bulk asynchronous page retrieval with parallel execution. If allow_stale is True, will return cached pages even if they are invalid."""
        parsed_uris = [
            PageURI.parse(uri) if isinstance(uri, str) else uri for uri in page_uris
        ]
        tasks = [self.get_page(uri, allow_stale=allow_stale) for uri in parsed_uris]
        return await asyncio.gather(*tasks)

    async def _get_from_cache(
        self, page_type: Type[Page], page_uri: PageURI, allow_stale: bool = False
    ) -> Page | None:
        """Attempt to retrieve page from cache. If allow_stale is True, will return a cached page even if it is invalid."""
        try:
            cached_page = await self.page_cache.get(
                page_type, page_uri, allow_stale=allow_stale
            )
            if cached_page:
                logger.debug(f"Found cached page for {page_uri}")
                return cached_page
        except Exception as e:
            logger.debug(
                f"Error checking cache for {page_uri}: {e}, falling back to handler"
            )
        return None

    async def _call_handler_async(self, handler: HandlerFn, page_uri: PageURI) -> Page:
        """Call the async handler to generate a page, ensuring proper URI versioning."""
        if page_uri.version is None:
            page_uri = await self._create_page_uri(
                self._get_handler_return_type(handler, page_uri.type),
                page_uri.root,
                page_uri.type,
                page_uri.id,
            )

        # All handlers are now async
        return await handler(page_uri)

    async def _store_in_cache(self, page: Page, page_uri: PageURI) -> None:
        """Attempt to store page in cache if not already present."""
        try:
            # Check if page is already in cache
            if not await self.page_cache.get(page.__class__, page_uri):
                await self.page_cache.store(page)
                logger.debug(f"Stored page in cache: {page_uri}")
        except Exception as e:
            logger.debug(f"Error storing page in cache for {page_uri}: {e}")

    async def _create_page_uri(
        self, page_type: Type[Page], root: str, type_path: str, id: str
    ) -> PageURI:
        if not self.is_cache_enabled(type_path):
            version = 1
        else:
            try:
                await self.page_cache._storage._registry.ensure_registered(page_type)
                prefix = f"{root}/{type_path}:{id}"
                latest_version = await self.page_cache.get_latest_version(
                    page_type, prefix
                )
                version = 1 if latest_version is None else (latest_version + 1)
            except Exception as e:
                logger.debug(
                    f"Error accessing cache for {type_path}: {e}, using version 1"
                )
                version = 1
        return PageURI(root=root, type=type_path, id=id, version=version)

    @staticmethod
    def _get_handler_return_type(handler: HandlerFn, page_type_name: str) -> Type[Page]:
        if (
            not hasattr(handler, "__annotations__")
            or "return" not in handler.__annotations__
        ):
            raise RuntimeError(
                f"Handler for page type '{page_type_name}' must have a return type annotation. "
                f"Example: def handle_{page_type_name}(page_uri: PageURI) -> {page_type_name.title()}Page:"
            )
        return_type = handler.__annotations__["return"]

        # Handle async return type annotations (e.g., Awaitable[Page])
        if hasattr(return_type, "__origin__") and return_type.__origin__ is not None:
            if return_type.__origin__ is Union:
                # Handle Union types, but for now we expect simple types
                return_type = return_type.__args__[0]
            elif hasattr(return_type, "__args__") and return_type.__args__:
                # Handle Awaitable[Page] -> Page
                return_type = return_type.__args__[0]

        if isinstance(return_type, str):
            raise RuntimeError(
                f"Handler for page type '{page_type_name}' has a string return type annotation '{return_type}'. "
                f"Please use a proper class import instead of a forward reference."
            )
        if not isinstance(return_type, type):
            raise RuntimeError(
                f"Handler for page type '{page_type_name}' return type annotation must be a class, "
                f"got {type(return_type).__name__}: {return_type}"
            )
        try:
            if not issubclass(return_type, Page):
                raise RuntimeError(
                    f"Handler for page type '{page_type_name}' return type annotation must be a Page subclass, "
                    f"got {return_type.__name__}"
                )
        except TypeError:
            raise RuntimeError(
                f"Handler for page type '{page_type_name}' return type annotation must be a Page subclass, "
                f"got {return_type}"
            )
        return return_type
