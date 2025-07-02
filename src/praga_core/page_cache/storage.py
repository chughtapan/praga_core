"""Core storage operations for pages."""

import logging
from typing import Optional, Type, TypeVar

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..types import Page, PageURI
from .registry import PageRegistry
from .schema import PageRelationships
from .serialization import deserialize_from_storage, serialize_for_storage

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)


class PageStorage:
    """Handles core CRUD operations for pages."""

    def __init__(self, session_factory: sessionmaker, registry: PageRegistry):
        self._session_factory = session_factory
        self._registry = registry

    def store(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page with optional parent relationship.

        Returns True if newly created, False if already existed.
        """
        if page.uri.version is None:
            raise ValueError("Cannot store page with None version")

        table_class = self._registry.get_table_class(page.__class__)

        with self._session_factory() as session:
            # Check if page already exists
            existing = (
                session.query(table_class)
                .filter_by(uri_prefix=page.uri.prefix, version=page.uri.version)
                .first()
            )

            if existing:
                from .exceptions import PageCacheError

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

            # Add parent relationship if specified
            effective_parent = parent_uri or page.parent_uri
            if effective_parent:
                relationship = PageRelationships(
                    source_uri=str(page.uri),
                    relationship_type="parent",
                    target_uri=str(effective_parent),
                )
                session.add(relationship)

            try:
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                return False

    def get(
        self, page_type: Type[P], uri: PageURI, ignore_validity: bool = False
    ) -> Optional[P]:
        """Get a page by type and URI."""
        try:
            table_class = self._registry.get_table_class(page_type)
        except ValueError:
            # Page type not registered - return None instead of raising error
            return None

        with self._session_factory() as session:
            query = session.query(table_class).filter_by(uri_prefix=uri.prefix)

            if uri.version is not None:
                query = query.filter_by(version=uri.version)
            else:
                query = query.order_by(table_class.version.desc())

            entity = query.first()
            if entity and (ignore_validity or entity.valid):
                return self._entity_to_page(entity, page_type)
            return None

    def get_latest(self, page_type: Type[P], uri_prefix: str) -> Optional[P]:
        """Get the latest version of a page."""
        try:
            table_class = self._registry.get_table_class(page_type)
        except ValueError:
            # Page type not registered - return None instead of raising error
            return None

        with self._session_factory() as session:
            entity = (
                session.query(table_class)
                .filter_by(uri_prefix=uri_prefix)
                .filter_by(valid=True)
                .order_by(table_class.version.desc())
                .first()
            )

            if entity:
                return self._entity_to_page(entity, page_type)
            return None

    def mark_invalid(self, uri: PageURI) -> bool:
        """Mark a page as invalid."""
        for page_type in self._registry.registered_types:
            table_class = self._registry.get_table_class(page_type)

            with self._session_factory() as session:
                result = session.execute(
                    update(table_class)
                    .where(
                        table_class.uri_prefix == uri.prefix,
                        table_class.version == uri.version,
                    )
                    .values(valid=False)
                )
                session.commit()

                if result.rowcount > 0:
                    logger.debug(f"Marked page invalid: {uri}")
                    return True

        return False

    def mark_invalid_by_prefix(self, uri_prefix: str) -> int:
        """Mark all versions of a URI prefix as invalid."""
        total_invalidated = 0

        for page_type in self._registry.registered_types:
            table_class = self._registry.get_table_class(page_type)

            with self._session_factory() as session:
                result = session.execute(
                    update(table_class)
                    .where(table_class.uri_prefix == uri_prefix)
                    .values(valid=False)
                )
                session.commit()
                total_invalidated += result.rowcount

        logger.debug(f"Invalidated {total_invalidated} pages with prefix: {uri_prefix}")
        return total_invalidated

    def _entity_to_page(self, entity: any, page_type: Type[P]) -> P:
        """Convert database entity back to Page instance."""
        full_uri_string = f"{entity.uri_prefix}@{entity.version}"
        page_data = {"uri": PageURI.parse(full_uri_string)}

        for field_name, field_info in page_type.model_fields.items():
            if field_name != "uri":
                value = getattr(entity, field_name)
                converted_value = deserialize_from_storage(value, field_info.annotation)
                page_data[field_name] = converted_value

        return page_type(**page_data)
