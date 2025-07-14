"""People orchestration service that coordinates between multiple providers."""

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Tuple

from praga_core.agents import tool
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import PersonPage
from pragweb.toolkit_service import ToolkitService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersonInfo:
    """Intermediate representation of person data from various sources.

    Used during the extraction and filtering phase before creating PersonPage objects.
    Frozen for immutability and thread safety.
    """

    first_name: str
    last_name: str
    email: str
    source: str  # "people_api", "directory_api", or "emails"

    @property
    def full_name(self) -> str:
        """Get the full name by combining first and last name."""
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}> (from {self.source})"


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
        """Register page routes with context."""
        ctx = self.context

        # Register page route handlers using page type
        @ctx.route("person", cache=True)
        async def handle_person(page_uri: PageURI) -> PersonPage:
            return await self.create_person_page(page_uri)

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
        """Get person records by trying lookup first, then create if not found."""
        existing_people = await self.search_existing_records(identifier)
        if existing_people:
            logger.debug(f"Found existing person records for: {identifier}")
            return existing_people
        try:
            new_people = await self.create_new_records(identifier)
            logger.debug(f"Created new person records for: {identifier}")
            return new_people
        except (ValueError, RuntimeError) as e:
            logger.warning(f"Failed to create person records for {identifier}: {e}")
            return []

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

        # Search comprehensively across ALL providers and ALL sources
        logger.debug(
            f"Performing comprehensive search across all providers for: {identifier}"
        )
        created_people = await self.search_across_providers(identifier)

        if created_people:
            logger.info(
                f"Created/found {len(created_people)} people for identifier '{identifier}'"
            )
        else:
            raise ValueError(
                f"Could not find any real people for '{identifier}' in any data source "
                f"(Google People, Directory, Gmail, Microsoft). Cannot create person without valid data."
            )

        return created_people

    async def search_across_providers(self, identifier: str) -> List[PersonPage]:
        """Search for a person across all providers using comprehensive search."""
        all_found_people = []

        for provider_name, provider_client in self.providers.items():
            try:
                # Use comprehensive search for each provider
                provider_people = await self._search_single_provider_comprehensive(
                    identifier, provider_name, provider_client
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

    async def _search_single_provider_comprehensive(
        self, identifier: str, provider_name: str, provider_client: BaseProviderClient
    ) -> List[PersonPage]:
        """Perform comprehensive search within a single provider with smart prioritization.

        Search Strategy:
        - For names: Search implicit sources (Gmail) first, then explicit sources (People API, Directory)
        - For emails: Search explicit sources (People API, Directory) first, then implicit sources (Gmail)
        """
        all_person_infos: List[PersonInfo] = []

        # Use provider-specific search methods with smart ordering
        if "google" in provider_name.lower():
            # Determine search order based on identifier type
            is_email_search = self._is_email_address(identifier)

            if is_email_search:
                # For email searches: explicit sources first (more reliable for exact matches)
                all_person_infos.extend(
                    await self._extract_people_info_from_provider_people_api(
                        identifier, provider_client
                    )
                )
                all_person_infos.extend(
                    await self._extract_people_from_provider_directory(
                        identifier, provider_client
                    )
                )
                all_person_infos.extend(
                    await self._extract_people_from_provider_gmail(
                        identifier, provider_client
                    )
                )
            else:
                # For name searches: implicit sources first (Gmail interactions more relevant)
                all_person_infos.extend(
                    await self._extract_people_from_provider_gmail(
                        identifier, provider_client
                    )
                )
                all_person_infos.extend(
                    await self._extract_people_info_from_provider_people_api(
                        identifier, provider_client
                    )
                )
                all_person_infos.extend(
                    await self._extract_people_from_provider_directory(
                        identifier, provider_client
                    )
                )
        else:
            # For other providers (Microsoft, etc.), use basic people API search
            all_person_infos.extend(
                await self._extract_people_info_from_provider_people_api(
                    identifier, provider_client
                )
            )

        # Filter and deduplicate within this provider
        new_person_infos, existing_people = await self._filter_and_deduplicate_people(
            all_person_infos, identifier
        )

        # Create PersonPage objects for new people
        newly_created_people = await self._create_person_pages_from_infos(
            new_person_infos
        )

        return existing_people + newly_created_people

    async def _extract_people_info_from_provider_people_api(
        self, identifier: str, provider_client: BaseProviderClient
    ) -> List[PersonInfo]:
        """Extract people from any provider's People API."""
        try:
            results = await provider_client.people_client.search_contacts(identifier)

            people_infos = []
            contacts = results.get("results", [])
            if not contacts and "connections" in results:
                contacts = results.get("connections", [])

            for contact_data in contacts:
                person_info = self._extract_person_from_generic_people_api(contact_data)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from provider People API: {e}")
            return []

    async def _extract_people_from_provider_directory(
        self, identifier: str, provider_client: BaseProviderClient
    ) -> List[PersonInfo]:
        """Extract people from provider's Directory API (Google only for now)."""
        # Only Google has Directory API access
        if not hasattr(provider_client, "people_client") or not hasattr(
            provider_client.people_client, "_people"
        ):
            return []

        try:
            # Use People API's searchDirectoryPeople endpoint
            people_service = provider_client.people_client._people

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                provider_client.people_client._executor,  # type: ignore[attr-defined]
                lambda: (
                    people_service.people()
                    .searchDirectoryPeople(
                        query=identifier,
                        readMask="names,emailAddresses",
                        sources=[
                            "DIRECTORY_SOURCE_TYPE_DOMAIN_CONTACT",
                            "DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE",
                        ],
                    )
                    .execute()
                ),
            )

            people_infos = []
            for person in results.get("people", []):
                person_info = self._extract_person_from_directory_result(person)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from provider Directory API: {e}")
            return []

    async def _extract_people_from_provider_gmail(
        self, identifier: str, provider_client: BaseProviderClient
    ) -> List[PersonInfo]:
        """Extract people from provider's Gmail/Email API."""
        try:
            # Check if provider has email client
            if not hasattr(provider_client, "email_client"):
                return []

            # If identifier is an email, search specifically for that email
            if self._is_email_address(identifier):
                search_result = await provider_client.email_client.search_messages(
                    f"from:{identifier} OR to:{identifier}"
                )
                messages = search_result.get("messages", [])
            else:
                # For name-based searches, perform broader searches
                search_queries = []
                identifier_clean = identifier.strip()

                # Search for quoted exact name
                search_queries.append(f'from:"{identifier_clean}"')
                search_queries.append(f'to:"{identifier_clean}"')

                # Search for name parts if it contains spaces (full name)
                if " " in identifier_clean:
                    name_parts = identifier_clean.split()
                    if len(name_parts) >= 2:
                        first_name = name_parts[0]
                        search_queries.append(f'from:"{first_name}"')
                        search_queries.append(f'to:"{first_name}"')

                # Combine all queries with OR
                combined_query = " OR ".join(f"({query})" for query in search_queries)
                search_result = await provider_client.email_client.search_messages(
                    combined_query
                )
                messages = search_result.get("messages", [])

            # Collect all email occurrences to find best display names
            email_to_names: Dict[str, List[tuple[str, str]]] = (
                {}
            )  # email -> list of (first_name, last_name) tuples

            for message in messages[:20]:  # Check more messages to find display names
                message_data = await provider_client.email_client.get_message(
                    message["id"]
                )

                # Extract people from email headers
                extracted_people = self._extract_from_gmail(message_data, identifier)

                for person_info in extracted_people:
                    if person_info and person_info.email:
                        email = person_info.email.lower()
                        if email not in email_to_names:
                            email_to_names[email] = []
                        email_to_names[email].append(
                            (person_info.first_name, person_info.last_name)
                        )

            # Now create PersonInfo objects with the best available names
            people_infos = []
            for email, name_list in email_to_names.items():
                best_name = self._find_best_name_for_email(email, name_list)

                if best_name:
                    people_infos.append(
                        PersonInfo(
                            first_name=best_name[0],
                            last_name=best_name[1],
                            email=email,
                            source="emails",
                        )
                    )

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from provider Gmail: {e}")
            return []

    def _extract_person_from_generic_people_api(
        self, contact_data: Dict[str, Any]
    ) -> Optional[PersonInfo]:
        """Extract person from generic People API result (works for Google/Microsoft)."""
        try:
            # Handle different response formats
            if "person" in contact_data:
                # Google People API format
                person_data = contact_data["person"]
            else:
                # Direct contact data format
                person_data = contact_data

            # Extract names
            names = person_data.get("names", [])
            if not names:
                # Try alternative name fields for Microsoft
                given_name = person_data.get("givenName", "")
                surname = person_data.get("surname", "")
                if given_name or surname:
                    display_name = f"{given_name} {surname}".strip()
                else:
                    return None
            else:
                primary_name = names[0]
                display_name = primary_name.get("displayName", "")

            # Extract emails
            emails = person_data.get("emailAddresses", [])
            if not emails:
                return None

            # Handle different email formats
            if isinstance(emails[0], dict):
                if "value" in emails[0]:
                    # Google format
                    primary_email = emails[0]["value"]
                elif "address" in emails[0]:
                    # Microsoft format
                    primary_email = emails[0]["address"]
                else:
                    return None
            else:
                primary_email = str(emails[0])

            if not primary_email:
                return None

            return self._parse_name_and_email(display_name, primary_email, "people_api")

        except Exception as e:
            logger.debug(f"Error extracting from generic People API: {e}")
            return None

    async def _find_existing_person_by_email(self, email: str) -> Optional[PersonPage]:
        """Find existing person in page cache by email address."""
        matches: List[PersonPage] = await (
            self.context.page_cache.find(PersonPage)
            .where(lambda t: t.email == email.lower())
            .all()
        )
        return matches[0] if matches else None

    async def _search_explicit_sources(self, identifier: str) -> List[PersonInfo]:
        """Search explicit sources (Google People API and Directory API) for the identifier."""
        all_explicit_infos = []

        # Google People API
        people_infos = await self._extract_people_info_from_google_people(identifier)
        all_explicit_infos.extend(people_infos)
        logger.debug(
            f"Found {len(people_infos)} people from Google People API for '{identifier}'"
        )

        # Directory API
        directory_infos = await self._extract_people_from_directory(identifier)
        all_explicit_infos.extend(directory_infos)
        logger.debug(
            f"Found {len(directory_infos)} people from Directory API for '{identifier}'"
        )

        return all_explicit_infos

    async def _search_implicit_sources(self, identifier: str) -> List[PersonInfo]:
        """Search implicit sources (Gmail contacts) for the identifier."""
        # Gmail contacts
        return await self._extract_people_from_gmail_contacts(identifier)

    async def _filter_and_deduplicate_people(
        self, all_person_infos: List[PersonInfo], identifier: str
    ) -> Tuple[List[PersonInfo], List[PersonPage]]:
        """Filter out non-real persons and remove duplicates based on email address."""
        new_person_infos: List[PersonInfo] = []
        existing_people: List[PersonPage] = []
        seen_emails = set()

        for person_info in all_person_infos:
            if not person_info.email:  # Skip if no email
                continue

            email = person_info.email.lower()

            # Skip if we've already seen this email
            if email in seen_emails:
                continue

            # Filter out non-real persons
            if not self._is_real_person(person_info):
                logger.debug(f"Skipping non-real person: {person_info.email}")
                continue

            # Check for existing person with this email but different name
            existing_person_with_email = await self._find_existing_person_by_email(
                email
            )
            if existing_person_with_email:
                # Check for name divergence
                self._validate_name_consistency(
                    existing_person_with_email, person_info, email
                )

                # Same email, same name - add to existing people list
                logger.debug(f"Person with email {email} already exists with same name")
                existing_people.append(existing_person_with_email)
            else:
                seen_emails.add(email)
                new_person_infos.append(person_info)

        # If we can't find any real people, raise an error
        if not new_person_infos and not existing_people:
            raise ValueError(
                f"Could not find any real people for '{identifier}' in any data source "
                f"(Google People, Directory, or Gmail). Cannot create person without valid data."
            )

        return new_person_infos, existing_people

    def _validate_name_consistency(
        self, existing_person: PersonPage, new_person_info: PersonInfo, email: str
    ) -> None:
        """Validate that names are consistent for the same email address.

        Args:
            existing_person: Existing PersonPage from cache
            new_person_info: New PersonInfo object
            email: Email address being checked

        Raises:
            ValueError: If name divergence is detected
        """
        existing_full_name = (
            existing_person.full_name.lower().strip()
            if existing_person.full_name
            else ""
        )
        new_full_name = new_person_info.full_name.lower().strip()

        if existing_full_name != new_full_name:
            raise ValueError(
                f"Name divergence detected for email {email}: "
                f"existing='{existing_person.full_name}' vs new='{new_person_info.full_name}'"
            )

    async def _create_person_pages_from_infos(
        self, new_person_infos: List[PersonInfo]
    ) -> List[PersonPage]:
        """Create PersonPage objects for new people only.

        Args:
            new_person_infos: List of PersonInfo objects for new people to create

        Returns:
            List of newly created PersonPage objects
        """
        created_people: List[PersonPage] = []

        for person_info in new_person_infos:
            person_page = await self._store_and_create_page(person_info)
            created_people.append(person_page)

        return created_people

    async def _extract_people_info_from_google_people(
        self, identifier: str
    ) -> List[PersonInfo]:
        """Extract people information from Google People API."""
        # Get the first available provider (Google)
        google_provider = None
        for provider_name, provider_client in self.providers.items():
            if "google" in provider_name.lower():
                google_provider = provider_client
                break

        if not google_provider:
            logger.debug("No Google provider available for People API search")
            return []

        try:
            results = await google_provider.people_client.search_contacts(identifier)

            people_infos = []
            contacts = results.get("results", [])

            for result in contacts:
                person_info = self._extract_person_from_people_api(result)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Google People API: {e}")
            return []

    async def _extract_people_from_directory(self, identifier: str) -> List[PersonInfo]:
        """Extract people from Directory using People API searchDirectoryPeople."""
        # Get the first available provider (Google)
        google_provider = None
        for provider_name, provider_client in self.providers.items():
            if "google" in provider_name.lower():
                google_provider = provider_client
                break

        if not google_provider:
            logger.debug("No Google provider available for Directory API search")
            return []

        try:
            # Use People API's searchDirectoryPeople endpoint
            people_service = google_provider.people_client._people  # type: ignore[attr-defined]

            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                google_provider.people_client._executor,  # type: ignore[attr-defined]
                lambda: (
                    people_service.people()
                    .searchDirectoryPeople(
                        query=identifier,
                        readMask="names,emailAddresses",
                        sources=[
                            "DIRECTORY_SOURCE_TYPE_DOMAIN_CONTACT",
                            "DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE",
                        ],
                    )
                    .execute()
                ),
            )

            people_infos = []
            for person in results.get("people", []):
                person_info = self._extract_person_from_directory_result(person)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Directory API: {e}")
            return []

    async def _extract_people_from_gmail_contacts(
        self, identifier: str
    ) -> List[PersonInfo]:
        """Extract people from Gmail contacts by searching for identifier."""
        # Get the first available provider (Google)
        google_provider = None
        for provider_name, provider_client in self.providers.items():
            if "google" in provider_name.lower():
                google_provider = provider_client
                break

        if not google_provider:
            logger.debug("No Google provider available for Gmail search")
            return []

        try:
            # Check if provider has email client
            if not hasattr(google_provider, "email_client"):
                logger.debug(
                    "Google provider doesn't have email client for Gmail search"
                )
                return []

            # If identifier is an email, search specifically for that email
            if self._is_email_address(identifier):
                search_result = await google_provider.email_client.search_messages(
                    f"from:{identifier} OR to:{identifier}"
                )
                messages = search_result.get("messages", [])
            else:
                # For name-based searches, perform broader searches to find people with matching names
                # Search in multiple ways to catch various name formats
                search_queries = []
                identifier_clean = identifier.strip()

                # Search for quoted exact name
                search_queries.append(f'from:"{identifier_clean}"')
                search_queries.append(f'to:"{identifier_clean}"')

                # Search for name parts if it contains spaces (full name)
                if " " in identifier_clean:
                    name_parts = identifier_clean.split()
                    if len(name_parts) >= 2:
                        first_name = name_parts[0]
                        search_queries.append(f'from:"{first_name}"')
                        search_queries.append(f'to:"{first_name}"')

                # Combine all queries with OR
                combined_query = " OR ".join(f"({query})" for query in search_queries)
                search_result = await google_provider.email_client.search_messages(
                    combined_query
                )
                messages = search_result.get("messages", [])

            # Collect all email occurrences to find best display names
            email_to_names: Dict[str, List[tuple[str, str]]] = (
                {}
            )  # email -> list of (first_name, last_name) tuples

            for message in messages[:20]:  # Check more messages to find display names
                message_data = await google_provider.email_client.get_message(
                    message["id"]
                )

                # Extract people from both From and To headers
                extracted_people = self._extract_from_gmail(message_data, identifier)

                for person_info in extracted_people:
                    if person_info and person_info.email:
                        email = person_info.email.lower()
                        if email not in email_to_names:
                            email_to_names[email] = []
                        email_to_names[email].append(
                            (person_info.first_name, person_info.last_name)
                        )

            # Now create PersonInfo objects with the best available names
            people_infos = []
            for email, name_list in email_to_names.items():
                best_name = self._find_best_name_for_email(email, name_list)

                if best_name:
                    people_infos.append(
                        PersonInfo(
                            first_name=best_name[0],
                            last_name=best_name[1],
                            email=email,
                            source="emails",
                        )
                    )

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Gmail: {e}")
            return []

    def _extract_person_from_people_api(
        self, person: Dict[str, Any]
    ) -> Optional[PersonInfo]:
        """Extract person information from People API result."""
        try:
            person_data = person.get("person", {})

            # Get primary name
            names = person_data.get("names", [])
            if not names:
                return None

            primary_name = names[0]
            display_name = primary_name.get("displayName", "")

            # Get primary email
            emails = person_data.get("emailAddresses", [])
            if not emails:
                return None

            primary_email = emails[0].get("value", "")
            if not primary_email:
                return None

            return self._parse_name_and_email(display_name, primary_email, "people_api")

        except Exception as e:
            logger.debug(f"Error extracting from People API: {e}")
            return None

    def _extract_person_from_directory_result(
        self, person: Dict[str, Any]
    ) -> Optional[PersonInfo]:
        """Extract person information from Directory API search result."""
        try:
            # Get primary name
            names = person.get("names", [])
            if not names:
                return None

            primary_name = names[0]
            display_name = primary_name.get("displayName", "")

            # Get primary email
            emails = person.get("emailAddresses", [])
            if not emails:
                return None

            primary_email = emails[0].get("value", "")
            if not primary_email:
                return None

            return self._parse_name_and_email(
                display_name, primary_email, "directory_api"
            )

        except Exception as e:
            logger.debug(f"Error extracting from Directory API: {e}")
            return None

    def _extract_from_gmail(
        self, message_data: Dict[str, Any], identifier: str
    ) -> List[PersonInfo]:
        """Extract all people from Gmail message headers that match the identifier."""

        headers = message_data.get("payload", {}).get("headers", [])
        header_dict = {h["name"]: h["value"] for h in headers}

        people_infos = []

        # Check From, To, and Cc headers for people
        for header_name in ["From", "To", "Cc"]:
            header_value = header_dict.get(header_name, "")
            if header_value:
                # Parse multiple addresses if present (To/Cc can have multiple)
                if "," in header_value:
                    addresses = [addr.strip() for addr in header_value.split(",")]
                else:
                    addresses = [header_value]

                for address in addresses:
                    display_name, email = parseaddr(address)
                    if email:
                        person_info = self._parse_name_and_email(
                            display_name, email, "emails"
                        )
                        if self._matches_identifier(
                            person_info, identifier
                        ) and self._is_real_person(person_info):
                            people_infos.append(person_info)

        return people_infos

    def _parse_name_and_email(
        self, display_name: str, email: str, source: str
    ) -> PersonInfo:
        """Parse display name and email into PersonInfo object."""
        display_name = display_name.strip()

        # Remove email from display name if present
        if "<" in display_name and ">" in display_name:
            display_name = display_name.split("<")[0].strip()

        # Split name into first and last
        name_parts = display_name.split() if display_name else []

        if len(name_parts) >= 2:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])
        elif len(name_parts) == 1:
            first_name = name_parts[0]
            last_name = ""
        else:
            # Use email local part as first name if no display name
            email_local = email.split("@")[0] if "@" in email else email
            first_name = email_local
            last_name = ""

        return PersonInfo(
            first_name=first_name,
            last_name=last_name,
            email=email.lower(),
            source=source,
        )

    def _matches_identifier(self, person_info: PersonInfo, identifier: str) -> bool:
        """Check if person info matches the search identifier."""
        identifier_lower = identifier.lower()

        # Check email match
        if self._is_email_address(identifier):
            return person_info.email == identifier_lower

        # Check name matches
        full_name = person_info.full_name.lower()
        first_name = person_info.first_name.lower()

        return (
            identifier_lower in full_name
            or identifier_lower in first_name
            or first_name in identifier_lower
        )

    def _is_real_person(self, person_info: PersonInfo) -> bool:
        """Check if person info represents a real person or automated system."""
        email = person_info.email.lower()
        first_name = person_info.first_name.lower()
        full_name = person_info.full_name.lower()

        # Common automated email patterns
        automated_patterns = [
            r"no[-_]?reply",
            r"do[-_]?not[-_]?reply",
            r"noreply",
            r"donotreply",
            r"auto[-_]?reply",
            r"autoreply",
            r"support",
            r"help",
            r"info",
            r"admin",
            r"administrator",
            r"webmaster",
            r"postmaster",
            r"mail[-_]?er[-_]?daemon",
            r"mailer[-_]?daemon",
            r"daemon",
            r"bounce",
            r"notification",
            r"alert",
            r"automated?",
            r"system",
            r"robot",
            r"bot",
        ]

        # Check email and names for automated patterns
        for pattern in automated_patterns:
            if re.search(pattern, email) or re.search(pattern, full_name):
                return False

        # Require at least first name
        if not first_name:
            return False

        return True

    async def _store_and_create_page(self, person_info: PersonInfo) -> PersonPage:
        """Store person information and create PersonPage."""
        person_id = self._generate_person_id(person_info.email)

        uri = await self.context.create_page_uri(PersonPage, "person", person_id)
        person_page = PersonPage(uri=uri, **person_info.__dict__)

        # Store in page cache
        await self.context.page_cache.store(person_page)

        logger.debug(f"Created and stored person page: {person_id}")
        return person_page

    def _generate_person_id(self, email: str) -> str:
        """Generate a consistent person ID from email."""
        return hashlib.md5(email.encode()).hexdigest()

    def _find_best_name_for_email(
        self, email: str, name_list: List[Tuple[str, str]]
    ) -> Optional[Tuple[str, str]]:
        """Find the best display name for an email from multiple occurrences.

        Strategy:
        1. Prefer entries with both first and last name
        2. Skip entries where the name is just the email local part
        3. Return None if no good name is found

        Args:
            email: The email address
            name_list: List of (first_name, last_name) tuples from different messages

        Returns:
            Tuple of (first_name, last_name) or None if no good name found
        """
        best_first = ""
        best_last = ""
        email_local_part = email.split("@")[0] if "@" in email else ""

        for first_name, last_name in name_list:
            # Skip if this is just the email local part (e.g., "jdoe" from "jdoe@example.com")
            if first_name == email_local_part and not last_name:
                continue

            # Full name (first + last) is always preferred
            if first_name and last_name and not best_last:
                best_first = first_name
                best_last = last_name
            # Otherwise use any real first name we find
            elif first_name and not best_first:
                best_first = first_name
                best_last = last_name

        # Only return a name if we found something better than the email local part
        if best_first and (best_last or best_first != email_local_part):
            return (best_first, best_last)

        return None

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
