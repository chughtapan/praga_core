"""SQL-based page cache for storing and retrieving Page instances.

This package provides a PageCache class that automatically creates SQL tables
from Pydantic Page models and provides type-safe querying capabilities with
provenance tracking support.
"""

from .exceptions import CacheValidationError, PageCacheError, ProvenanceError
from .simple_core import PageCache

__all__ = ["PageCache", "PageCacheError", "ProvenanceError", "CacheValidationError"]
