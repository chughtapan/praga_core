"""High-level Google API client that abstracts API specifics."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

from .auth import GoogleAuthManager

_MAX_WORKERS = 10


class GoogleAPIClient:
    """High-level client for Google API interactions."""

    def __init__(self, auth_manager: Optional[GoogleAuthManager] = None):
        self.auth_manager = auth_manager or GoogleAuthManager()

        # Dedicated pool ensures we control thread lifecycle and have a bounded
        # number of per-thread service objects.
        self._executor = ThreadPoolExecutor(
            max_workers=_MAX_WORKERS, thread_name_prefix="google-api-client"
        )

    # Gmail Methods
    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a single Gmail message by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            ),
        )
        return result  # type: ignore

    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get a Gmail thread by ID with all messages."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .threads()
                .get(userId="me", id=thread_id, format="full")
                .execute()
            ),
        )
        return result  # type: ignore

    async def search_messages(
        self, query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search Gmail messages with pagination."""
        # Add inbox filter if not specified
        if "in:inbox" not in query.lower() and "in:" not in query.lower():
            query = f"{query} in:inbox" if query.strip() else "in:inbox"

        params = {"userId": "me", "q": query, "maxResults": page_size}
        if page_token:
            params["pageToken"] = page_token

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: self._gmail.users().messages().list(**params).execute()
        )
        messages = results.get("messages", [])
        next_token = results.get("nextPageToken")

        return messages, next_token

    async def get_user_profile(self) -> Dict[str, Any]:
        """Get the current user's Gmail profile."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._gmail.users().getProfile(userId="me").execute(),
        )
        return result  # type: ignore

    async def send_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
        references: Optional[str] = None,
        in_reply_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email message."""
        import base64
        from email.message import EmailMessage

        # Create message
        message = EmailMessage()
        message["To"] = ", ".join(to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = ", ".join(cc)

        # Add threading headers for replies
        if references:
            message["References"] = references
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to

        message.set_content(body)

        # Encode message
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

        # Prepare request body
        send_body = {"raw": raw_message}
        if thread_id:
            send_body["threadId"] = thread_id

        # Send message
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._gmail.users()
                .messages()
                .send(userId="me", body=send_body)
                .execute()
            ),
        )
        return result  # type: ignore

    # Calendar Methods
    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Get a single calendar event by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._calendar.events()
                .get(calendarId=calendar_id, eventId=event_id)
                .execute()
            ),
        )
        return result  # type: ignore

    async def search_events(
        self,
        query_params: Dict[str, Any],
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search calendar events with pagination (async)."""
        params = {**query_params, "maxResults": page_size}
        if page_token:
            params["pageToken"] = page_token

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: self._calendar.events().list(**params).execute()
        )
        events = results.get("items", [])
        next_token = results.get("nextPageToken")

        return events, next_token

    # People Methods
    async def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """Search contacts using People API."""
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            self._executor,
            lambda: (
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
            ),
        )

        return results.get("results", [])  # type: ignore

    # Google Docs Methods
    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get a Google Docs document by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: self._docs.documents().get(documentId=document_id).execute()
        )
        return result  # type: ignore

    async def get_file_metadata(
        self, file_id: str, fields: str = "name,createdTime,modifiedTime,owners"
    ) -> Dict[str, Any]:
        """Get Google Drive file metadata."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._drive.files().get(fileId=file_id, fields=fields).execute(),
        )
        return result  # type: ignore

    async def get_file_revisions(self, file_id: str) -> List[Dict[str, Any]]:
        """Get all revisions for a Google Drive file."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: self._drive.revisions().list(fileId=file_id).execute(),
        )
        return result.get("revisions", [])  # type: ignore

    async def get_latest_revision_id(self, file_id: str) -> Optional[str]:
        """Get the latest revision ID for a Google Drive file."""
        try:
            revisions = await self.get_file_revisions(file_id)
            if revisions:
                # Revisions are returned in chronological order, so the last one is the latest
                return revisions[-1].get("id")
            return None
        except Exception:
            # If we can't get revisions, return None to be safe
            return None

    async def check_file_revision(self, file_id: str, cached_revision_id: str) -> bool:
        """Check if the cached revision ID matches the current latest revision.

        Args:
            file_id: Google Drive file ID
            cached_revision_id: The revision ID stored in cache

        Returns:
            True if the cached revision is still current, False otherwise
        """
        try:
            current_revision_id = await self.get_latest_revision_id(file_id)
            return current_revision_id == cached_revision_id
        except Exception:
            # If we can't check, assume it's invalid to be safe
            return False

    async def search_documents(
        self,
        search_params: Dict[str, Any],
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Search Google Docs documents with pagination using flexible parameters."""
        # Start with base query for Google Docs
        drive_query_parts = [
            "mimeType='application/vnd.google-apps.document'",
            "trashed=false",
        ]

        # Add specific search criteria based on parameters
        if "query" in search_params and search_params["query"].strip():
            drive_query_parts.append(f"fullText contains '{search_params['query']}'")

        if "title_query" in search_params:
            drive_query_parts.append(f"name contains '{search_params['title_query']}'")

        if "owner_email" in search_params:
            drive_query_parts.append(f"'{search_params['owner_email']}' in owners")

        if "days" in search_params:
            from datetime import datetime, timedelta

            recent_date = (
                datetime.now() - timedelta(days=search_params["days"])
            ).isoformat() + "Z"
            drive_query_parts.append(f"modifiedTime > '{recent_date}'")

        # Combine all query parts
        drive_query = " and ".join(drive_query_parts)

        # Set up search parameters
        api_params = {
            "q": drive_query,
            "pageSize": page_size,
            "fields": "nextPageToken,files(id,name,modifiedTime)",
            "orderBy": search_params.get("order_by", "modifiedTime desc"),
        }
        if page_token:
            api_params["pageToken"] = page_token

        # Execute search
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            self._executor, lambda: self._drive.files().list(**api_params).execute()
        )
        files = results.get("files", [])
        next_token = results.get("nextPageToken")

        return files, next_token

    # Private properties for lazy loading
    @property
    def _gmail(self) -> Any:
        return self.auth_manager.get_gmail_service()

    @property
    def _calendar(self) -> Any:
        return self.auth_manager.get_calendar_service()

    @property
    def _people(self) -> Any:
        return self.auth_manager.get_people_service()

    @property
    def _docs(self) -> Any:
        return self.auth_manager.get_docs_service()

    @property
    def _drive(self) -> Any:
        return self.auth_manager.get_drive_service()
