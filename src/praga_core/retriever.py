import abc
from typing import List

from praga_core.types import PageReference


class RetrieverAgentBase(abc.ABC):

    @abc.abstractmethod
    def search(self, query: str) -> List[PageReference]:
        """Search for documents matching the query."""
