"""
Praga Core

A framework for building web-services for LLM agents.
"""

from .agents import ReactAgent, RetrieverToolkit
from .context import ServerContext
from .global_context import (
    ContextMixin,
    ServiceContext,
    clear_global_context,
    get_global_context,
    set_global_context,
)
from .page_cache import PageCache, ProvenanceError
from .retriever import RetrieverAgentBase
from .service import Service
from .types import Page, PageReference, PageURI, TextPage

__version__ = "0.1.0"

__all__ = [
    "ServerContext",
    "ContextMixin",
    "ServiceContext",
    "Service",
    "PageCache",
    "ProvenanceError",
    "get_global_context",
    "set_global_context",
    "clear_global_context",
    "ReactAgent",
    "RetrieverAgentBase",
    "RetrieverToolkit",
    "Page",
    "PageReference",
    "PageURI",
    "TextPage",
]
