"""Schema utilities for mapping Python types to SQLAlchemy types and creating tables."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Type, TypeVar, Union, get_args, get_origin

from sqlalchemy import (
    JSON,
    TIMESTAMP,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm.decl_api import DeclarativeBase

from ..types import Page, PageURI

logger = logging.getLogger(__name__)

# TypeVar for generic Page type support
P = TypeVar("P", bound=Page)


# SQLAlchemy declarative base for table definitions
class Base(DeclarativeBase):
    pass


# Global registry to reuse table classes across PageCache instances
# This prevents SQLAlchemy warnings about duplicate table definitions
_TABLE_REGISTRY: Dict[str, Any] = {}


class PageRelationships(Base):
    """Table for storing page relationships for efficient provenance tracking.

    This table directly stores parent-child relationships between pages,
    allowing for efficient queries without scanning all page tables.
    """

    __tablename__ = "page_relationships"

    # Composite primary key of source and relationship type
    source_uri = Column(String, primary_key=True)
    relationship_type = Column(String, primary_key=True, default="parent")
    target_uri = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index("idx_relationships_target", "target_uri"),
        Index("idx_relationships_source", "source_uri"),
    )


def get_base_type(field_type: Any) -> Any:
    """Extract the base type from a complex type annotation.

    Handles Optional/Union types, Annotated types, and container types like List, Dict.

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
            # Recursively handle the non-None type (in case it's also Annotated)
            return get_base_type(non_none_types[0])
        # If multiple non-None types, treat as complex type
        return None

    # Handle Annotated types (extract the actual type)
    try:
        from typing import _AnnotatedAlias  # type: ignore

        if isinstance(field_type, _AnnotatedAlias):
            # Get the first argument which is the actual type
            args = get_args(field_type)
            if args:
                return get_base_type(args[0])
    except ImportError:
        # For older Python versions, try another approach
        pass

    # Alternative check for Annotated types
    if (
        hasattr(field_type, "__origin__")
        and getattr(field_type, "__origin__", None) is not None
    ):
        origin_name = getattr(field_type.__origin__, "_name", None)
        if origin_name == "Annotated":
            args = get_args(field_type)
            if args:
                return get_base_type(args[0])

    # Handle container types (List, Dict, etc.)
    if origin is not None:
        # For now, treat all container types as JSON-serializable
        return None

    return field_type


def get_sql_type(field_type: Any, field_info: Any) -> Any:
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
    base_type = get_base_type(field_type)

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


def get_page_schema_signature(page_class: Type[P]) -> str:
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
            sql_type = get_sql_type(field_type, field)
            is_optional = get_origin(field_type) is Union and type(None) in get_args(
                field_type
            )
            fields.append(f"{field_name}:{sql_type.__class__.__name__}:{is_optional}")

    return "|".join(sorted(fields))


def create_page_table(page_class: Type[P]) -> Any:
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
        current_signature = get_page_schema_signature(page_class)
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
        "_schema_signature": get_page_schema_signature(page_class),
    }

    # Add page fields as columns with appropriate SQL types
    for field_name, field in page_class.model_fields.items():
        if field_name not in ("uri",):  # Skip uri field - handled as primary key
            field_type = field.annotation
            sql_type = get_sql_type(field_type, field)

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


def clear_table_registry() -> None:
    """Clear the global table registry."""
    _TABLE_REGISTRY.clear()


def get_table_registry() -> Dict[str, Any]:
    """Get a copy of the current table registry."""
    return _TABLE_REGISTRY.copy()
