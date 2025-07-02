"""SQL-based page cache for storing and retrieving Page instances.

This package provides a PageCache class that automatically creates SQL tables
from Pydantic Page models and provides type-safe querying capabilities with
provenance tracking support.
"""

from .compat import PageCache
from .exceptions import CacheValidationError, PageCacheError, ProvenanceError

__all__ = ["PageCache", "PageCacheError", "ProvenanceError", "CacheValidationError"]
