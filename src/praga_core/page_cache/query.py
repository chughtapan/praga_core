"""Page query building and execution."""

import logging
from typing import Any, Callable, List, Type, TypeVar

from sqlalchemy.orm import sessionmaker

from ..types import Page
from .registry import PageRegistry
from .serialization import deserialize_from_storage

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)


class PageQuery:
    """Handles page query building and execution."""

    def __init__(self, session_factory: sessionmaker, registry: PageRegistry):
        self._session_factory = session_factory
        self._registry = registry

    def find(self, page_type: Type[P], filters: List[Callable[[Any], Any]]) -> List[P]:
        """Find pages matching the given filters.

        Args:
            page_type: The type of pages to search for
            filters: List of filter functions that take the table class and return filter expressions

        Returns:
            List of matching pages (includes invalid pages - caller should validate)
        """
        try:
            table_class = self._registry.get_table_class(page_type)
        except ValueError:
            # Page type not registered
            return []

        with self._session_factory() as session:
            query = session.query(table_class)

            # Apply all filters
            for filter_func in filters:
                if callable(filter_func):
                    filter_expr = filter_func(table_class)
                    query = query.filter(filter_expr)
                else:
                    # Direct SQLAlchemy expression
                    query = query.filter(filter_func)

            # Only return valid pages at the database level
            query = query.filter(table_class.valid.is_(True))

            entities = query.all()

            # Convert entities back to Page instances
            results = []
            for entity in entities:
                try:
                    page = self._entity_to_page(entity, page_type)
                    results.append(page)
                except Exception as e:
                    logger.warning(f"Failed to convert entity to page: {e}")
                    continue

            return results

    def _entity_to_page(self, entity: Any, page_type: Type[P]) -> P:
        """Convert database entity back to Page instance."""
        from ..types import PageURI

        full_uri_string = f"{entity.uri_prefix}@{entity.version}"
        page_data = {"uri": PageURI.parse(full_uri_string)}

        for field_name, field_info in page_type.model_fields.items():
            if field_name != "uri":
                value = getattr(entity, field_name)
                converted_value = deserialize_from_storage(value, field_info.annotation)
                page_data[field_name] = converted_value

        return page_type(**page_data)
