"""Exceptions for page cache operations."""


class ProvenanceError(Exception):
    """Exception raised for provenance tracking violations."""


class PageCacheError(Exception):
    """Exception raised for general page cache errors."""
