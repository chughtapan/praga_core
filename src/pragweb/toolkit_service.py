"""Toolkit-aware service base class for pragweb."""

from abc import abstractmethod
from typing import List

from praga_core import ServiceContext
from praga_core.agents import RetrieverToolkit


class ToolkitService(ServiceContext):
    """Service base class that provides toolkit functionality."""

    @property
    @abstractmethod
    def toolkit(self) -> RetrieverToolkit:
        """Get the main toolkit for this service."""

    @property
    def toolkits(self) -> List[RetrieverToolkit]:
        """Return all toolkits this service provides."""
        return [self.toolkit]
