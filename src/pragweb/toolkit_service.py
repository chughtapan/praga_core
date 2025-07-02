"""Toolkit-aware service base class for pragweb."""

from typing import Any, List

from praga_core import ServiceContext
from praga_core.agents import RetrieverToolkit


class ToolkitService(ServiceContext, RetrieverToolkit):
    """Service base class that provides toolkit functionality and inherits from RetrieverToolkit."""

    def __init__(self, api_client: Any = None, *args: Any, **kwargs: Any) -> None:
        # Initialize both parent classes
        ServiceContext.__init__(self, api_client, *args, **kwargs)
        RetrieverToolkit.__init__(self)

    @property
    def toolkit(self) -> RetrieverToolkit:
        """Get the main toolkit for this service (returns self)."""
        return self

    @property
    def toolkits(self) -> List[RetrieverToolkit]:
        """Return all toolkits this service provides."""
        return [self.toolkit]
