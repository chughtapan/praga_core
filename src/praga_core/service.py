"""Abstract service interface for praga_core."""

from abc import ABC, abstractmethod


class Service(ABC):
    """Abstract service interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Service name for registration."""
