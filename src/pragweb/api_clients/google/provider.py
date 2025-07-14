"""Google provider client that combines all Google service clients."""

from typing import Optional

from pragweb.api_clients.base import BaseProviderClient

from .auth import GoogleAuthManager
from .calendar import GoogleCalendarClient
from .documents import GoogleDocumentsClient
from .email import GoogleEmailClient
from .people import GooglePeopleClient


class GoogleProviderClient(BaseProviderClient):
    """Google provider client that combines all Google service clients."""

    def __init__(self, auth_manager: Optional[GoogleAuthManager] = None):
        google_auth_manager = auth_manager or GoogleAuthManager()
        super().__init__(google_auth_manager)

        # Initialize service clients
        self._email_client = GoogleEmailClient(google_auth_manager)
        self._calendar_client = GoogleCalendarClient(google_auth_manager)
        self._people_client = GooglePeopleClient(google_auth_manager)
        self._documents_client = GoogleDocumentsClient(google_auth_manager)

    @property
    def email_client(self) -> GoogleEmailClient:
        """Get email client instance."""
        return self._email_client

    @property
    def calendar_client(self) -> GoogleCalendarClient:
        """Get calendar client instance."""
        return self._calendar_client

    @property
    def people_client(self) -> GooglePeopleClient:
        """Get people client instance."""
        return self._people_client

    @property
    def documents_client(self) -> GoogleDocumentsClient:
        """Get documents client instance."""
        return self._documents_client

    async def test_connection(self) -> bool:
        """Test connection to Google APIs."""
        # Test authentication
        if not self.auth_manager.is_authenticated():
            return False

        # Test a simple API call
        await self._email_client.search_messages("", max_results=1)
        return True

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "google"
