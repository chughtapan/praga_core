"""Praga Core - A toolkit for document retrieval and agent-based search."""

from .retriever import RetrieverAgent
from .retriever_toolkit import RetrieverToolkit
from .tool import PaginatedResponse, Tool
from .types import Document, DocumentMetadata, DocumentReference, TextDocument

__all__ = [
    # Core types
    "Document",
    "DocumentMetadata",
    "DocumentReference",
    "TextDocument",
    # Tools and toolkit
    "Tool",
    "PaginatedResponse",
    "RetrieverToolkit",
    # Retriever agent
    "RetrieverAgent",
]
