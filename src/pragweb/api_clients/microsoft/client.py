"""Microsoft Graph API client."""

from typing import Any, Dict, Optional
from urllib.parse import urlencode

import aiohttp

from .auth import MicrosoftAuthManager

# Microsoft Graph API base URL
GRAPH_API_BASE_URL = "https://graph.microsoft.com/v1.0"


class MicrosoftGraphClient:
    """High-level client for Microsoft Graph API interactions."""

    def __init__(self, auth_manager: Optional[MicrosoftAuthManager] = None):
        self.auth_manager = auth_manager or MicrosoftAuthManager()
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "MicrosoftGraphClient":
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        if self.session:
            await self.session.close()

    def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure we have an active session."""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make a request to Microsoft Graph API."""
        # Ensure authentication
        self.auth_manager.ensure_authenticated()

        # Get session
        session = self._ensure_session()

        # Build URL
        url = f"{GRAPH_API_BASE_URL}/{endpoint.lstrip('/')}"

        # Build headers
        request_headers = self.auth_manager.get_headers()
        if headers:
            request_headers.update(headers)

        # Build query string
        if params:
            # Remove None values
            params = {k: v for k, v in params.items() if v is not None}
            if params:
                url += "?" + urlencode(params)

        # Make request
        async with session.request(
            method=method,
            url=url,
            headers=request_headers,
            json=data,
        ) as response:
            response.raise_for_status()

            # Return empty dict for 204 No Content
            if response.status == 204:
                return {}

            return dict(await response.json())

    async def get(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a GET request."""
        return await self._make_request("GET", endpoint, params=params)

    async def post(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a POST request."""
        return await self._make_request("POST", endpoint, params=params, data=data)

    async def patch(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a PATCH request."""
        return await self._make_request("PATCH", endpoint, params=params, data=data)

    async def put(
        self,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a PUT request."""
        return await self._make_request("PUT", endpoint, params=params, data=data)

    async def delete(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make a DELETE request."""
        return await self._make_request("DELETE", endpoint, params=params)

    # User Profile Methods
    async def get_user_profile(self) -> Dict[str, Any]:
        """Get the current user's profile."""
        return await self.get("me")

    # Mail Methods
    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a mail message by ID."""
        return await self.get(f"me/messages/{message_id}")

    async def list_messages(
        self,
        folder: str = "inbox",
        top: int = 10,
        skip: int = 0,
        filter_query: Optional[str] = None,
        search: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List mail messages."""
        params: Dict[str, Any] = {
            "$top": top,
            "$skip": skip,
        }

        if filter_query:
            params["$filter"] = filter_query
        if search:
            params["$search"] = search
        if order_by:
            params["$orderby"] = order_by

        return await self.get(f"me/mailFolders/{folder}/messages", params=params)

    async def send_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        """Send a mail message."""
        return await self.post("me/sendMail", data=message_data)

    async def reply_to_message(
        self, message_id: str, reply_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Reply to a mail message."""
        return await self.post(f"me/messages/{message_id}/reply", data=reply_data)

    async def mark_message_as_read(self, message_id: str) -> Dict[str, Any]:
        """Mark a message as read."""
        return await self.patch(f"me/messages/{message_id}", data={"isRead": True})

    async def mark_message_as_unread(self, message_id: str) -> Dict[str, Any]:
        """Mark a message as unread."""
        return await self.patch(f"me/messages/{message_id}", data={"isRead": False})

    # Calendar Methods
    async def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get a calendar event by ID."""
        return await self.get(f"me/events/{event_id}")

    async def list_events(
        self,
        top: int = 10,
        skip: int = 0,
        filter_query: Optional[str] = None,
        search: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List calendar events."""
        params: Dict[str, Any] = {
            "$top": top,
            "$skip": skip,
        }

        if filter_query:
            params["$filter"] = filter_query
        if search:
            params["$search"] = search
        if order_by:
            params["$orderby"] = order_by

        return await self.get("me/events", params=params)

    async def create_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a calendar event."""
        return await self.post("me/events", data=event_data)

    async def update_event(
        self, event_id: str, event_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a calendar event."""
        return await self.patch(f"me/events/{event_id}", data=event_data)

    async def delete_event(self, event_id: str) -> Dict[str, Any]:
        """Delete a calendar event."""
        return await self.delete(f"me/events/{event_id}")

    # Contacts Methods
    async def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get a contact by ID."""
        return await self.get(f"me/contacts/{contact_id}")

    async def list_contacts(
        self,
        top: int = 10,
        skip: int = 0,
        filter_query: Optional[str] = None,
        search: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List contacts."""
        params: Dict[str, Any] = {
            "$top": top,
            "$skip": skip,
        }

        if filter_query:
            params["$filter"] = filter_query
        if search:
            params["$search"] = search
        if order_by:
            params["$orderby"] = order_by

        return await self.get("me/contacts", params=params)

    async def create_contact(self, contact_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a contact."""
        return await self.post("me/contacts", data=contact_data)

    async def update_contact(
        self, contact_id: str, contact_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update a contact."""
        return await self.patch(f"me/contacts/{contact_id}", data=contact_data)

    async def delete_contact(self, contact_id: str) -> Dict[str, Any]:
        """Delete a contact."""
        return await self.delete(f"me/contacts/{contact_id}")

    # Files Methods
    async def get_drive_item(self, item_id: str) -> Dict[str, Any]:
        """Get a drive item by ID."""
        return await self.get(f"me/drive/items/{item_id}")

    async def list_drive_items(
        self,
        folder_id: str = "root",
        top: int = 10,
        skip: int = 0,
        filter_query: Optional[str] = None,
        search: Optional[str] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List drive items."""
        params: Dict[str, Any] = {
            "$top": top,
            "$skip": skip,
        }

        if filter_query:
            params["$filter"] = filter_query
        if search:
            params["$search"] = search
        if order_by:
            params["$orderby"] = order_by

        return await self.get(f"me/drive/items/{folder_id}/children", params=params)

    async def search_drive_items(
        self,
        query: str,
        top: int = 10,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Search drive items."""
        params: Dict[str, Any] = {
            "$top": top,
            "$skip": skip,
        }

        return await self.get(f"me/drive/root/search(q='{query}')", params=params)

    async def get_drive_item_content(self, item_id: str) -> bytes:
        """Get drive item content."""
        session = self._ensure_session()

        # Ensure authentication
        self.auth_manager.ensure_authenticated()

        # Get download URL
        url = f"{GRAPH_API_BASE_URL}/me/drive/items/{item_id}/content"

        # Get headers
        headers = self.auth_manager.get_headers()

        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.read()

    # Test connection
    async def test_connection(self) -> bool:
        """Test connection to Microsoft Graph API."""
        try:
            await self.get_user_profile()
            return True
        except Exception:
            return False
