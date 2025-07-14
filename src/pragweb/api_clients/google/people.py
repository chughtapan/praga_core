"""Google-specific people client implementation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BasePeopleClient
from pragweb.pages import PersonPage

from .auth import GoogleAuthManager


class GooglePeopleClient(BasePeopleClient):
    """Google-specific people client implementation."""

    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self._executor = ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="google-people-client"
        )

    @property
    def _people(self) -> Any:
        """Get People service instance."""
        return self.auth_manager.get_people_service()

    async def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get a Google contact by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .get(
                    resourceName=f"people/{contact_id}",
                    personFields="names,emailAddresses,metadata",
                )
                .execute()
            ),
        )
        return dict(result)

    async def search_contacts(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Google contacts.

        Note: Google's searchContacts API does not support pagination via pageToken.
        If page_token is provided, this method will raise a NotImplementedError.
        """
        if page_token is not None:
            raise NotImplementedError(
                "Google People API searchContacts does not support pagination via pageToken"
            )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .searchContacts(
                    query=query,
                    pageSize=max_results,
                    readMask="names,emailAddresses,metadata",
                )
                .execute()
            ),
        )
        return dict(result)

    async def list_contacts(
        self, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List Google contacts."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .connections()
                .list(
                    resourceName="people/me",
                    pageSize=max_results,
                    pageToken=page_token,
                    personFields="names,emailAddresses,metadata",
                )
                .execute()
            ),
        )
        return dict(result)

    async def create_contact(
        self, first_name: str, last_name: str, email: str
    ) -> Dict[str, Any]:
        """Create a new Google contact."""
        contact_body = {
            "names": [
                {
                    "givenName": first_name,
                    "familyName": last_name,
                }
            ],
            "emailAddresses": [
                {
                    "value": email,
                    "type": "work",
                }
            ],
        }

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (self._people.people().createContact(body=contact_body).execute()),
        )
        return dict(result)

    async def update_contact(self, contact_id: str, **updates: Any) -> Dict[str, Any]:
        """Update a Google contact."""
        # First get the current contact
        current_contact = await self.get_contact(contact_id)

        # Apply updates
        if "first_name" in updates or "last_name" in updates:
            names = current_contact.get("names", [{}])
            if names:
                if "first_name" in updates:
                    names[0]["givenName"] = updates["first_name"]
                if "last_name" in updates:
                    names[0]["familyName"] = updates["last_name"]

        if "email" in updates:
            emails = current_contact.get("emailAddresses", [])
            if emails:
                emails[0]["value"] = updates["email"]
            else:
                current_contact["emailAddresses"] = [
                    {"value": updates["email"], "type": "work"}
                ]

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .updateContact(
                    resourceName=f"people/{contact_id}",
                    body=current_contact,
                    updatePersonFields="names,emailAddresses",
                )
                .execute()
            ),
        )
        return dict(result)

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a Google contact."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .deleteContact(resourceName=f"people/{contact_id}")
                .execute()
            ),
        )
        return True

    def parse_contact_to_person_page(
        self, contact_data: Dict[str, Any], page_uri: PageURI
    ) -> PersonPage:
        """Parse Google contact data to PersonPage."""
        # Extract names
        names = contact_data.get("names", [])
        first_name = ""
        last_name = ""
        full_name = ""

        if names:
            first_name = names[0].get("givenName", "")
            last_name = names[0].get("familyName", "")
            full_name = names[0].get("displayName", f"{first_name} {last_name}".strip())

        # Extract primary email
        emails = contact_data.get("emailAddresses", [])
        primary_email = emails[0]["value"] if emails else ""

        return PersonPage(
            uri=page_uri,
            source="people_api",
            first_name=first_name,
            last_name=last_name,
            email=primary_email,
            full_name=full_name,
        )
