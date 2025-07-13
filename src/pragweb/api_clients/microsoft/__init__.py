"""Microsoft API client implementations."""

from .auth import MicrosoftAuthManager, get_microsoft_auth_manager
from .calendar import OutlookCalendarClient
from .client import MicrosoftGraphClient
from .email import OutlookEmailClient
from .people import OutlookPeopleClient
from .provider import MicrosoftDocumentsClient, MicrosoftProviderClient

__all__ = [
    "MicrosoftAuthManager",
    "get_microsoft_auth_manager",
    "MicrosoftGraphClient",
    "OutlookEmailClient",
    "OutlookCalendarClient",
    "OutlookPeopleClient",
    "MicrosoftDocumentsClient",
    "MicrosoftProviderClient",
]
