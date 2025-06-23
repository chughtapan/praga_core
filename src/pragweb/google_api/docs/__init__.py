"""Google Docs integration module."""

from .page import GDocChunk, GDocHeader
from .service import GoogleDocsService

__all__ = ["GDocChunk", "GDocHeader", "GoogleDocsService"]
