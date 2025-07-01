"""Serialization utilities for converting complex objects to/from database storage."""

from typing import Any, get_args, get_origin

from pydantic import BaseModel

from ..types import PageURI
from .schema import get_base_type


def serialize_for_storage(value: Any) -> Any:
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
    if isinstance(value, PageURI):
        return str(value)
    elif isinstance(value, BaseModel):
        # Use mode='json' to handle datetime serialization automatically
        return value.model_dump(mode="json")
    elif isinstance(value, list):
        return [serialize_for_storage(item) for item in value]
    elif isinstance(value, dict):
        return {k: serialize_for_storage(v) for k, v in value.items()}
    else:
        return value


def deserialize_from_storage(value: Any, field_type: Any) -> Any:
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
    base_type = get_base_type(field_type)

    # Handle PageURI conversion
    if base_type == PageURI and isinstance(value, str):
        return PageURI.parse(value)

    # Handle list types
    if get_origin(field_type) is list and isinstance(value, list):
        return _deserialize_list(value, field_type)

    # Handle single Pydantic model
    if _is_pydantic_model_type(base_type) and isinstance(value, dict):
        # Recursively deserialize the dictionary first to convert nested PageURIs
        deserialized_dict = _deserialize_pydantic_model_dict(value, base_type)
        return base_type.model_validate(deserialized_dict)

    # Handle nested dictionaries (for general dict types)
    if isinstance(value, dict) and not _is_pydantic_model_type(base_type):
        return {k: deserialize_from_storage(v, field_type) for k, v in value.items()}

    return value


def _deserialize_list(value: list[Any], field_type: Any) -> list[Any]:
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
    elif _is_pydantic_model_type(element_type):
        # Handle List[PydanticModel]
        result = []
        for item in value:
            if isinstance(item, dict):
                # Recursively deserialize the dictionary first
                deserialized_dict = _deserialize_pydantic_model_dict(item, element_type)
                result.append(element_type.model_validate(deserialized_dict))
            else:
                result.append(item)
        return result
    else:
        # Handle other list types recursively
        return [deserialize_from_storage(item, element_type) for item in value]


def _is_pydantic_model_type(type_obj: Any) -> bool:
    """Check if a type is a Pydantic model class."""
    return isinstance(type_obj, type) and issubclass(type_obj, BaseModel)


def _deserialize_pydantic_model_dict(
    data: dict[str, Any], model_class: type
) -> dict[str, Any]:
    """Recursively deserialize a dictionary that will be used to create a Pydantic model.

    This function examines the model's field types and converts nested values appropriately,
    particularly converting string URIs back to PageURI objects.

    Args:
        data: Dictionary data from storage
        model_class: The Pydantic model class that will be created

    Returns:
        Dictionary with properly deserialized values
    """
    if not hasattr(model_class, "model_fields"):
        # Not a Pydantic model, return as-is
        return data

    deserialized = {}

    for field_name, field_value in data.items():
        if field_name in model_class.model_fields:
            field_info = model_class.model_fields[field_name]
            field_type = field_info.annotation
            # Recursively deserialize this field
            deserialized[field_name] = deserialize_from_storage(field_value, field_type)
        else:
            # Field not defined in model, keep as-is
            deserialized[field_name] = field_value

    return deserialized


# Backward compatibility functions (delegating to new implementations)
def convert_page_uris_for_storage(value: Any) -> Any:
    """Convert PageURI objects to strings for database storage.

    Args:
        value: Value that may contain PageURI objects

    Returns:
        Value with PageURI objects converted to strings

    Note:
        This function is kept for backward compatibility.
        New code should use serialize_for_storage() instead.
    """
    return serialize_for_storage(value)


def convert_page_uris_from_storage(value: Any, field_type: Any) -> Any:
    """Convert strings back to PageURI objects after database retrieval.

    Args:
        value: Value from database storage
        field_type: Expected type annotation for the field

    Returns:
        Value with strings converted back to PageURI objects where appropriate

    Note:
        This function is kept for backward compatibility.
        New code should use deserialize_from_storage() instead.
    """
    return deserialize_from_storage(value, field_type)
