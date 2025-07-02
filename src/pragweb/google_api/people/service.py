"""People service for handling person data and page creation using Google People API."""

import hashlib
import logging
import re
from dataclasses import dataclass
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Tuple

from praga_core.agents import RetrieverToolkit, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from .page import PersonPage

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
    """Service for managing person data and PersonPage creation using Google People API."""

    def __init__(self, api_client: GoogleAPIClient) -> None:
        super().__init__()
        self.api_client = api_client
        self._register_handlers()
        logger.info("People service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        @self.context.handler("person")
        def handle_person(person_id: str) -> PersonPage:
            return self.handle_person_request(person_id)

    def handle_person_request(self, person_id: str) -> PersonPage:
        """Handle a person page request - get from database or create if not exists."""
        person_uri = PageURI(root=self.context.root, type="person", id=person_id)
        cached_person = self.page_cache.get(PersonPage, person_uri)

        if cached_person:
            logger.debug(f"Found existing person in cache: {person_id}")
            return cached_person

        raise RuntimeError(f"Invalid request: Person {person_id} not yet created.")

    def get_person_records(self, identifier: str) -> List[PersonPage]:
        """Get person records by trying lookup first, then create if not found.

        Args:
            identifier: Email address, full name, or first name to search for
        """
        # First try to lookup existing record
        existing_people = self.search_existing_records(identifier)
        if existing_people:
            logger.debug(f"Found existing person records for: {identifier}")
            return existing_people

        # If not found, try to create new record
        try:
            new_people = self.create_new_records(identifier)
            logger.debug(f"Created new person records for: {identifier}")
            return new_people
        except (ValueError, RuntimeError) as e:
            logger.warning(f"Failed to create person records for {identifier}: {e}")
            return []

    def search_existing_records(self, identifier: str) -> List[PersonPage]:
        """Search for existing records in the page cache by identifier.

        Args:
            identifier: first name, full name, or email
        """
        identifier_lower = identifier.lower().strip()

        # Try exact email match first
        if self._is_email_address(identifier):
            email_matches = (
                self.page_cache.find(PersonPage)
                .where(lambda t: t.email == identifier_lower)
                .all()
            )
            return email_matches

        # Try full name matches (partial/case-insensitive)
        full_name_matches = (
            self.page_cache.find(PersonPage)
            .where(lambda t: t.full_name.ilike(f"%{identifier_lower}%"))
            .all()
        )
        if full_name_matches:
            return full_name_matches

        # Try first name matches (if not already found)
        first_name_matches = (
            self.page_cache.find(PersonPage)
            .where(lambda t: t.first_name.ilike(f"%{identifier_lower}%"))
            .all()
        )
        return first_name_matches

    def create_new_records(self, identifier: str) -> List[PersonPage]:
        """Create new person pages for a given identifier."""
        # First check if person already exists
        existing_people = self.search_existing_records(identifier)
        if existing_people:
            raise RuntimeError(f"Person already exists for identifier: {identifier}")

        # Extract information from various API sources with different ordering based on search type
        all_person_infos: List[PersonInfo] = []
        is_name_search = not self._is_email_address(identifier)

        if is_name_search:
            logger.debug(
                f"Name-based search for '{identifier}' - prioritizing implicit sources"
            )
            # For name searches: implicit sources first (emails have richer name data)
            all_person_infos.extend(self._search_implicit_sources(identifier))
            all_person_infos.extend(self._search_explicit_sources(identifier))
        else:
            logger.debug(
                f"Email-based search for '{identifier}' - prioritizing explicit sources"
            )
            # For email searches: explicit sources first (more authoritative for emails)
            all_person_infos.extend(self._search_explicit_sources(identifier))
            all_person_infos.extend(self._search_implicit_sources(identifier))

        # Process and deduplicate results
        new_person_infos, existing_people = self._filter_and_deduplicate_people(
            all_person_infos, identifier
        )

        # Create PersonPage objects for new people only
        newly_created_people = self._create_person_pages(new_person_infos)

        # Combine existing and newly created people
        created_people = existing_people + newly_created_people

        logger.info(
            f"Created/found {len(created_people)} people for identifier '{identifier}'"
        )
        return created_people

    def _search_explicit_sources(self, identifier: str) -> List[PersonInfo]:
        """Search explicit sources (Google People API and Directory API) for the identifier."""
        all_explicit_infos = []

        # Google People API
        people_infos = self._extract_people_info_from_google_people(identifier)
        all_explicit_infos.extend(people_infos)
        logger.debug(
            f"Found {len(people_infos)} people from Google People API for '{identifier}'"
        )

        # Directory API
        directory_infos = self._extract_people_from_directory(identifier)
        all_explicit_infos.extend(directory_infos)
        logger.debug(
            f"Found {len(directory_infos)} people from Directory API for '{identifier}'"
        )

        return all_explicit_infos

    def _search_implicit_sources(self, identifier: str) -> List[PersonInfo]:
        """Search implicit sources (Gmail contacts) for the identifier."""
        # Gmail contacts
        return self._extract_people_from_gmail_contacts(identifier)

    def _filter_and_deduplicate_people(
        self, all_person_infos: List[PersonInfo], identifier: str
    ) -> Tuple[List[PersonInfo], List[PersonPage]]:
        """Filter out non-real persons and remove duplicates based on email address.

        Args:
            all_person_infos: Raw PersonInfo objects from all sources
            identifier: Original search identifier for error messages

        Returns:
            Tuple (new_person_infos, existing_people)

        Raises:
            ValueError: If no valid people found or name divergence detected
        """
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
            existing_person_with_email = self._find_existing_person_by_email(email)
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

    def _find_existing_person_by_email(self, email: str) -> Optional[PersonPage]:
        """Find existing person in page cache by email address."""
        page_cache = self.context.page_cache
        matches = (
            page_cache.find(PersonPage).where(lambda t: t.email == email.lower()).all()
        )
        return matches[0] if matches else None

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

    def _create_person_pages(
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
            person_page = self._store_and_create_page(person_info)
            created_people.append(person_page)

        return created_people

    def _extract_people_info_from_google_people(
        self, identifier: str
    ) -> List[PersonInfo]:
        """Extract people information from Google People API."""
        try:
            results = self.api_client.search_contacts(identifier)

            people_infos = []
            for result in results:
                person_info = self._extract_person_from_people_api(result)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Google People API: {e}")
            return []

    def _extract_people_from_directory(self, identifier: str) -> List[PersonInfo]:
        """Extract people from Directory using People API searchDirectoryPeople."""
        try:
            # Use People API's searchDirectoryPeople endpoint
            people_service = self.api_client._people

            results = (
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

    def _extract_people_from_gmail_contacts(self, identifier: str) -> List[PersonInfo]:
        """Extract people from Gmail contacts by searching for identifier."""
        try:
            # If identifier is an email, search specifically for that email
            if self._is_email_address(identifier):
                messages, _ = self.api_client.search_messages(
                    f"from:{identifier} OR to:{identifier}"
                )
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
                messages, _ = self.api_client.search_messages(combined_query)

            people_infos = []
            seen_emails = set()

            for message in messages[:10]:  # Limit to first 10 messages
                message_data = self.api_client.get_message(message["id"])

                # Extract people from both From and To headers
                extracted_people = self._extract_from_gmail(message_data, identifier)

                for person_info in extracted_people:
                    if person_info and person_info.email not in seen_emails:
                        people_infos.append(person_info)
                        seen_emails.add(person_info.email)

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

    def _extract_person_from_gmail_message(
        self, message_data: Dict[str, Any], identifier: str
    ) -> Optional[PersonInfo]:
        """Extract person information from Gmail message headers."""
        try:
            headers = message_data.get("payload", {}).get("headers", [])
            header_dict = {h["name"]: h["value"] for h in headers}

            # Check From header first, then To header
            for header_name in ["From", "To"]:
                header_value = header_dict.get(header_name, "")
                if header_value:
                    display_name, email = parseaddr(header_value)
                    if email:
                        person_info = self._parse_name_and_email(
                            display_name, email, "emails"
                        )
                        # Only return if it matches our identifier
                        if self._matches_identifier(person_info, identifier):
                            return person_info

            return None
        except Exception as e:
            logger.debug(f"Error extracting from email: {e}")
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

    def _store_and_create_page(self, person_info: PersonInfo) -> PersonPage:
        """Store person information and create PersonPage."""
        person_id = self._generate_person_id(person_info.email)

        uri = self.context.create_page_uri(PersonPage, "person", person_id)
        person_page = PersonPage(uri=uri, **person_info.__dict__)

        # Store in page cache
        self.page_cache.store(person_page)

        logger.debug(f"Created and stored person page: {person_id}")
        return person_page

    def _generate_person_id(self, email: str) -> str:
        """Generate a consistent person ID from email."""
        return hashlib.md5(email.encode()).hexdigest()

    def _is_email_address(self, text: str) -> bool:
        """Check if text looks like an email address."""
        return "@" in text and "." in text.split("@")[-1]

    @property
    def toolkit(self) -> "PeopleToolkit":
        """Get the People toolkit for this service."""
        return PeopleToolkit(people_service=self)

    @property
    def name(self) -> str:
        return "people"


class PeopleToolkit(RetrieverToolkit):
    """Toolkit for managing people using People service."""

    def __init__(self, people_service: PeopleService):
        super().__init__()
        self.people_service = people_service
        logger.info("People toolkit initialized")

    @property
    def name(self) -> str:
        return "people_toolkit"

    @tool()
    def get_person_records(self, identifier: str) -> List[PersonPage]:
        """Get or create person records by email, full name, or first name.

        Tries to lookup existing records first, then creates new records if not found.

        Args:
            identifier: Email address, full name, or first name to search for

        Returns:
            List of PersonPage objects found or created, empty list if not possible
        """
        return self.people_service.get_person_records(identifier)
