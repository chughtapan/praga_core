"""API clients for external service providers."""

from .base import (
    BaseAPIClient,
    BaseAuthManager,
    BaseCalendarClient,
    BaseDocumentsClient,
    BaseEmailClient,
    BasePeopleClient,
    BaseProviderClient,
)

__all__ = [
    "BaseAuthManager",
    "BaseAPIClient",
    "BaseEmailClient",
    "BaseCalendarClient",
    "BasePeopleClient",
    "BaseDocumentsClient",
    "BaseProviderClient",
]
