"""Microsoft Outlook-specific people client implementation."""

from typing import Any, Dict, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BasePeopleClient
from pragweb.pages import PersonPage

from .auth import MicrosoftAuthManager
from .client import MicrosoftGraphClient


class OutlookPeopleClient(BasePeopleClient):
    """Microsoft Outlook-specific people client implementation."""

    def __init__(self, auth_manager: MicrosoftAuthManager):
        self.auth_manager = auth_manager
        self.graph_client = MicrosoftGraphClient(auth_manager)

    async def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get an Outlook contact by ID."""
        return await self.graph_client.get_contact(contact_id)

    async def search_contacts(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Outlook contacts."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        return await self.graph_client.list_contacts(
            top=max_results, skip=skip, search=query, order_by="displayName"
        )

    async def list_contacts(
        self, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List Outlook contacts."""
        skip = 0
        if page_token:
            try:
                skip = int(page_token)
            except ValueError:
                skip = 0

        return await self.graph_client.list_contacts(
            top=max_results, skip=skip, order_by="displayName"
        )

    async def create_contact(
        self, first_name: str, last_name: str, email: str
    ) -> Dict[str, Any]:
        """Create a new Outlook contact."""
        contact_data = {
            "givenName": first_name,
            "surname": last_name,
            "emailAddresses": [
                {"address": email, "name": f"{first_name} {last_name}".strip()}
            ],
        }

        return await self.graph_client.create_contact(contact_data)

    async def update_contact(self, contact_id: str, **updates: Any) -> Dict[str, Any]:
        """Update an Outlook contact."""
        contact_data = {}

        if "first_name" in updates:
            contact_data["givenName"] = updates["first_name"]

        if "last_name" in updates:
            contact_data["surname"] = updates["last_name"]

        if "email" in updates:
            contact_data["emailAddresses"] = [
                {"address": updates["email"], "name": updates["email"]}
            ]

        if "phone" in updates:
            contact_data["businessPhones"] = [updates["phone"]]

        if "company" in updates:
            contact_data["companyName"] = updates["company"]

        if "job_title" in updates:
            contact_data["jobTitle"] = updates["job_title"]

        if "department" in updates:
            contact_data["department"] = updates["department"]

        return await self.graph_client.update_contact(contact_id, contact_data)

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete an Outlook contact."""
        await self.graph_client.delete_contact(contact_id)
        return True

    def parse_contact_to_person_page(
        self, contact_data: Dict[str, Any], page_uri: PageURI
    ) -> PersonPage:
        """Parse Outlook contact data to PersonPage."""
        # Extract names
        first_name = contact_data.get("givenName", "")
        last_name = contact_data.get("surname", "")
        full_name = contact_data.get("displayName", f"{first_name} {last_name}".strip())

        # Extract emails
        email_addresses = contact_data.get("emailAddresses", [])
        primary_email = ""
        secondary_emails = []

        for i, email_data in enumerate(email_addresses):
            email = email_data.get("address", "")
            if i == 0:
                primary_email = email
            else:
                secondary_emails.append(email)

        # Extract phone numbers
        phone_numbers = []
        business_phones = contact_data.get("businessPhones", [])
        home_phones = contact_data.get("homePhones", [])
        mobile_phone = contact_data.get("mobilePhone")

        phone_numbers.extend(business_phones)
        phone_numbers.extend(home_phones)
        if mobile_phone:
            phone_numbers.append(mobile_phone)

        # Extract professional information
        contact_data.get("jobTitle", "")
        contact_data.get("companyName", "")
        contact_data.get("department", "")

        # Extract addresses

        home_address_data = contact_data.get("homeAddress")
        if home_address_data:
            # Build address string from components
            address_parts = []
            if home_address_data.get("street"):
                address_parts.append(home_address_data["street"])
            if home_address_data.get("city"):
                address_parts.append(home_address_data["city"])
            if home_address_data.get("state"):
                address_parts.append(home_address_data["state"])
            if home_address_data.get("postalCode"):
                address_parts.append(home_address_data["postalCode"])
            ", ".join(address_parts)

        business_address_data = contact_data.get("businessAddress")
        if business_address_data:
            # Build address string from components
            address_parts = []
            if business_address_data.get("street"):
                address_parts.append(business_address_data["street"])
            if business_address_data.get("city"):
                address_parts.append(business_address_data["city"])
            if business_address_data.get("state"):
                address_parts.append(business_address_data["state"])
            if business_address_data.get("postalCode"):
                address_parts.append(business_address_data["postalCode"])
            ", ".join(address_parts)

        # Extract notes
        contact_data.get("personalNotes", "")

        # Extract manager
        contact_data.get("manager", "")

        # Extract categories as groups
        contact_data.get("categories", [])

        # Parse timestamps
        contact_data.get("createdDateTime")
        contact_data.get("lastModifiedDateTime")

        return PersonPage(
            uri=page_uri,
            source="contacts_api",
            first_name=first_name,
            last_name=last_name,
            email=primary_email,
            full_name=full_name,
        )
