"""Base toolkit for Google API integrations with common person resolution functionality."""

import os
import re
import sys
from typing import Optional

from praga_core.agents.toolkit import RetrieverToolkit
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import GoogleAuthManager  # noqa: E402


class GoogleBaseToolkit(RetrieverToolkit):
    """Base toolkit for Google API integrations with common functionality."""

    def __init__(self, context: ServerContext, secrets_dir: Optional[str] = None):
        """Initialize the base Google toolkit with authentication."""
        super().__init__(context)
        self.auth_manager = GoogleAuthManager(secrets_dir)

    @property
    def people_service(self):
        """Lazy initialization of People API service."""
        if not hasattr(self, "_people_service"):
            self._people_service = self.auth_manager.get_people_service()
        return self._people_service

    def _resolve_person_to_email(self, person_identifier: str) -> str:
        """Resolve a person's name or email to their email address.

        Args:
            person_identifier: Either an email address or a person's name

        Returns:
            Email address if found, otherwise returns the original identifier
        """
        # If it's already an email address, return as-is
        if re.match(
            r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", person_identifier
        ):
            return person_identifier

        try:
            results = (
                self.people_service.people()
                .searchContacts(
                    query=person_identifier,
                    readMask="names,emailAddresses",
                    sources=[
                        "READ_SOURCE_TYPE_PROFILE",
                        "READ_SOURCE_TYPE_CONTACT",
                        "READ_SOURCE_TYPE_DOMAIN_CONTACT",
                    ],
                )
                .execute()
            )
            contacts = results.get("results", [])

            if not contacts:
                results = (
                    self.people_service.people()
                    .searchDirectoryPeople(
                        query=person_identifier,
                        readMask="names,emailAddresses",
                        sources=["DIRECTORY_SOURCE_TYPE_DOMAIN_CONTACT"],
                    )
                    .execute()
                )
            contacts = results.get("results", [])

            # Look for a contact with matching name
            for result in contacts:
                person = result.get("person", {})
                names = person.get("names", [])
                emails = person.get("emailAddresses", [])

                # Check if name matches
                for name in names:
                    display_name = name.get("displayName", "").lower()
                    given_name = name.get("givenName", "").lower()
                    family_name = name.get("familyName", "").lower()

                    if (
                        person_identifier.lower() in display_name
                        or person_identifier.lower() == given_name
                        or person_identifier.lower() == family_name
                    ):
                        # Return the primary email if available
                        primary_email = next(
                            (
                                e["value"]
                                for e in emails
                                if e.get("metadata", {}).get("primary")
                            ),
                            None,
                        )
                        if primary_email:
                            return primary_email
                        elif emails:  # Return any email if no primary
                            raise NotImplementedError(
                                "Multiple emails found for person. Please specify which email to use."
                            )

        except Exception as e:
            print(f"Error resolving person identifier '{person_identifier}': {e}")
            raise e
        print(f"Unable to find email address for person '{person_identifier}'")
        return person_identifier
