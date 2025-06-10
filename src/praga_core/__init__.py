"""Praga Core - A toolkit for document retrieval and agent-based search."""

from .format_instructions import get_agent_format_instructions
from .react_agent import DocumentReference, ReActAgent, process_agent_response
from .response import (
    AgentDocumentReference,
    AgentResponse,
    ResponseCode,
    parse_agent_response,
)
from .retriever_toolkit import RetrieverToolkit, RetrieverToolkitMeta
from .tool import PaginatedResponse, Tool
from .types import Document, DocumentMetadata, TextDocument

__all__ = [
    # Core types
    "Document",
    "DocumentMetadata",
    "TextDocument",
    # Tools and toolkit
    "Tool",
    "PaginatedResponse",
    "RetrieverToolkit",
    "RetrieverToolkitMeta",
    # ReAct agent
    "ReActAgent",
    "DocumentReference",
    "process_agent_response",
    # Response handling
    "AgentResponse",
    "AgentDocumentReference",
    "ResponseCode",
    "parse_agent_response",
    # Format instructions
    "get_agent_format_instructions",
]
