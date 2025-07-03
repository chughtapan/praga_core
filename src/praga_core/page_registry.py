import logging
from typing import Callable, Dict, Optional, Type, TypeVar

from praga_core.types import Page

from .page_cache import PageCache

logger = logging.getLogger(__name__)

PageHandler = Callable[..., Page]
PageInvalidator = Callable[[Page], bool]
T = TypeVar("T", bound=Page)


class PageRegistry:
    def __init__(self, page_cache: PageCache):
        self._page_handlers: Dict[str, PageHandler] = {}
        self._page_invalidators: Dict[str, PageInvalidator] = {}
        self._page_cache_enabled: Dict[str, bool] = {}
        self._page_cache = page_cache

    def register_handler(
        self,
        type_name: str,
        handler_func: Callable[..., Page],
        invalidator_func: Optional[PageInvalidator] = None,
        cache: bool = True,
    ) -> None:
        if type_name in self._page_handlers:
            raise RuntimeError(f"Page handler already registered for type: {type_name}")
        page_type = PageRegistry._get_handler_return_type(handler_func, type_name)
        if cache:
            try:
                self._page_cache._storage._registry.ensure_registered(page_type)
            except Exception as e:
                logger.debug(f"Error initializing cache for {type_name}: {e}")
        self._page_handlers[type_name] = handler_func
        self._page_cache_enabled[type_name] = cache
        if invalidator_func is not None:
            assert cache
            self._page_invalidators[type_name] = invalidator_func
            self._register_invalidator_with_cache(page_type, invalidator_func)

    def handler(
        self,
        page_type: str,
        invalidator: Optional[PageInvalidator] = None,
        cache: bool = True,
    ) -> Callable[[Callable[..., T]], Callable[..., T]]:
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            self.register_handler(page_type, func, invalidator, cache)
            return func

        return decorator

    def get_handler(self, type_name: str) -> PageHandler:
        return self._page_handlers[type_name]

    def get_invalidator(self, type_name: str) -> Optional[PageInvalidator]:
        return self._page_invalidators.get(type_name)

    def is_cache_enabled(self, type_name: str) -> bool:
        return self._page_cache_enabled.get(type_name, True)

    def _register_invalidator_with_cache(
        self, page_type: Type[Page], invalidator: PageInvalidator
    ) -> None:
        self._page_cache.register_validator(page_type, invalidator)

    @staticmethod
    def _get_handler_return_type(
        handler: PageHandler, page_type_name: str
    ) -> Type[Page]:
        if (
            not hasattr(handler, "__annotations__")
            or "return" not in handler.__annotations__
        ):
            raise RuntimeError(
                f"Handler for page type '{page_type_name}' must have a return type annotation. "
                f"Example: def handle_{page_type_name}(page_uri: PageURI) -> {page_type_name.title()}Page:"
            )
        return_type = handler.__annotations__["return"]
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
