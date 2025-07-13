"""People orchestration service that coordinates between multiple providers."""

import logging
from typing import Dict, List, Optional

from praga_core.agents import tool
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import PersonPage
from pragweb.toolkit_service import ToolkitService

logger = logging.getLogger(__name__)


class PeopleService(ToolkitService):
    """Orchestration service for people/contacts operations across multiple providers."""

    def __init__(self, providers: Dict[str, BaseProviderClient]):
        if not providers:
            raise ValueError("PeopleService requires at least one provider")

        self.providers = providers
        super().__init__()
        self._register_handlers()
        logger.info(
            "People service initialized with providers: %s", list(providers.keys())
        )

    @property
    def name(self) -> str:
        """Service name used for registration."""
        # Unified service across all providers
        return "people"

    def _register_handlers(self) -> None:
        """Register page routes and actions with context."""
        ctx = self.context

        # Register page route handlers using page type
        @ctx.route("person", cache=True)
        async def handle_person(page_uri: PageURI) -> PersonPage:
            return await self.create_person_page(page_uri)

        # Register people actions (all actions must have a Page as first parameter)

        @ctx.action()
        async def update_contact(
            person: PersonPage,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
            email: Optional[str] = None,
            phone: Optional[str] = None,
            company: Optional[str] = None,
            job_title: Optional[str] = None,
        ) -> bool:
            """Update a contact."""
            try:
                provider = self._get_provider_for_person(person)
                if not provider:
                    return False

                updates = {}
                if first_name is not None:
                    updates["first_name"] = first_name
                if last_name is not None:
                    updates["last_name"] = last_name
                if email is not None:
                    updates["email"] = email
                if phone is not None:
                    updates["phone"] = phone
                if company is not None:
                    updates["company"] = company
                if job_title is not None:
                    updates["job_title"] = job_title

                await provider.people_client.update_contact(
                    contact_id=person.provider_person_id,
                    **updates,
                )

                return True
            except Exception as e:
                logger.error(f"Failed to update contact: {e}")
                return False

        @ctx.action()
        async def delete_contact(person: PersonPage) -> bool:
            """Delete a contact."""
            try:
                provider = self._get_provider_for_person(person)
                if not provider:
                    return False

                return await provider.people_client.delete_contact(
                    contact_id=person.provider_person_id,
                )
            except Exception as e:
                logger.error(f"Failed to delete contact: {e}")
                return False

    async def create_person_page(self, page_uri: PageURI) -> PersonPage:
        """Create a PersonPage from a URI."""
        # Extract provider and person ID from URI
        provider_name, person_id = self._parse_person_uri(page_uri)

        provider = self.providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name} not available")

        # Get person data from provider
        person_data = await provider.people_client.get_contact(person_id)

        # Parse to PersonPage
        return provider.people_client.parse_contact_to_person_page(
            person_data, page_uri
        )

    @tool()
    async def get_person_records(self, identifier: str) -> List[PersonPage]:
        """Get person records by trying lookup first, then search across providers."""
        # Try to find existing records first
        existing_people = await self.search_existing_records(identifier)
        if existing_people:
            logger.debug(f"Found existing person records for: {identifier}")
            return existing_people

        # Search across all providers if not found locally
        logger.debug(
            f"No existing records found, searching across providers for: {identifier}"
        )
        new_people = await self.search_across_providers(identifier)
        return new_people

    async def search_existing_records(self, identifier: str) -> List[PersonPage]:
        """Search for existing records in the page cache by identifier."""
        identifier_lower = identifier.lower().strip()

        # Try exact email match first
        if self._is_email_address(identifier):
            email_matches: List[PersonPage] = await (
                self.context.page_cache.find(PersonPage)
                .where(lambda t: t.email == identifier_lower)
                .all()
            )
            return email_matches

        # Try full name matches (partial/case-insensitive)
        full_name_matches: List[PersonPage] = await (
            self.context.page_cache.find(PersonPage)
            .where(lambda t: t.full_name.ilike(f"%{identifier_lower}%"))
            .all()
        )
        if full_name_matches:
            return full_name_matches

        # Try first name matches (if not already found)
        first_name_matches: List[PersonPage] = await (
            self.context.page_cache.find(PersonPage)
            .where(lambda t: t.first_name.ilike(f"%{identifier_lower}%"))
            .all()
        )
        return first_name_matches

    async def create_new_records(self, identifier: str) -> List[PersonPage]:
        """Create new person pages for a given identifier."""
        existing_people = await self.search_existing_records(identifier)
        if existing_people:
            raise RuntimeError(f"Person already exists for identifier: {identifier}")

        # For now, return empty list - this would need full implementation
        # of the complex person creation logic from the original
        logger.warning(f"Person creation not fully implemented for: {identifier}")
        return []

    async def _create_person_pages(
        self, identifier: str, provider_client: BaseProviderClient
    ) -> List[PersonPage]:
        """Create person pages for a given identifier from a specific provider."""
        found_people = []

        try:
            # Search for the person in this provider
            search_result = await provider_client.people_client.search_contacts(
                query=identifier, max_results=10
            )

            # Handle different response formats
            contacts = search_result.get("results", [])
            if not contacts and "connections" in search_result:
                contacts = search_result.get("connections", [])

            # Convert each found contact to a PersonPage
            for contact_data in contacts:
                try:
                    # Extract email address from contact data
                    email_addresses = contact_data.get("emailAddresses", [])
                    if not email_addresses:
                        continue  # Skip contacts without email addresses

                    primary_email = email_addresses[0].get("value", "").lower()
                    if not primary_email:
                        continue

                    # Create PageURI using email address as ID
                    page_uri = PageURI(
                        root=self.context.root, type="person", id=primary_email
                    )

                    # Parse to PersonPage
                    person_page = (
                        provider_client.people_client.parse_contact_to_person_page(
                            contact_data, page_uri
                        )
                    )
                    found_people.append(person_page)

                except Exception as e:
                    logger.warning(f"Failed to parse contact: {e}")
                    continue

        except Exception as e:
            logger.warning(f"Failed to search contacts: {e}")

        return found_people

    async def search_across_providers(self, identifier: str) -> List[PersonPage]:
        """Search for a person across all providers and combine results."""
        all_found_people = []

        for provider_name, provider_client in self.providers.items():
            try:
                # Use the provider-specific creation method
                provider_people = await self._create_person_pages(
                    identifier, provider_client
                )
                all_found_people.extend(provider_people)

            except Exception as e:
                logger.warning(f"Failed to search in provider {provider_name}: {e}")
                continue

        if all_found_people:
            logger.info(
                f"Found {len(all_found_people)} people across providers for: {identifier}"
            )
        else:
            logger.warning(f"No people found across providers for: {identifier}")

        return all_found_people

    def _is_email_address(self, text: str) -> bool:
        """Check if text looks like an email address."""
        return "@" in text and "." in text.split("@")[-1]

    # Note: The original PeopleService had only get_person_records as a tool.
    # Other functionality was handled through internal methods.

    def _parse_person_uri(self, page_uri: PageURI) -> tuple[str, str]:
        """Parse person URI to extract provider and person ID."""
        # Since each service instance has only one provider, use it directly
        if not self.providers:
            raise ValueError("No provider available for service")
        provider_name = list(self.providers.keys())[0]
        return provider_name, page_uri.id

    def _get_provider_for_person(
        self, person: PersonPage
    ) -> Optional[BaseProviderClient]:
        """Get provider client for a person."""
        # Since each service instance has only one provider, return it
        return list(self.providers.values())[0] if self.providers else None
