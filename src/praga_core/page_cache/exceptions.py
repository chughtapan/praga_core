"""Exceptions for page cache operations."""


class ProvenanceError(Exception):
    """Exception raised for provenance tracking violations."""


class PageCacheError(Exception):
    """Exception raised for general page cache errors."""


class CacheValidationError(Exception):
    """Exception raised when cache validation fails."""
