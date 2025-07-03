"""
Praga Core

A framework for building document retrieval toolkits and agents for LLM applications.
Includes LLMRP (LLM Retrieval Protocol) implementation for standardized document retrieval over HTTP.
"""

from .agents import ReactAgent, RetrieverToolkit
from .context import ActionExecutor, ServerContext, action
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
    "ActionExecutor",
    "action",
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
