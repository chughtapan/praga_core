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
        self._docs_service = None
        self._drive_service = None

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

    def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get a Gmail thread by ID with all messages."""
        result = (
            self._gmail.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
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
            .searchContacts(
                query=query,
                readMask="names,emailAddresses",
                sources=[
                    "READ_SOURCE_TYPE_PROFILE",
                    "READ_SOURCE_TYPE_CONTACT",
                    "READ_SOURCE_TYPE_DOMAIN_CONTACT",
                ],
            )
            .execute()
        )

        return results.get("results", [])  # type: ignore

    # Google Docs Methods
    def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get a Google Docs document by ID."""
        result = self._docs.documents().get(documentId=document_id).execute()
        return result  # type: ignore

    def get_file_metadata(
        self, file_id: str, fields: str = "name,createdTime,modifiedTime,owners"
    ) -> Dict[str, Any]:
        """Get Google Drive file metadata."""
        result = self._drive.files().get(fileId=file_id, fields=fields).execute()
        return result  # type: ignore

    def search_documents(
        self,
        query: str = "",
        page_token: Optional[str] = None,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search Google Docs documents with pagination."""
        # Build Drive API query for Google Docs
        drive_query = (
            "mimeType='application/vnd.google-apps.document' and trashed=false"
        )

        if query.strip():
            # Add fullText search if query provided
            drive_query += f" and fullText contains '{query}'"

        # Search for files with pagination
        search_params = {
            "q": drive_query,
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,modifiedTime)",
            "orderBy": order_by,
        }
        if page_token:
            search_params["pageToken"] = page_token

        results = self._drive.files().list(**search_params).execute()
        files = results.get("files", [])
        next_token = results.get("nextPageToken")

        return files, next_token

    def search_documents_by_title(
        self, title_query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search Google Docs documents by title."""
        drive_query = f"mimeType='application/vnd.google-apps.document' and trashed=false and name contains '{title_query}'"

        search_params = {
            "q": drive_query,
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            search_params["pageToken"] = page_token

        results = self._drive.files().list(**search_params).execute()
        files = results.get("files", [])
        next_token = results.get("nextPageToken")

        return files, next_token

    def search_documents_by_owner(
        self, owner_email: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search Google Docs documents by owner email."""
        drive_query = f"mimeType='application/vnd.google-apps.document' and trashed=false and '{owner_email}' in owners"

        search_params = {
            "q": drive_query,
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            search_params["pageToken"] = page_token

        results = self._drive.files().list(**search_params).execute()
        files = results.get("files", [])
        next_token = results.get("nextPageToken")

        return files, next_token

    def search_recent_documents(
        self, days: int = 7, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search for recently modified Google Docs documents."""
        from datetime import datetime, timedelta

        recent_date = (datetime.now() - timedelta(days=days)).isoformat() + "Z"
        drive_query = f"mimeType='application/vnd.google-apps.document' and trashed=false and modifiedTime > '{recent_date}'"

        search_params = {
            "q": drive_query,
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,modifiedTime)",
            "orderBy": "modifiedTime desc",
        }
        if page_token:
            search_params["pageToken"] = page_token

        results = self._drive.files().list(**search_params).execute()
        files = results.get("files", [])
        next_token = results.get("nextPageToken")

        return files, next_token

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

    @property
    def _docs(self) -> Any:
        if self._docs_service is None:
            self._docs_service = self.auth_manager.get_docs_service()
        return self._docs_service

    @property
    def _drive(self) -> Any:
        if self._drive_service is None:
            self._drive_service = self.auth_manager.get_drive_service()
        return self._drive_service
