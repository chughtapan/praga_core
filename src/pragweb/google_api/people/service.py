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
        # First try to lookup existing record
        existing_person = self.lookup_existing_record(identifier)
        if existing_person:
            logger.debug(f"Found existing person record for: {identifier}")
            return existing_person
            
        # If not found, try to create new record
        try:
            new_person = self.create_new_record(identifier)
            logger.info(f"Created new person record for: {identifier}")
            return new_person
        except ValueError as e:
            logger.warning(f"Could not create person record for '{identifier}': {e}")
            return None

    def lookup_existing_record(self, identifier: str) -> Optional[PersonPage]:
        """Lookup existing person record by identifier.
        
        Searches by email (exact), full name (partial), then first name (partial).
        
        Args:
            identifier: Email address, full name, or first name
            
        Returns:
            First matching PersonPage or None if not found
        """
        page_cache = self.context.page_cache
        identifier_lower = identifier.lower().strip()

        # Try exact email match first (most specific)
        if self._is_email_address(identifier):
            email_matches = page_cache.find_pages_by_attribute(
                PersonPage, lambda t: t.email == identifier_lower
            )
            if email_matches:
                return email_matches[0]

        # Try full name matches (partial/case-insensitive)
        full_name_matches = page_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.full_name.ilike(f"%{identifier_lower}%")
        )
        if full_name_matches:
            return full_name_matches[0]

        # Try first name matches
        first_name_matches = page_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.first_name.ilike(f"%{identifier_lower}%")
        )
        if first_name_matches:
            return first_name_matches[0]

        return None

    def create_new_record(self, identifier: str) -> PersonPage:
        """Create new person record from available sources.
        
        Searches sources in priority order: People API, Directory API, then Emails.
        Only creates the specifically requested person, not additional found persons.
        
        Args:
            identifier: Email address, full name, or first name
            
        Returns:
            PersonPage for the created person
            
        Raises:
            ValueError: If no valid person data can be found in any source
        """
        # Search explicit sources first (People API, Directory API)
        person_info = self._search_explicit_sources(identifier)
        
        # If not found in explicit sources, search implicit sources (Emails)
        if not person_info:
            person_info = self._search_implicit_sources(identifier)
            
        if not person_info:
            raise ValueError(
                f"Could not find person data for '{identifier}' in any source "
                f"(People API, Directory API, or Emails)"
            )
            
        # Validate person data
        if not self._is_real_person(person_info):
            raise ValueError(f"Person data for '{identifier}' appears to be automated/non-human")
            
        # Check for existing person with same email but different name
        existing_person = self._get_existing_person_by_email(person_info["email"])
        if existing_person:
            self._validate_name_consistency(existing_person, person_info)
            return existing_person
            
        # Create and store new person
        return self._create_and_store_person(person_info)

    def _search_explicit_sources(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Search explicit sources (People API, Directory API) for person information.
        
        Args:
            identifier: Search identifier
            
        Returns:
            Person info dict if found, None otherwise
        """
        # Search People API first
        person_info = self._search_people_api(identifier)
        if person_info:
            return person_info
            
        # Search Directory API second
        person_info = self._search_directory_api(identifier)
        if person_info:
            return person_info
            
        return None

    def _search_implicit_sources(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Search implicit sources (Emails) for person information.
        
        Args:
            identifier: Search identifier
            
        Returns:
            Person info dict if found, None otherwise
        """
        return self._search_emails(identifier)

    def _search_people_api(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Search Google People API for person information."""
        try:
            results = self.api_client.search_contacts(identifier)
            
            for result in results:
                person_info = self._extract_person_from_people_api(result, identifier)
                if person_info and self._matches_identifier(person_info, identifier):
                    return person_info
                    
            return None
        except Exception as e:
            logger.debug(f"Error searching People API: {e}")
            return None

    def _search_directory_api(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Search Google Directory API for person information."""
        try:
            # Use Directory API to search for users in the organization
            directory_service = self.api_client.auth_manager.get_admin_service()
            
            # Search by email if identifier looks like email
            if self._is_email_address(identifier):
                try:
                    user = directory_service.users().get(userKey=identifier).execute()
                    return self._extract_person_from_directory_user(user, SourceType.DIRECTORY_API)
                except Exception:
                    # User not found by exact email, continue to name search
                    pass
            
            # Search by name
            search_query = f"name:{identifier}"
            users_result = directory_service.users().list(
                domain=self._get_organization_domain(),
                query=search_query,
                maxResults=10
            ).execute()
            
            users = users_result.get('users', [])
            for user in users:
                person_info = self._extract_person_from_directory_user(user, SourceType.DIRECTORY_API)
                if person_info and self._matches_identifier(person_info, identifier):
                    return person_info
                    
            return None
        except Exception as e:
            logger.debug(f"Error searching Directory API: {e}")
            return None

    def _search_emails(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Search emails for person information."""
        try:
            # Search Gmail messages for the identifier
            messages, _ = self.api_client.search_messages(
                f"from:{identifier} OR to:{identifier}"
            )
            
            # Look through recent messages for person information
            for message in messages[:5]:  # Limit search to avoid creating too many records
                message_data = self.api_client.get_message(message["id"])
                person_info = self._extract_person_from_email(message_data, identifier)
                if person_info and self._matches_identifier(person_info, identifier):
                    return person_info
                    
            return None
        except Exception as e:
            logger.debug(f"Error searching emails: {e}")
            return None

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

    def _extract_person_from_directory_user(self, user: Dict[str, Any], source: SourceType) -> Dict[str, Any]:
        """Extract person information from Directory API user object."""
        primary_email = user.get("primaryEmail", "")
        name_obj = user.get("name", {})
        display_name = name_obj.get("fullName", "")
        
        # Fallback to first + last name if no display name
        if not display_name:
            first_name = name_obj.get("givenName", "")
            last_name = name_obj.get("familyName", "")
            display_name = f"{first_name} {last_name}".strip()
        
        return self._parse_name_and_email(display_name, primary_email, source)

    def _extract_person_from_email(self, message_data: Dict[str, Any], identifier: str) -> Optional[Dict[str, Any]]:
        """Extract person information from email message headers."""
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

    def _validate_name_consistency(self, existing_person: PersonPage, new_person_info: Dict[str, Any]) -> None:
        """Validate that names are consistent for the same email address."""
        existing_full_name = existing_person.full_name.lower().strip() if existing_person.full_name else ""
        new_full_name = f"{new_person_info['first_name']} {new_person_info['last_name']}".lower().strip()
        
        if existing_full_name and new_full_name and existing_full_name != new_full_name:
            raise ValueError(
                f"Name divergence detected for email {new_person_info['email']}: "
                f"existing='{existing_person.full_name}' vs new='{new_full_name.title()}'"
            )

    def _create_and_store_person(self, person_info: Dict[str, Any]) -> PersonPage:
        """Create and store a new PersonPage from person info."""
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

    def _get_organization_domain(self) -> str:
        """Get the organization domain for Directory API searches."""
        # This would typically come from configuration
        # For now, we'll extract from a known admin email or use a default
        return "example.com"  # Replace with actual domain logic

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
    def get_person_record(self, identifier: str) -> Optional[PersonPage]:
        """Get person record by email, full name, or first name.
        
        Tries to lookup existing record first, then creates new record if not found.
        
        Args:
            identifier: Email address, full name, or first name to search for
            
        Returns:
            PersonPage if found or created, None if not possible
        """
        return self.people_service.get_person_record(identifier)

    @tool()
    def get_person_by_email(self, email: str) -> Optional[PersonPage]:
        """Get a specific person by email address.

        Args:
            email: Email address to search for
            
        Returns:
            PersonPage if found, None otherwise
        """
        return self.people_service._get_existing_person_by_email(email)
