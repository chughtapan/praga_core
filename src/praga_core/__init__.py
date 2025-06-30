"""
Praga Core

A framework for building document retrieval toolkits and agents for LLM applications.
Includes LLMRP (LLM Retrieval Protocol) implementation for standardized document retrieval over HTTP.
"""

from .agents import OrchestratorAgent, ReactAgent, RetrieverToolkit
from .context import ServerContext
from .global_context import (
    ContextMixin,
    ServiceContext,
    clear_global_context,
    get_global_context,
    set_global_context,
)
from .page_cache import PageCache
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
    "get_global_context",
    "set_global_context",
    "clear_global_context",
    "ReactAgent",
    "OrchestratorAgent",
    "RetrieverAgentBase",
    "RetrieverToolkit",
    "Page",
    "PageReference",
    "PageURI",
    "TextPage",
]
