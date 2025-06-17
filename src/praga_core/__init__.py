"""
Praga Core

A framework for building document retrieval toolkits and agents for LLM applications.
Includes LLMRP (LLM Retrieval Protocol) implementation for standardized document retrieval over HTTP.
"""

from .types import Page, PageReference, TextPage

__version__ = "0.1.0"

__all__ = [
    "Page",
    "PageReference",
    "TextPage",
]
