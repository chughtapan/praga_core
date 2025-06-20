"""High-level Google API client that abstracts API specifics."""

from typing import Any, Dict, List, Optional, Tuple

from .auth import GoogleAuthManager


class GoogleAPIClient:
    """High-level client for Google API interactions."""

    def __init__(self, auth_manager: Optional[GoogleAuthManager] = None):
        self.auth_manager = auth_manager or GoogleAuthManager()

        # Lazy-load the actual Google API service objects
        self._gmail_service = None
        self._calendar_service = None
        self._people_service = None

    # Gmail Methods
    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a single Gmail message by ID."""
        result = (
            self._gmail.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        return result  # type: ignore

    def search_messages(
        self, query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search Gmail messages with pagination."""
        # Add inbox filter if not specified
        if "in:inbox" not in query.lower() and "in:" not in query.lower():
            query = f"{query} in:inbox" if query.strip() else "in:inbox"

        params = {"userId": "me", "q": query, "maxResults": page_size}
        if page_token:
            params["pageToken"] = page_token

        results = self._gmail.users().messages().list(**params).execute()
        messages = results.get("messages", [])
        next_token = results.get("nextPageToken")

        return messages, next_token

    # Calendar Methods
    def get_event(self, event_id: str, calendar_id: str = "primary") -> Dict[str, Any]:
        """Get a single calendar event by ID."""
        result = (
            self._calendar.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
        return result  # type: ignore

    def search_events(
        self,
        query_params: Dict[str, Any],
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search calendar events with pagination."""
        params = {**query_params, "maxResults": page_size}
        if page_token:
            params["pageToken"] = page_token

        results = self._calendar.events().list(**params).execute()
        events = results.get("items", [])
        next_token = results.get("nextPageToken")

        return events, next_token

    # People Methods
    def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Search contacts using People API."""
        results = (
            self._people.people()
            .searchContacts(query=query, readMask="names,emailAddresses")
            .execute()
        )

        return results.get("results", [])  # type: ignore

    # Private properties for lazy loading
    @property
    def _gmail(self) -> Any:
        if self._gmail_service is None:
            self._gmail_service = self.auth_manager.get_gmail_service()
        return self._gmail_service

    @property
    def _calendar(self) -> Any:
        if self._calendar_service is None:
            self._calendar_service = self.auth_manager.get_calendar_service()
        return self._calendar_service

    @property
    def _people(self) -> Any:
        if self._people_service is None:
            self._people_service = self.auth_manager.get_people_service()
        return self._people_service
