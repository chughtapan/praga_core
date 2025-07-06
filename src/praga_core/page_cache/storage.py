"""Core storage operations for pages (async version)."""

import logging
from typing import Any, Optional, Type, TypeVar

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..types import Page, PageURI
from .registry import PageRegistry
from .schema import PageRelationships
from .serialization import deserialize_from_storage, serialize_for_storage

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)


class PageStorage:
    """Handles core CRUD operations for pages (async)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], registry: PageRegistry
    ):
        self._session_factory = session_factory
        self._registry = registry

    async def store(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page with optional parent relationship.

        Returns True if newly created, False if already existed.
        """
        if page.uri.version is None:
            raise ValueError("Cannot store page with None version")

        await self._registry.ensure_registered(page.__class__)
        table_class = self._registry.get_table_class(page.__class__)

        async with self._session_factory() as session:
            # Check if page already exists
            logger.debug(f"[STORE] Checking if page exists: {page.uri}")
            existing = await session.execute(
                select(table_class).where(
                    table_class.uri_prefix == page.uri.prefix,
                    table_class.version == page.uri.version,
                )
            )
            existing_row = existing.scalar_one_or_none()
            logger.debug(f"[STORE] Exists: {existing_row is not None} for {page.uri}")

            if existing_row:
                from .exceptions import PageCacheError

                logger.debug(f"[STORE] Page already exists, raising error: {page.uri}")
                raise PageCacheError(
                    f"Page {page.uri} already exists and cannot be updated"
                )

            # Create new page record
            page_data = {
                "uri_prefix": page.uri.prefix,
                "version": page.uri.version,
                "valid": True,
            }

            # Serialize all fields except uri
            for field_name in page.__class__.model_fields:
                if field_name != "uri":
                    value = getattr(page, field_name)
                    page_data[field_name] = serialize_for_storage(value)

            page_entity = table_class(**page_data)
            session.add(page_entity)
            logger.debug(f"[STORE] Added new page entity: {page.uri}")

            # Add parent relationship if specified (in same transaction)
            effective_parent = parent_uri or page.parent_uri
            if effective_parent:
                relationship = PageRelationships(
                    source_uri=str(page.uri),
                    relationship_type="parent",
                    target_uri=str(effective_parent),
                )
                session.add(relationship)
                logger.debug(
                    f"[STORE] Added relationship: {page.uri} -> {effective_parent}"
                )

            try:
                await session.commit()
                logger.debug(f"[STORE] Committed page and relationship: {page.uri}")
                return True
            except IntegrityError:
                await session.rollback()
                logger.debug(f"[STORE] Rollback due to integrity error: {page.uri}")
                return False

    async def get(
        self, page_type: Type[P], uri: PageURI, ignore_validity: bool = False
    ) -> Optional[P]:
        """Get a page by type and URI (async)."""
        try:
            await self._registry.ensure_registered(page_type)
            table_class = self._registry.get_table_class(page_type)
        except ValueError:
            # Page type not registered - return None instead of raising error
            logger.debug(f"[GET] Page type not registered: {page_type}")
            return None

        async with self._session_factory() as session:
            query = select(table_class).where(table_class.uri_prefix == uri.prefix)
            if uri.version is not None:
                query = query.where(table_class.version == uri.version)
            else:
                query = query.order_by(table_class.version.desc())

            logger.debug(f"[GET] Querying for page: {uri}")
            result = await session.execute(query)
            entity = result.scalars().first()
            logger.debug(f"[GET] Found: {entity is not None} for {uri}")
            if entity and (ignore_validity or entity.valid):
                logger.debug(f"[GET] Returning entity for {uri}")
                return self._entity_to_page(entity, page_type)
            logger.debug(f"[GET] No valid entity for {uri}")
            return None

    async def get_latest_version(
        self, page_type: Type[P], uri_prefix: str
    ) -> Optional[P]:
        """Get the latest version of a page."""
        try:
            await self._registry.ensure_registered(page_type)
            table_class = self._registry.get_table_class(page_type)
        except ValueError:
            # Page type not registered - return None instead of raising error
            return None

        async with self._session_factory() as session:
            query = (
                select(table_class)
                .where(table_class.uri_prefix == uri_prefix)
                .order_by(table_class.version.desc())
                .limit(1)
            )
            result = await session.execute(query)
            entity = result.scalar_one_or_none()
            if entity:
                return self._entity_to_page(entity, page_type)
            return None

    async def mark_invalid(self, uri: PageURI) -> bool:
        """Mark a page as invalid (async)."""
        for page_type in self._registry.registered_types:
            await self._registry.ensure_registered(page_type)
            table_class = self._registry.get_table_class(page_type)
            async with self._session_factory() as session:
                result = await session.execute(
                    update(table_class)
                    .where(
                        table_class.uri_prefix == uri.prefix,
                        table_class.version == uri.version,
                    )
                    .values(valid=False)
                )
                await session.commit()
                if result.rowcount > 0:
                    logger.debug(f"Marked page invalid: {uri}")
                    return True
        return False

    async def mark_invalid_by_prefix(self, uri_prefix: str) -> int:
        """Mark all versions of a URI prefix as invalid (async)."""
        total_invalidated = 0
        for page_type in self._registry.registered_types:
            await self._registry.ensure_registered(page_type)
            table_class = self._registry.get_table_class(page_type)
            async with self._session_factory() as session:
                result = await session.execute(
                    update(table_class)
                    .where(table_class.uri_prefix == uri_prefix)
                    .values(valid=False)
                )
                await session.commit()
                total_invalidated += result.rowcount
        logger.debug(f"Invalidated {total_invalidated} pages with prefix: {uri_prefix}")
        return total_invalidated

    def _entity_to_page(self, entity: Any, page_type: Type[P]) -> P:
        """Convert database entity back to Page instance."""
        full_uri_string = f"{entity.uri_prefix}@{entity.version}"
        page_data = {"uri": PageURI.parse(full_uri_string)}
        for field_name, field_info in page_type.model_fields.items():
            if field_name != "uri":
                value = getattr(entity, field_name)
                converted_value = deserialize_from_storage(value, field_info.annotation)
                page_data[field_name] = converted_value
        return page_type(**page_data)
