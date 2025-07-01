"""SQL-based page cache for storing and retrieving Page instances.

This module provides a PageCache class that automatically creates SQL tables
from Pydantic Page models and provides type-safe querying capabilities.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    Boolean,
    Column,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.decl_api import declarative_base

from .types import Page, PageURI

logger = logging.getLogger(__name__)

# TypeVar for generic Page type support
P = TypeVar("P", bound=Page)

# SQLAlchemy declarative base for table definitions
Base = declarative_base()

# Global registry to reuse table classes across PageCache instances
# This prevents SQLAlchemy warnings about duplicate table definitions
_TABLE_REGISTRY: Dict[str, Any] = {}


def _get_base_type(field_type: Any) -> Any:
    """Extract the base type from a complex type annotation.

    Handles Optional/Union types and container types like List, Dict.

    Args:
        field_type: The type annotation to analyze

    Returns:
        The base type if extractable, None for complex container types
    """
    # Handle Optional/Union types
    origin = get_origin(field_type)
    if origin is Union:
        # Get non-None type from Optional/Union
        args = get_args(field_type)
        non_none_types = [t for t in args if t is not type(None)]
        if len(non_none_types) == 1:
            return non_none_types[0]
        # If multiple non-None types, treat as complex type
        return None

    # Handle container types (List, Dict, etc.)
    if origin is not None:
        # For now, treat all container types as JSON-serializable
        return None

    return field_type


def _get_sql_type(field_type: Any, field_info: Any) -> Any:
    """Map Python/Pydantic types to appropriate SQLAlchemy column types.

    Args:
        field_type: The Python/Pydantic type annotation
        field_info: The Pydantic field info object

    Returns:
        Appropriate SQLAlchemy column type

    Examples:
        str -> String (default) or Text (if sql_type="text" in field metadata)
        int -> Integer
        float -> Float
        bool -> Boolean
        datetime -> TIMESTAMP with timezone
        Optional[int] -> Integer with nullable=True
        List[str] -> JSON
        Dict[str, Any] -> JSON
    """
    # Get the base type (handling Optional, Union, etc)
    base_type = _get_base_type(field_type)

    # If no base type found (complex type), use JSON
    if base_type is None:
        return JSON

    # Handle string types with optional metadata for TEXT vs VARCHAR
    if base_type == str:
        metadata = getattr(field_info, "json_schema_extra", {}) or {}
        sql_type_name = metadata.get("sql_type", "string").lower()
        if sql_type_name == "text":
            return Text
        return String

    # Handle PageURI as string (special case)
    from .types import PageURI

    if base_type == PageURI:
        return String

    # Map basic Python types to SQLAlchemy types
    type_mapping = {
        int: Integer,
        float: Float,
        bool: Boolean,
        datetime: TIMESTAMP(timezone=True),
        Decimal: Numeric,
        dict: JSON,
        list: JSON,
    }

    sql_type = type_mapping.get(base_type)
    if sql_type is None:
        # Fallback to JSON for unknown types
        logger.debug(f"Unknown type {base_type}, using JSON column")
        return JSON

    return sql_type


def _get_page_schema_signature(page_class: Type[P]) -> str:
    """Generate a signature string for the page schema to detect changes.

    This helps detect when a Page model's schema has changed between
    different runs, which could require database migrations.

    Args:
        page_class: The Page class to analyze

    Returns:
        A string signature representing the schema
    """
    fields = []
    for field_name, field in page_class.model_fields.items():
        if field_name not in ("uri", "id"):  # Skip special fields
            field_type = field.annotation
            sql_type = _get_sql_type(field_type, field)
            is_optional = get_origin(field_type) is Union and type(None) in get_args(
                field_type
            )
            fields.append(f"{field_name}:{sql_type.__class__.__name__}:{is_optional}")

    return "|".join(sorted(fields))


def _create_page_table(page_class: Type[P]) -> Any:
    """Create or reuse a SQLAlchemy table class from a Page class.

    This function automatically generates SQLAlchemy table classes based on
    Pydantic Page models. It includes automatic type mapping and reuses
    existing table classes to avoid SQLAlchemy warnings.

    Args:
        page_class: The Page class to create a table for

    Returns:
        SQLAlchemy table class (declarative model)
    """
    page_type_name = page_class.__name__
    table_name = f"{page_type_name.lower()}_pages"

    # Check if we already have this table class in our registry
    if page_type_name in _TABLE_REGISTRY:
        existing_table_class = _TABLE_REGISTRY[page_type_name]

        # Check if schema has changed since last registration
        current_signature = _get_page_schema_signature(page_class)
        if hasattr(existing_table_class, "_schema_signature"):
            if existing_table_class._schema_signature != current_signature:
                logger.warning(
                    f"Schema change detected for {page_type_name}. "
                    f"Consider dropping and recreating the database or running migrations. "
                    f"Reusing existing table schema for now."
                )

        logger.debug(f"Reusing existing table class for {page_type_name}")
        return existing_table_class

    # Create new table class dynamically
    class_name = f"{page_type_name}Table"

    # Define base table attributes
    attrs = {
        "__tablename__": table_name,
        "uri": Column(String, primary_key=True),  # URI as primary key
        "created_at": Column(
            TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
        ),
        "updated_at": Column(
            TIMESTAMP(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
        ),
        "_schema_signature": _get_page_schema_signature(page_class),
    }

    # Add page fields as columns with appropriate SQL types
    for field_name, field in page_class.model_fields.items():
        if field_name not in ("uri",):  # Skip uri field - handled as primary key
            field_type = field.annotation
            sql_type = _get_sql_type(field_type, field)

            # Make column nullable if field is Optional
            is_optional = get_origin(field_type) is Union and type(None) in get_args(
                field_type
            )
            attrs[field_name] = Column(sql_type, nullable=is_optional)

    # Create the table class dynamically
    table_class = type(class_name, (Base,), attrs)

    # Register in our global registry to enable reuse
    _TABLE_REGISTRY[page_type_name] = table_class

    logger.debug(f"Created new table class for {page_type_name}")
    return table_class


class PageCache:
    """SQL-based cache for storing and retrieving Page instances.

    This class provides automatic SQL table generation from Pydantic Page models,
    with support for storing, retrieving, and querying pages using type-safe
    SQLAlchemy expressions.

    Features:
    - Automatic schema synthesis from Page models
    - URI-based primary keys
    - Type-safe querying with SQLAlchemy expressions
    - Table reuse across cache instances
    - Support for complex field types via JSON columns

    Example:
        cache = PageCache("sqlite:///pages.db")

        # Pages are automatically registered when first stored
        user = UserPage(uri=PageURI(...), name="John", email="john@example.com")
        cache.store_page(user)

        # Query with type-safe expressions
        users = cache.find_pages_by_attribute(
            UserPage,
            lambda t: t.email.like("%@company.com")
        )
    """

    def __init__(self, url: str, drop_previous: bool = False) -> None:
        """Initialize the page cache.

        Args:
            url: Database URL (e.g., "sqlite:///cache.db", "postgresql://...")
            drop_previous: Whether to drop existing tables on initialization
        """
        # Configure engine based on database type
        engine_args = {}
        if url.startswith("postgresql"):
            from sqlalchemy.pool import NullPool

            engine_args["poolclass"] = NullPool

        self._engine = create_engine(url, **engine_args)
        self._session = sessionmaker(bind=self.engine)

        # Instance-specific tracking of registered page types
        self._registered_types: set[str] = set()
        self._table_mapping: Dict[str, str] = {}

        # Reset database if requested
        if drop_previous:
            self._reset()

    def _reset(self) -> None:
        """Reset the database by dropping all tables and clearing registries."""
        Base.metadata.drop_all(self.engine)

        # Clear registries for clean state
        _TABLE_REGISTRY.clear()
        self._registered_types.clear()
        self._table_mapping.clear()

        logger.debug("Reset database and cleared all registries")

    def register_page_type(self, page_type: Type[P]) -> None:
        """Register a page type for caching.

        This creates the necessary SQL table structure for the page type
        if it doesn't already exist.

        Args:
            page_type: Page class to register for caching
        """
        type_name = page_type.__name__
        if type_name in self._registered_types:
            return  # Already registered in this instance

        # Create or reuse the table class
        table_class = _create_page_table(page_type)
        self._table_mapping[type_name] = table_class.__tablename__

        # Create the table in the database if it doesn't exist
        table_class.__table__.create(self.engine, checkfirst=True)

        # Mark as registered in this instance
        self._registered_types.add(type_name)

        logger.debug(f"Registered page type {type_name}")

    def _serialize_for_storage(self, value: Any) -> Any:
        """Convert complex objects to JSON-serializable formats for database storage.

        Handles:
        - PageURI objects → strings
        - Pydantic models → JSON-serialized dictionaries
        - Lists and dicts recursively

        Args:
            value: The value to serialize

        Returns:
            JSON-serializable representation of the value
        """
        from pydantic import BaseModel

        from .types import PageURI

        if isinstance(value, PageURI):
            return str(value)
        elif isinstance(value, BaseModel):
            # Use mode='json' to handle datetime serialization automatically
            return value.model_dump(mode="json")
        elif isinstance(value, list):
            return [self._serialize_for_storage(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_for_storage(v) for k, v in value.items()}
        else:
            return value

    def _deserialize_from_storage(self, value: Any, field_type: Any) -> Any:
        """Convert stored values back to their original types after database retrieval.

        Handles:
        - String → PageURI objects
        - JSON dictionaries → Pydantic models
        - Lists with typed elements
        - Nested structures recursively

        Args:
            value: The stored value to deserialize
            field_type: The target field type annotation

        Returns:
            Deserialized value with proper types restored
        """

        from .types import PageURI

        base_type = _get_base_type(field_type)

        # Handle PageURI conversion
        if base_type == PageURI and isinstance(value, str):
            return PageURI.parse(value)

        # Handle list types
        if get_origin(field_type) is list and isinstance(value, list):
            return self._deserialize_list(value, field_type)

        # Handle single Pydantic model
        if self._is_pydantic_model_type(base_type) and isinstance(value, dict):
            return base_type.model_validate(value)

        # Handle nested dictionaries
        if isinstance(value, dict):
            return {
                k: self._deserialize_from_storage(v, field_type)
                for k, v in value.items()
            }

        return value

    def _deserialize_list(self, value: list[Any], field_type: Any) -> list[Any]:
        """Deserialize a list with proper element type handling."""

        args = get_args(field_type)
        if not args:
            return value

        element_type = args[0]

        if element_type == PageURI:
            # Handle List[PageURI]
            return [
                PageURI.parse(item) if isinstance(item, str) else item for item in value
            ]
        elif self._is_pydantic_model_type(element_type):
            # Handle List[PydanticModel]
            return [
                element_type.model_validate(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            # Handle other list types recursively
            return [
                self._deserialize_from_storage(item, element_type) for item in value
            ]

    def _is_pydantic_model_type(self, type_obj: Any) -> bool:
        """Check if a type is a Pydantic model class."""
        from pydantic import BaseModel

        return isinstance(type_obj, type) and issubclass(type_obj, BaseModel)

    def store_page(self, page: Page) -> bool:
        """Store a page in the cache.

        If the page already exists (same URI), it will be updated.
        Otherwise, a new record will be created.

        Args:
            page: Page instance to store

        Returns:
            True if page was newly created, False if updated
        """
        page_type_name = page.__class__.__name__
        if page_type_name not in self._registered_types:
            self.register_page_type(page.__class__)

        table_class = _TABLE_REGISTRY[page_type_name]

        with self.get_session() as session:
            # Check if page already exists
            existing = session.query(table_class).filter_by(uri=str(page.uri)).first()

            if existing:
                # Update existing page
                for field_name in page.__class__.model_fields:
                    if field_name not in ("uri",):
                        value = getattr(page, field_name)
                        # Serialize complex objects for storage
                        converted_value = self._serialize_for_storage(value)
                        setattr(existing, field_name, converted_value)
                existing.updated_at = datetime.now(timezone.utc)
                session.commit()
                return False
            else:
                # Create new page record
                page_data = {"uri": str(page.uri)}
                for field_name in page.__class__.model_fields:
                    if field_name not in ("uri",):
                        value = getattr(page, field_name)
                        # Serialize complex objects for storage
                        page_data[field_name] = self._serialize_for_storage(value)

                page_entity = table_class(**page_data)
                session.add(page_entity)
                try:
                    session.commit()
                    return True
                except IntegrityError:
                    session.rollback()
                    return False

    def get_page(self, page_type: Type[P], uri: PageURI) -> Optional[P]:
        """Retrieve a page by its type and URI.

        Args:
            page_type: The Page class type to retrieve
            uri: The PageURI to look up

        Returns:
            Page instance of the requested type if found, None otherwise
        """
        page_type_name = page_type.__name__
        if page_type_name not in _TABLE_REGISTRY:
            return None

        table_class = _TABLE_REGISTRY[page_type_name]

        with self.get_session() as session:
            entity = session.query(table_class).filter_by(uri=str(uri)).first()

            if entity:
                # Convert database entity back to Page instance
                page_data = {"uri": PageURI.parse(entity.uri)}
                for field_name, field_info in page_type.model_fields.items():
                    if field_name not in ("uri",):
                        value = getattr(entity, field_name)
                        # Deserialize stored values back to original types
                        converted_value = self._deserialize_from_storage(
                            value, field_info.annotation
                        )
                        page_data[field_name] = converted_value

                return page_type(**page_data)
            return None

    def find_pages_by_attribute(
        self,
        page_type: Type[P],
        query_filter: Callable[[Any], bool],
    ) -> List[P]:
        """Find pages of a given type that match a SQLAlchemy query filter.

        This method provides type-safe querying using SQLAlchemy expressions.
        You can use lambda functions for simple queries or direct SQLAlchemy
        expressions for more complex cases.

        Args:
            page_type: Page class type to query
            query_filter: Either a callable that takes the table class and returns
                         a filter expression, or a SQLAlchemy filter expression

        Returns:
            List of matching Page instances of the requested type

        Examples:
            # Simple equality check
            users = cache.find_pages_by_attribute(
                UserPage,
                lambda t: t.email == "test@example.com"
            )

            # Pattern matching
            users = cache.find_pages_by_attribute(
                UserPage,
                lambda t: t.name.ilike("%john%")
            )

            # Complex conditions
            users = cache.find_pages_by_attribute(
                UserPage,
                lambda t: (t.age > 18) & (t.email.like("%@company.com"))
            )

            # Direct table reference (advanced)
            table = cache._get_table_class(UserPage)
            users = cache.find_pages_by_attribute(
                UserPage,
                table.email == "test@example.com"
            )
        """
        page_type_name = page_type.__name__
        if page_type_name not in _TABLE_REGISTRY:
            return []

        table_class = _TABLE_REGISTRY[page_type_name]

        with self.get_session() as session:
            query = session.query(table_class)

            # Apply the filter based on its type
            if callable(query_filter):
                # Lambda function that takes table class and returns filter
                filter_expr = query_filter(table_class)
                query = query.filter(filter_expr)
            else:
                # Direct SQLAlchemy filter expression
                query = query.filter(query_filter)

            entities = query.all()
            results = []

            # Convert database entities back to Page instances
            for entity in entities:
                page_data = {"uri": PageURI.parse(entity.uri)}
                for field_name, field_info in page_type.model_fields.items():
                    if field_name not in ("uri",):
                        value = getattr(entity, field_name)
                        # Deserialize stored values back to original types
                        converted_value = self._deserialize_from_storage(
                            value, field_info.annotation
                        )
                        page_data[field_name] = converted_value

                results.append(page_type(**page_data))

            return results

    def _get_table_class(self, page_type: Type[P]) -> Any:
        """Get the SQLAlchemy table class for a page type.

        This is useful for creating direct filter expressions when you need
        more control over the query construction.

        Args:
            page_type: Page class type

        Returns:
            SQLAlchemy table class (declarative model)

        Raises:
            ValueError: If page type is not registered

        Example:
            table = cache._get_table_class(UserPage)
            users = cache.find_pages_by_attribute(
                UserPage,
                table.email.in_(["user1@example.com", "user2@example.com"])
            )
        """
        page_type_name = page_type.__name__
        if page_type_name not in _TABLE_REGISTRY:
            raise ValueError(f"Page type {page_type_name} not registered")
        return _TABLE_REGISTRY[page_type_name]

    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine instance."""
        return self._engine

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy session instance

        Note:
            Remember to close the session when done, or use it in a context manager.
        """
        return self._session()

    @property
    def registered_page_types(self) -> List[str]:
        """Get list of page type names registered in this cache instance.

        Returns:
            List of registered page type names
        """
        return list(self._registered_types)

    @property
    def table_mapping(self) -> Dict[str, str]:
        """Get mapping from page type names to database table names.

        Returns:
            Dictionary mapping page type names to table names
        """
        return self._table_mapping.copy()
