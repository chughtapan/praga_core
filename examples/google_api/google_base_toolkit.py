"""Base toolkit for Google API integrations with common person resolution functionality."""

import re
from typing import Optional

from auth import GoogleAuthManager

from praga_core.retriever_toolkit import RetrieverToolkit


class GoogleBaseToolkit(RetrieverToolkit):
    """Base toolkit for Google API integrations with common functionality."""

    def __init__(self, secrets_dir: Optional[str] = None):
        """Initialize the base Google toolkit with authentication."""
        super().__init__()
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
            # Search for the person in contacts using People API
            results = (
                self.people_service.people()
                .searchContacts(
                    query=person_identifier, readMask="names,emailAddresses"
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
                            return emails[0]["value"]

            # If not found in contacts, try searching using service-specific fallback
            fallback_email = self._fallback_person_search(person_identifier)
            if fallback_email != person_identifier:
                return fallback_email

        except Exception as e:
            print(f"Error resolving person identifier '{person_identifier}': {e}")

        # If all else fails, return the original identifier
        # This allows the method to still work even if resolution fails
        return person_identifier

    def _fallback_person_search(self, person_identifier: str) -> str:
        """Service-specific fallback search for person resolution.

        Subclasses should override this method to implement service-specific
        person search functionality (e.g., searching emails, calendar events).

        Args:
            person_identifier: The person identifier to search for

        Returns:
            Email address if found, otherwise returns the original identifier
        """
        return person_identifier
