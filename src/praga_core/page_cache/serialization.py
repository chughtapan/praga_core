"""Serialization utilities for converting PageURI objects to/from database storage."""

from typing import Any, get_args, get_origin

from ..types import PageURI
from .schema import get_base_type


def convert_page_uris_for_storage(value: Any) -> Any:
    """Convert PageURI objects to strings for database storage.
    
    Args:
        value: Value that may contain PageURI objects
        
    Returns:
        Value with PageURI objects converted to strings
    """
    if isinstance(value, PageURI):
        return str(value)
    elif isinstance(value, list):
        return [convert_page_uris_for_storage(item) for item in value]
    elif isinstance(value, dict):
        return {k: convert_page_uris_for_storage(v) for k, v in value.items()}
    else:
        return value


def convert_page_uris_from_storage(value: Any, field_type: Any) -> Any:
    """Convert strings back to PageURI objects after database retrieval.
    
    Args:
        value: Value from database storage
        field_type: Expected type annotation for the field
        
    Returns:
        Value with strings converted back to PageURI objects where appropriate
    """
    # Get the base type, handling Optional/Union
    base_type = get_base_type(field_type)

    if base_type == PageURI and isinstance(value, str):
        return PageURI.parse(value)
    elif get_origin(field_type) is list:
        # Handle List[PageURI]
        args = get_args(field_type)
        if args and args[0] == PageURI and isinstance(value, list):
            return [
                PageURI.parse(item) if isinstance(item, str) else item
                for item in value
            ]
    elif isinstance(value, dict):
        # Handle nested dictionaries (though less common for PageURI)
        return {
            k: convert_page_uris_from_storage(v, field_type)
            for k, v in value.items()
        }

    return value