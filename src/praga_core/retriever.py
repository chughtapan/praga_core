import abc
from typing import List

from praga_core.types import PageReference


class RetrieverAgentBase(abc.ABC):

    @abc.abstractmethod
    async def search(self, query: str) -> List[PageReference]:
        """Execute a search and return matching page references."""
