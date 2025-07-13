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
                    personFields="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,photos,urls,memberships,metadata",
                )
                .execute()
            ),
        )
        return dict(result)

    async def search_contacts(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Google contacts."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .searchContacts(
                    query=query,
                    pageSize=max_results,
                    pageToken=page_token,
                    readMask="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,photos,urls,memberships,metadata",
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
                    personFields="names,emailAddresses,phoneNumbers,organizations,addresses,birthdays,photos,urls,memberships,metadata",
                )
                .execute()
            ),
        )
        return dict(result)

    async def create_contact(
        self, first_name: str, last_name: str, email: str, **additional_fields: Any
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

        # Add additional fields
        if "phone" in additional_fields:
            contact_body["phoneNumbers"] = [
                {
                    "value": additional_fields["phone"],
                    "type": "work",
                }
            ]

        if "company" in additional_fields:
            contact_body["organizations"] = [
                {
                    "name": additional_fields["company"],
                    "type": "work",
                }
            ]

        if "job_title" in additional_fields:
            if "organizations" not in contact_body:
                contact_body["organizations"] = [{}]
            contact_body["organizations"][0]["title"] = additional_fields["job_title"]

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

        # Add more update logic as needed

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._people.people()
                .updateContact(
                    resourceName=f"people/{contact_id}",
                    body=current_contact,
                    updatePersonFields="names,emailAddresses,phoneNumbers,organizations",
                )
                .execute()
            ),
        )
        return dict(result)

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a Google contact."""
        try:
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
        except Exception:
            return False

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

        # Extract phone numbers
        phones = contact_data.get("phoneNumbers", [])
        [phone["value"] for phone in phones]

        # Extract organization info
        organizations = contact_data.get("organizations", [])

        if organizations:
            org = organizations[0]
            org.get("name", "")
            org.get("title", "")
            org.get("department", "")

        # Extract addresses
        addresses = contact_data.get("addresses", [])

        for address in addresses:
            if address.get("type") == "work":
                address.get("formattedValue", "")
            elif address.get("type") == "home":
                address.get("formattedValue", "")

        # Extract photo URL
        photos = contact_data.get("photos", [])
        photos[0].get("url") if photos else None

        # Extract groups/memberships
        memberships = contact_data.get("memberships", [])
        groups = []
        for membership in memberships:
            contact_group = membership.get("contactGroupMembership", {})
            if contact_group:
                groups.append(contact_group.get("contactGroupResourceName", ""))

        # Extract metadata
        metadata = contact_data.get("metadata", {})
        person_id = metadata.get("sources", [{}])[0].get("id", "")

        return PersonPage(
            uri=page_uri,
            provider_person_id=person_id,
            source="people_api",
            first_name=first_name,
            last_name=last_name,
            email=primary_email,
            full_name=full_name,
        )
