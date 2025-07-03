import logging
from typing import Awaitable, Callable, Dict, List, Type, Union

from praga_core.types import Page, PageURI

from .page_cache import PageCache

logger = logging.getLogger(__name__)

HandlerFn = Callable[..., Awaitable[Page]]

__all__ = ["PageRouter", "HandlerFn"]


class PageRouter:
    def __init__(self, page_cache: PageCache) -> None:
        self._handlers: Dict[str, HandlerFn] = {}
        self._cache_enabled: Dict[str, bool] = {}
        self._page_cache: PageCache = page_cache

    def route(self, path: str, cache: bool = True) -> Callable[[HandlerFn], HandlerFn]:
        def decorator(func: HandlerFn) -> HandlerFn:
            # Validate handler before registering
            if (
                not hasattr(func, "__annotations__")
                or "return" not in func.__annotations__
            ):
                raise RuntimeError(
                    f"Handler for page type '{path}' must have a return type annotation. "
                    f"Example: def handle_{path}(page_uri: PageURI) -> {path.title()}Page:"
                )
            return_type = func.__annotations__["return"]
            
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
                    f"Handler for page type '{path}' has a string return type annotation '{return_type}'. "
                    f"Please use a proper class import instead of a forward reference."
                )
            if not isinstance(return_type, type):
                raise RuntimeError(
                    f"Handler for page type '{path}' return type annotation must be a class, "
                    f"got {type(return_type).__name__}: {return_type}"
                )
            try:
                if not issubclass(return_type, Page):
                    raise RuntimeError(
                        f"Handler for page type '{path}' return type annotation must be a Page subclass, "
                        f"got {return_type.__name__}"
                    )
            except TypeError:
                raise RuntimeError(
                    f"Handler for page type '{path}' return type annotation must be a Page subclass, "
                    f"got {return_type}"
                )

            if path in self._handlers:
                raise RuntimeError(f"Handler already registered for path: {path}")
            self._handlers[path] = func
            self._cache_enabled[path] = cache
            # Register page type with cache if enabled
            if cache and self._page_cache:
                page_type = return_type
                try:
                    self._page_cache._storage._registry.ensure_registered(page_type)
                except Exception as e:
                    logger.debug(f"Error initializing cache for {path}: {e}")
            return func

        return decorator

    def get_handler(self, path: str) -> HandlerFn:
        return self._handlers[path]

    def is_cache_enabled(self, path: str) -> bool:
        return self._cache_enabled.get(path, True)

    async def get_page(self, page_uri: PageURI) -> Page:
        """Retrieve a page by routing to the appropriate handler.

        First checks cache if caching is enabled for the page type.
        If not cached or caching disabled, calls the handler to generate the page.
        """
        if page_uri.type not in self._handlers:
            raise RuntimeError(f"No handler registered for type: {page_uri.type}")

        cache_enabled = self.is_cache_enabled(page_uri.type)
        handler = self._handlers[page_uri.type]
        page_type = self._get_handler_return_type(handler, page_uri.type)

        # Try cache first if enabled
        if cache_enabled:
            cached_page = await self._get_from_cache(page_type, page_uri)
            if cached_page:
                return cached_page

        # Not in cache or caching disabled - call handler
        page = await self._call_handler_async(handler, page_uri)

        # Store in cache if enabled and not already cached
        if cache_enabled:
            await self._store_in_cache(page, page_uri)

        return page

    async def get_pages(self, page_uris: List[PageURI]) -> List[Page]:
        """Bulk asynchronous page retrieval with parallel execution."""
        tasks = [self.get_page(uri) for uri in page_uris]
        return await asyncio.gather(*tasks)

    async def _get_from_cache(self, page_type: Type[Page], page_uri: PageURI) -> Page | None:
        """Attempt to retrieve page from cache."""
        try:
            cached_page = await self._page_cache.get(page_type, page_uri)
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
            page_uri = self._create_page_uri(
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
            if not await self._page_cache.get(page.__class__, page_uri):
                self._page_cache.store(page)
                logger.debug(f"Stored page in cache: {page_uri}")
        except Exception as e:
            logger.debug(f"Error storing page in cache for {page_uri}: {e}")

    def _create_page_uri(
        self, page_type: Type[Page], root: str, type_path: str, id: str
    ) -> PageURI:
        if not self.is_cache_enabled(type_path):
            version = 1
        else:
            try:
                self._page_cache._storage._registry.ensure_registered(page_type)
                prefix = f"{root}/{type_path}:{id}"
                latest_version = self._page_cache.get_latest_version(page_type, prefix)
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
