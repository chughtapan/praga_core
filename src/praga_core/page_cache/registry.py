"""Page type registration and table management."""

import logging
from typing import Any, Dict, List, Type

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from ..types import Page
from .schema import clear_table_registry, create_page_table, get_table_registry

logger = logging.getLogger(__name__)


class PageRegistry:
    """Manages page type registration and table creation."""

    def __init__(self, engine: Engine):
        self._engine = engine
        self._registered_types: set[str] = set()
        self._page_classes: Dict[str, Type[Page]] = {}

    async def ensure_registered(self, page_type: Type[Page]) -> None:
        """Ensure a page type is registered, registering if needed (async)."""
        type_name = page_type.__name__
        if type_name not in self._registered_types:
            await self._register(page_type)

    async def _register(self, page_type: Type[Page]) -> None:
        """Register a page type for caching (async)."""
        type_name = page_type.__name__
        table_class = create_page_table(page_type)

        # Create the table in the database if it doesn't exist
        if not isinstance(self._engine, AsyncEngine):
            raise RuntimeError("Must use AsyncSqlAlchemy engine")

        # Use AsyncConnection.run_sync to run the synchronous create_all method
        async with self._engine.begin() as conn:
            await conn.run_sync(table_class.metadata.create_all, checkfirst=True)

        self._registered_types.add(type_name)
        self._page_classes[type_name] = page_type
        logger.debug(f"Registered page type: {type_name}")

    def get_table_class(self, page_type: Type[Page]) -> Any:
        """Get the SQLAlchemy table class for a page type."""
        type_name = page_type.__name__
        table_registry = get_table_registry()

        if type_name not in table_registry:
            raise ValueError(f"Page type {type_name} not registered")

        return table_registry[type_name]

    def get_page_class(self, type_name: str) -> Type[Page]:
        """Get the Page class for a type name."""
        if type_name not in self._page_classes:
            raise ValueError(f"Page type {type_name} not registered")
        return self._page_classes[type_name]

    @property
    def registered_types(self) -> List[Type[Page]]:
        """Get list of registered page types."""
        return list(self._page_classes.values())

    @property
    def registered_type_names(self) -> List[str]:
        """Get list of registered type names."""
        return list(self._registered_types)

    def clear(self) -> None:
        """Clear all registrations."""
        clear_table_registry()
        self._registered_types.clear()
        self._page_classes.clear()
        logger.debug("Cleared page type registry")
