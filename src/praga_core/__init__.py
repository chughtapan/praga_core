"""
Praga Core

A framework for building document retrieval toolkits and agents for LLM applications.
Includes LLMRP (LLM Retrieval Protocol) implementation for standardized document retrieval over HTTP.
"""

from .agents import ReactAgent, RetrieverToolkit
from .context import ServerContext
from .retriever import RetrieverAgentBase
from .types import Page, PageReference, PageURI, TextPage

__version__ = "0.1.0"

__all__ = [
    "ServerContext",
    "ReactAgent",
    "RetrieverAgentBase",
    "RetrieverToolkit",
    "Page",
    "PageReference",
    "PageURI",
    "TextPage",
]
