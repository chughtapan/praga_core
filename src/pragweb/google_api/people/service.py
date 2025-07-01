"""People service for handling person data and page creation using Google People API."""

import hashlib
import logging
import re
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Union

from praga_core.agents import RetrieverToolkit, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from .page import PersonPage, SourceType

logger = logging.getLogger(__name__)


class PeopleService(ToolkitService):
    """Service for managing person data and PersonPage creation using Google People API.
    
    Supports three sources for people information:
    - People API (explicit)
    - Directory API (explicit) 
    - Emails (implicit)
    
    Prefers explicit sources over implicit sources.
    """

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
        page_cache = self.context.page_cache
        person_uri = PageURI(root=self.context.root, type="person", id=person_id)
        cached_person = page_cache.get_page(PersonPage, person_uri)
        
        if cached_person:
            logger.debug(f"Found existing person in cache: {person_id}")
            return cached_person

        raise RuntimeError(f"Invalid request: Person {person_id} not found.")

    def get_person_record(self, identifier: str) -> Optional[PersonPage]:
        """Get person record by trying lookup first, then create if not found.
        
        Args:
            identifier: Email address, full name, or first name to search for
            
        Returns:
            PersonPage if found or created, None if not possible to create
        """
        # First try to lookup existing record (search path - only uses page_cache)
        existing_person = self.lookup_people(identifier)
        if existing_person:
            logger.debug(f"Found existing person record for: {identifier}")
            return existing_person[0]  # Return first match
            
        # If not found, try to create new record (create path - uses all APIs)
        try:
            new_person = self.create_person(identifier)
            logger.info(f"Created new person record for: {identifier}")
            return new_person[0] if new_person else None  # Return first created
        except ValueError as e:
            logger.warning(f"Could not create person record for '{identifier}': {e}")
            return None

    def lookup_people(self, identifier: str) -> List[PersonPage]:
        """Lookup people by identifier (first name, full name, or email).
        
        SEARCH PATH: Only searches the page_cache, does not create new records.
        Returns all matching people, not just the first match.
        """
        page_cache = self.context.page_cache
        identifier_lower = identifier.lower().strip()

        # Try exact email match first (most specific)
        if self._is_email_address(identifier):
            email_matches = page_cache.find_pages_by_attribute(
                PersonPage, lambda t: t.email == identifier_lower
            )
            return email_matches

        # Try full name matches (partial/case-insensitive)
        full_name_matches = page_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.full_name.ilike(f"%{identifier_lower}%")
        )
        if full_name_matches:
            return full_name_matches

        # Try first name matches (if not already found)
        first_name_matches = page_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.first_name.ilike(f"%{identifier_lower}%")
        )
        return first_name_matches

    def create_person(self, identifier: str) -> List[PersonPage]:
        """Create person pages for a given identifier.
        
        CREATE PATH: May return multiple people if multiple email addresses are found for the same name.
        Raises ValueError if no people can be found in any API source.
        """
        # First check if person already exists (avoid duplicate work)
        existing_people = self.lookup_people(identifier)
        if existing_people:
            logger.debug(f"Person already exists for identifier: {identifier}")
            return existing_people

        # Try to extract information from various API sources
        all_person_infos: List[Dict[str, Any]] = []

        # Google People API might return multiple matches
        people_infos = self._extract_people_info_from_google_people(identifier)
        all_person_infos.extend(people_infos)

        # Directory API might find multiple matches
        directory_infos = self._extract_people_from_directory(identifier)
        all_person_infos.extend(directory_infos)

        # Gmail might find multiple email addresses
        gmail_infos = self._extract_people_from_gmail_contacts(identifier)
        all_person_infos.extend(gmail_infos)

        # Filter out non-real persons and remove duplicates based on email address
        unique_person_infos: List[Union[Dict[str, Any], Dict[str, PersonPage]]] = []
        seen_emails = set()

        for person_info in all_person_infos:
            if not person_info["email"]:  # Skip if no email
                continue

            email = person_info["email"].lower()

            # Skip if we've already seen this email
            if email in seen_emails:
                continue

            # Filter out non-real persons
            if not self._is_real_person(person_info):
                logger.debug(f"Skipping non-real person: {person_info['email']}")
                continue

            # Check for existing person with this email but different name
            existing_person_with_email = self._get_existing_person_by_email(email)
            if existing_person_with_email:
                # Check for name divergence
                existing_full_name = (
                    existing_person_with_email.full_name.lower().strip()
                    if existing_person_with_email.full_name
                    else ""
                )
                new_full_name = f"{person_info['first_name']} {person_info['last_name']}".lower().strip()

                if existing_full_name != new_full_name:
                    raise ValueError(
                        f"Name divergence detected for email {email}: "
                        f"existing='{existing_person_with_email.full_name}' vs new='{new_full_name.title()}'"
                    )

                # Same email, same name - return existing person
                logger.debug(f"Person with email {email} already exists with same name")
                unique_person_infos.append({"existing": existing_person_with_email})
            else:
                seen_emails.add(email)
                unique_person_infos.append(person_info)

        # If we can't find any real people, raise an error
        if not unique_person_infos:
            raise ValueError(
                f"Could not find any real people for '{identifier}' in any data source "
                f"(Google People, Directory, or Gmail). Cannot create person without valid data."
            )

        # Store all found people in database and return PersonPages
        created_people: List[PersonPage] = []
        for person_info in unique_person_infos:
            if "existing" in person_info:
                # Return existing person
                created_people.append(person_info["existing"])  # type: ignore
            else:
                # Create new person
                person_page = self._store_and_create_page(person_info)
                created_people.append(person_page)

        logger.info(
            f"Created/found {len(created_people)} people for identifier '{identifier}'"
        )
        return created_people

    def _extract_people_info_from_google_people(self, identifier: str) -> List[Dict[str, Any]]:
        """Extract people information from Google People API."""
        try:
            results = self.api_client.search_contacts(identifier)

            people_infos = []
            for result in results:
                person_info = self._extract_person_from_people_api(result, identifier)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Google People API: {e}")
            return []

    def _extract_people_from_directory(self, identifier: str) -> List[Dict[str, Any]]:
        """Extract people from Directory using People API searchDirectoryPeople."""
        try:
            # Use People API's searchDirectoryPeople endpoint
            people_service = self.api_client._people
            
            results = people_service.people().searchDirectoryPeople(
                query=identifier,
                readMask="names,emailAddresses",
                sources=["DIRECTORY_SOURCE_TYPE_DOMAIN_PROFILE"]
            ).execute()

            people_infos = []
            for person in results.get("people", []):
                person_info = self._extract_person_from_directory_result(person)
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Directory API: {e}")
            return []

    def _extract_people_from_gmail_contacts(self, identifier: str) -> List[Dict[str, Any]]:
        """Extract people from Gmail contacts by searching for identifier."""
        try:
            messages, _ = self.api_client.search_messages(
                f"from:{identifier} OR to:{identifier}"
            )

            people_infos = []
            for message in messages[:10]:  # Limit to first 10 messages
                message_data = self.api_client.get_message(message["id"])
                person_info = self._extract_person_from_gmail_message(
                    message_data, identifier
                )
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Gmail: {e}")
            return []

    def _extract_person_from_people_api(self, person: Dict[str, Any], identifier: str) -> Optional[Dict[str, Any]]:
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
                
            return self._parse_name_and_email(display_name, primary_email, SourceType.PEOPLE_API)
            
        except Exception as e:
            logger.debug(f"Error extracting from People API: {e}")
            return None

    def _extract_person_from_directory_result(self, person: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
                
            return self._parse_name_and_email(display_name, primary_email, SourceType.DIRECTORY_API)
            
        except Exception as e:
            logger.debug(f"Error extracting from Directory API: {e}")
            return None

    def _extract_person_from_gmail_message(self, message_data: Dict[str, Any], identifier: str) -> Optional[Dict[str, Any]]:
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
                        person_info = self._parse_name_and_email(display_name, email, SourceType.EMAILS)
                        # Only return if it matches our identifier
                        if self._matches_identifier(person_info, identifier):
                            return person_info
                            
            return None
        except Exception as e:
            logger.debug(f"Error extracting from email: {e}")
            return None

    def _parse_name_and_email(self, display_name: str, email: str, source: SourceType) -> Dict[str, Any]:
        """Parse display name and email into person info dict."""
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
            
        return {
            "first_name": first_name,
            "last_name": last_name,
            "email": email.lower(),
            "source": source,
        }

    def _matches_identifier(self, person_info: Dict[str, Any], identifier: str) -> bool:
        """Check if person info matches the search identifier."""
        identifier_lower = identifier.lower()
        
        # Check email match
        if self._is_email_address(identifier):
            return person_info["email"] == identifier_lower
            
        # Check name matches
        full_name = f"{person_info['first_name']} {person_info['last_name']}".lower()
        first_name = person_info["first_name"].lower()
        
        return (identifier_lower in full_name or 
                identifier_lower in first_name or
                first_name in identifier_lower)

    def _is_real_person(self, person_info: Dict[str, Any]) -> bool:
        """Check if person info represents a real person or automated system."""
        email = person_info["email"].lower()
        first_name = person_info["first_name"].lower()
        last_name = person_info["last_name"].lower()
        full_name = f"{first_name} {last_name}".strip()
        
        # Common automated email patterns
        automated_patterns = [
            r"no[-_]?reply", r"do[-_]?not[-_]?reply", r"noreply", r"donotreply",
            r"auto[-_]?reply", r"autoreply", r"support", r"help", r"info",
            r"admin", r"administrator", r"webmaster", r"postmaster",
            r"mail[-_]?er[-_]?daemon", r"mailer[-_]?daemon", r"daemon",
            r"bounce", r"notification", r"alert", r"automated?",
            r"system", r"robot", r"bot",
        ]
        
        # Check email and names for automated patterns
        for pattern in automated_patterns:
            if re.search(pattern, email) or re.search(pattern, full_name):
                return False
                
        # Require at least first name
        if not first_name:
            return False
            
        return True

    def _get_existing_person_by_email(self, email: str) -> Optional[PersonPage]:
        """Get existing person by email address."""
        page_cache = self.context.page_cache
        matches = page_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.email == email.lower()
        )
        return matches[0] if matches else None

    def _store_and_create_page(self, person_info: Dict[str, Any]) -> PersonPage:
        """Store person information and create PersonPage."""
        person_id = self._generate_person_id(person_info["email"])
        
        uri = PageURI(root=self.context.root, type="person", id=person_id)
        person_page = PersonPage(
            uri=uri,
            first_name=person_info["first_name"],
            last_name=person_info["last_name"],
            email=person_info["email"],
            full_name=f"{person_info['first_name']} {person_info['last_name']}".strip(),
            source_enum=person_info["source"],
        )
        
        # Store in page cache
        self.context.page_cache.store_page(person_page)
        
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
        return "PeopleToolkit"

    @tool()
    def get_person_record(self, identifier: str) -> List[PersonPage]:
        """Get person record by email, full name, or first name.
        
        Tries to lookup existing record first, then creates new record if not found.
        
        Args:
            identifier: Email address, full name, or first name to search for
            
        Returns:
            List containing PersonPage if found or created, empty list if not possible
        """
        result = self.people_service.get_person_record(identifier)
        return [result] if result else []

    @tool()
    def get_person_by_email(self, email: str) -> List[PersonPage]:
        """Get a specific person by email address.

        Args:
            email: Email address to search for
            
        Returns:
            List containing PersonPage if found, empty list otherwise
        """
        result = self.people_service._get_existing_person_by_email(email)
        return [result] if result else []

    @tool()
    def find_or_create_person(self, identifier: str) -> List[PersonPage]:
        """Find existing person or create new one if not found.

        Args:
            identifier: Name or email to search for
        """
        # Try to find existing first
        existing = self.people_service.lookup_people(identifier)
        if existing:
            return existing

        # Create new if not found
        return self.people_service.create_person(identifier)
