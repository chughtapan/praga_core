"""Microsoft provider client that combines all Microsoft service clients."""

from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BaseDocumentsClient, BaseProviderClient
from pragweb.pages import DocumentChunk, DocumentHeader

from .auth import MicrosoftAuthManager
from .calendar import OutlookCalendarClient
from .client import MicrosoftGraphClient
from .email import OutlookEmailClient
from .people import OutlookPeopleClient


class MicrosoftDocumentsClient(BaseDocumentsClient):
    """Placeholder Microsoft documents client (OneDrive/SharePoint)."""

    def __init__(self, auth_manager: MicrosoftAuthManager):
        self.auth_manager = auth_manager
        self.graph_client = MicrosoftGraphClient(auth_manager)

    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get a OneDrive document by ID."""
        return await self.graph_client.get_drive_item(document_id)

    async def list_documents(
        self, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List OneDrive documents."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        return await self.graph_client.list_drive_items(
            folder_id="root",
            top=max_results,
            skip=skip,
            order_by="lastModifiedDateTime desc",
        )

    async def search_documents(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search OneDrive documents."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        return await self.graph_client.search_drive_items(
            query=query, top=max_results, skip=skip
        )

    async def get_document_content(self, document_id: str) -> str:
        """Get OneDrive document content."""
        content_bytes = await self.graph_client.get_drive_item_content(document_id)
        return content_bytes.decode("utf-8", errors="ignore")

    async def create_document(
        self, title: str, content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a OneDrive document."""
        # This would require more complex implementation
        raise NotImplementedError("Document creation not yet implemented for OneDrive")

    async def update_document(self, document_id: str, **updates: Any) -> Dict[str, Any]:
        """Update a OneDrive document."""
        # This would require more complex implementation
        raise NotImplementedError("Document update not yet implemented for OneDrive")

    async def delete_document(self, document_id: str) -> bool:
        """Delete a OneDrive document."""
        try:
            await self.graph_client.delete(f"me/drive/items/{document_id}")
            return True
        except Exception:
            return False

    async def parse_document_to_header_page(
        self, document_data: Dict[str, Any], page_uri: PageURI
    ) -> DocumentHeader:
        """Parse OneDrive document data to DocumentHeader."""
        # This would require implementation based on OneDrive file structure
        raise NotImplementedError("Document parsing not yet implemented for OneDrive")

    def parse_document_to_chunks(
        self, document_data: Dict[str, Any], header_uri: PageURI
    ) -> List[DocumentChunk]:
        """Parse OneDrive document data to DocumentChunk list."""
        # This would require implementation based on OneDrive file structure
        raise NotImplementedError("Document chunking not yet implemented for OneDrive")


class MicrosoftProviderClient(BaseProviderClient):
    """Microsoft provider client that combines all Microsoft service clients."""

    def __init__(self, auth_manager: Optional[MicrosoftAuthManager] = None):
        self._microsoft_auth_manager = auth_manager or MicrosoftAuthManager()
        super().__init__(self._microsoft_auth_manager)

        # Initialize service clients
        self._email_client = OutlookEmailClient(self._microsoft_auth_manager)
        self._calendar_client = OutlookCalendarClient(self._microsoft_auth_manager)
        self._people_client = OutlookPeopleClient(self._microsoft_auth_manager)
        self._documents_client = MicrosoftDocumentsClient(self._microsoft_auth_manager)

    @property
    def email_client(self) -> OutlookEmailClient:
        """Get email client instance."""
        return self._email_client

    @property
    def calendar_client(self) -> OutlookCalendarClient:
        """Get calendar client instance."""
        return self._calendar_client

    @property
    def people_client(self) -> OutlookPeopleClient:
        """Get people client instance."""
        return self._people_client

    @property
    def documents_client(self) -> MicrosoftDocumentsClient:
        """Get documents client instance."""
        return self._documents_client

    async def test_connection(self) -> bool:
        """Test connection to Microsoft Graph APIs."""
        try:
            # Test authentication
            if not self._microsoft_auth_manager.is_authenticated():
                return False

            # Test a simple API call
            graph_client = MicrosoftGraphClient(self._microsoft_auth_manager)
            await graph_client.get_user_profile()
            return True
        except Exception:
            return False

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "microsoft"
