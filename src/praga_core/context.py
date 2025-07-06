from __future__ import annotations

import logging
from typing import Dict, List, Optional

from praga_core.action_executor import ActionExecutorMixin
from praga_core.retriever import RetrieverAgentBase
from praga_core.types import PageReference, SearchResponse

from .page_cache import PageCache
from .page_router import PageRouterMixin
from .service import Service

logger = logging.getLogger(__name__)


class ServerContext(PageRouterMixin, ActionExecutorMixin):
    """Central server context that acts as single source of truth for caching and state."""

    def __init__(
        self,
        root: str = "",
        cache_url: Optional[str] = None,
        _page_cache: Optional[PageCache] = None,
    ) -> None:
        """Do not use directly. Use `await ServerContext.create(...)` instead."""
        super().__init__()
        self._root = root
        self._retriever: Optional[RetrieverAgentBase] = None
        self._services: Dict[str, Service] = {}
        if _page_cache is not None:
            self._page_cache = _page_cache
        else:
            raise RuntimeError(
                "Use `await ServerContext.create(...)` to instantiate ServerContext."
            )

    @classmethod
    async def create(
        cls, root: str = "", cache_url: Optional[str] = None
    ) -> "ServerContext":
        if cache_url is None:
            cache_url = "sqlite+aiosqlite:///:memory:"
        page_cache = await PageCache.create(cache_url)
        return cls(root, cache_url, _page_cache=page_cache)

    def register_service(self, name: str, service: Service) -> None:
        """Register a service with the context."""
        if name in self._services:
            raise RuntimeError(f"Service already registered: {name}")
        self._services[name] = service
        logger.info(f"Registered service: {name}")

    def get_service(self, name: str) -> Service:
        """Get a service by name."""
        if name not in self._services:
            raise RuntimeError(f"No service registered with name: {name}")
        return self._services[name]

    @property
    def services(self) -> Dict[str, Service]:
        """Get all registered services."""
        return self._services.copy()

    async def search(
        self,
        instruction: str,
        retriever: Optional[RetrieverAgentBase] = None,
        resolve_references: bool = True,
    ) -> SearchResponse:
        """Execute search using the provided retriever."""
        active_retriever = retriever or self.retriever
        if not active_retriever:
            raise RuntimeError(
                "No RetrieverAgent available. Either set context.retriever or pass retriever parameter."
            )

        results = await self._search(instruction, active_retriever)
        if resolve_references:
            results = await self._resolve_references(results)
        return SearchResponse(results=results)

    async def _search(
        self, instruction: str, retriever: RetrieverAgentBase
    ) -> List[PageReference]:
        """Search for pages using the provided retriever.

        Args:
            instruction: The search instruction/query
            retriever: The retriever agent to use for search

        Returns:
            List[PageReference]: List of page references matching the search
        """
        results = await retriever.search(instruction)
        return results

    async def _resolve_references(
        self, results: List[PageReference]
    ) -> List[PageReference]:
        """Resolve references to pages by calling get_page."""
        uris = [ref.uri for ref in results]
        pages = await self.get_pages(uris)
        for ref, page in zip(results, pages):
            ref.page = page
        return results

    @property
    def root(self) -> str:
        """Get the root path for this context."""
        return self._root

    @property
    def page_cache(self) -> PageCache:
        """Get access to the SQL-based page cache."""
        return self._page_cache

    @property
    def retriever(self) -> Optional[RetrieverAgentBase]:
        """Get the current retriever agent."""
        return self._retriever

    @retriever.setter
    def retriever(self, retriever: RetrieverAgentBase) -> None:
        """Set the retriever agent."""
        if self._retriever is not None:
            raise RuntimeError("Retriever for this context is already set")
        self._retriever = retriever
