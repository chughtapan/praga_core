"""People service for handling person data and page creation using Google People API."""

import hashlib
import logging
import re
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, TypedDict, Union

from praga_core.agents import RetrieverToolkit, tool
from praga_core.types import PageURI, DEFAULT_VERSION
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from .page import PersonPage

logger = logging.getLogger(__name__)


class PersonInfo(TypedDict):
    """Type for person information dictionary."""

    first_name: str
    last_name: str
    email: str
    source: str


class PersonInfoWithExisting(TypedDict):
    """Type for person information dictionary with existing person."""

    existing: PersonPage


class PeopleService(ToolkitService):
    """Service for managing person data and PersonPage creation using Google People API."""

    def __init__(self, api_client: GoogleAPIClient) -> None:
        super().__init__()
        self.api_client = api_client

        # Register handlers using decorators
        self._register_handlers()
        logger.info("People service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        @self.context.handler("person")
        def handle_person(person_id: str) -> PersonPage:
            return self.handle_person_request(person_id)

    def handle_person_request(self, person_id: str) -> PersonPage:
        """Handle a person page request - get from database or create if not exists."""
        # Try to get from page cache first
        page_cache = self.context.page_cache

        # Construct URI from person_id
        person_uri = PageURI(root=self.context.root, type="person", id=person_id, version=DEFAULT_VERSION)
        cached_person = page_cache.get_page(PersonPage, person_uri)
        if cached_person:
            logger.debug(f"Found existing person in cache: {person_id}")
            return cached_person

        raise RuntimeError(f"Invalid request: Person {person_id} not found.")

    def lookup_people(self, identifier: str) -> List[PersonPage]:
        """Lookup people by identifier (first name, full name, or email).

        Returns all matching people, not just the first match.
        """
        page_cache = self.context.page_cache

        identifier_lower = identifier.lower().strip()

        # Try exact email match first (most specific)
        if _is_email_address(identifier):
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

        May return multiple people if multiple email addresses are found for the same name.
        Raises ValueError if no people can be found in any API source.
        """
        # First check if person already exists
        existing_people = self.lookup_people(identifier)
        if existing_people:
            logger.debug(f"Person already exists for identifier: {identifier}")
            return existing_people

        # Try to extract information from various API sources
        all_person_infos: List[PersonInfo] = []

        # Google People API might return multiple matches
        people_infos = self._extract_people_info_from_google_people(identifier)
        all_person_infos.extend(people_infos)

        # Gmail might find multiple email addresses
        gmail_infos = self._extract_people_from_gmail_contacts(identifier)
        all_person_infos.extend(gmail_infos)

        # Calendar might find multiple attendees/organizers
        calendar_infos = self._extract_people_from_calendar_contacts(identifier)
        all_person_infos.extend(calendar_infos)

        # Filter out non-real persons and remove duplicates based on email address
        unique_person_infos: List[Union[PersonInfo, PersonInfoWithExisting]] = []
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
                f"(Google People, Gmail, or Calendar). Cannot create person without valid data."
            )

        # Store all found people in database and return PersonPages
        created_people: List[PersonPage] = []
        for person_info in unique_person_infos:  # type: ignore
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

    def _is_real_person(self, person_info: PersonInfo) -> bool:
        """Check if this person info represents a real person or an automated system."""
        email = person_info["email"].lower() if person_info["email"] else ""
        first_name = (
            person_info["first_name"].lower() if person_info["first_name"] else ""
        )
        last_name = person_info["last_name"].lower() if person_info["last_name"] else ""
        full_name = f"{first_name} {last_name}".strip()

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

        # Check email for automated patterns
        for pattern in automated_patterns:
            if re.search(pattern, email):
                return False

        # Check names for automated patterns
        for pattern in automated_patterns:
            if re.search(pattern, full_name):
                return False

        # Additional checks for obvious non-person names
        if not first_name and not last_name:
            return False

        # If email looks like a person's email (contains real name parts)
        email_local = email.split("@")[0] if "@" in email else email
        if any(name in email_local for name in [first_name, last_name] if name):
            return True

        # Default to True if we can't determine it's automated
        return True

    def _get_existing_person_by_email(self, email: str) -> Optional[PersonPage]:
        """Get existing person by email address."""
        page_cache = self.context.page_cache

        matches = page_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.email == email.lower()
        )
        return matches[0] if matches else None

    def _extract_people_info_from_google_people(
        self, identifier: str
    ) -> List[PersonInfo]:
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

    def _extract_person_from_people_api(
        self, person: Dict[str, Any], identifier: str
    ) -> Optional[PersonInfo]:
        """Extract person information from People API result."""
        try:
            # Get person data
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

            # Parse the name
            return self._parse_name_and_email(
                display_name, primary_email, "google_people"
            )

        except Exception as e:
            logger.debug(f"Error parsing person from People API: {e}")
            return None

    def _extract_people_from_gmail_contacts(self, identifier: str) -> List[PersonInfo]:
        """Extract people from Gmail contacts by searching for identifier."""
        # This is a simplified version - in reality, you'd search Gmail messages
        # for the identifier and extract contact information
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

    def _extract_people_from_gmail_field(
        self, identifier: str, field: str
    ) -> List[PersonInfo]:
        """Extract people from Gmail field (From, To, Cc)."""
        try:
            messages, _ = self.api_client.search_messages(f"{field}:{identifier}")

            people_infos = []
            for message in messages[:5]:  # Limit to first 5 messages
                message_data = self.api_client.get_message(message["id"])
                person_info = self._extract_person_from_gmail_message(
                    message_data, field
                )
                if person_info:
                    people_infos.append(person_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Gmail {field}: {e}")
            return []

    def _extract_person_from_gmail_message(
        self, message_data: Dict[str, Any], field: str
    ) -> Optional[PersonInfo]:
        """Extract person information from Gmail message headers."""
        try:
            headers = message_data.get("payload", {}).get("headers", [])
            header_dict = {h["name"]: h["value"] for h in headers}

            # Extract relevant header based on field
            if field.lower() == "from":
                header_value = header_dict.get("From", "")
            elif field.lower() == "to":
                header_value = header_dict.get("To", "")
            elif field.lower() == "cc":
                header_value = header_dict.get("Cc", "")
            else:
                return None

            if not header_value:
                return None

            # Parse email address
            display_name, email = parseaddr(header_value)
            if not email:
                return None

            return self._parse_name_and_email(display_name, email, "gmail")

        except Exception as e:
            logger.debug(f"Error parsing Gmail message: {e}")
            return None

    def _extract_people_from_calendar_contacts(
        self, identifier: str
    ) -> List[PersonInfo]:
        """Extract people from Calendar events by searching for identifier."""
        try:
            # Search for events with the identifier
            query_params = {"calendarId": "primary", "q": identifier, "maxResults": 10}

            events, _ = self.api_client.search_events(query_params)

            people_infos = []
            for event in events:
                event_data = self.api_client.get_event(event["id"])

                # Extract from attendees
                attendee_infos = self._extract_people_from_calendar_attendees(
                    event_data, identifier
                )
                people_infos.extend(attendee_infos)

                # Extract from organizer
                organizer_info = self._extract_from_calendar_organizer(
                    event_data, identifier
                )
                if organizer_info:
                    people_infos.append(organizer_info)

            return people_infos
        except Exception as e:
            logger.debug(f"Error extracting people from Calendar: {e}")
            return []

    def _extract_people_from_calendar_attendees(
        self, event: Dict[str, Any], identifier: str
    ) -> List[PersonInfo]:
        """Extract people from Calendar event attendees."""
        people_infos = []

        try:
            attendees = event.get("attendees", [])
            for attendee in attendees:
                email = attendee.get("email", "")
                display_name = attendee.get("displayName", email)

                if not email:
                    continue

                # Check if this attendee matches the identifier
                if (
                    identifier.lower() in email.lower()
                    or identifier.lower() in display_name.lower()
                ):
                    person_info = self._parse_name_and_email(
                        display_name, email, "calendar"
                    )
                    people_infos.append(person_info)

        except Exception as e:
            logger.debug(f"Error parsing calendar attendees: {e}")

        return people_infos

    def _extract_from_calendar_organizer(
        self, event: Dict[str, Any], identifier: str
    ) -> Optional[PersonInfo]:
        """Extract person information from Calendar event organizer."""
        try:
            organizer = event.get("organizer", {})
            email = organizer.get("email", "")
            display_name = organizer.get("displayName", email)

            if not email:
                return None

            # Check if organizer matches the identifier
            if (
                identifier.lower() in email.lower()
                or identifier.lower() in display_name.lower()
            ):
                return self._parse_name_and_email(display_name, email, "calendar")

            return None
        except Exception as e:
            logger.debug(f"Error parsing calendar organizer: {e}")
            return None

    def _parse_name_and_email(
        self, display_name: str, email: str, source: str
    ) -> PersonInfo:
        """Parse display name and email into PersonInfo."""
        # Clean up the display name
        display_name = display_name.strip()

        # Remove email from display name if present (e.g., "John Doe <john@example.com>")
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

    def _store_and_create_page(self, person_info: PersonInfo) -> PersonPage:
        """Store person information and create PersonPage."""
        # Generate person ID
        person_id = self._generate_person_id(person_info["email"])

        # Create PersonPage
        uri = PageURI(root=self.context.root, type="person", id=person_id, version=DEFAULT_VERSION)
        person_page = PersonPage(
            uri=uri,
            first_name=person_info["first_name"],
            last_name=person_info["last_name"],
            email=person_info["email"],
            full_name=f"{person_info['first_name']} {person_info['last_name']}".strip(),
        )

        # Store in page cache
        self.context.page_cache.store_page(person_page)

        logger.debug(f"Created and stored person page: {person_id}")
        return person_page

    def _generate_person_id(self, email: str) -> str:
        """Generate a consistent person ID from email."""
        return hashlib.md5(email.encode()).hexdigest()

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
        super().__init__()  # No explicit context - will use global context
        self.people_service = people_service

        logger.info("People toolkit initialized")

    @property
    def name(self) -> str:
        return "PeopleToolkit"

    @tool()
    def get_person_by_email(self, email: str) -> List[PersonPage]:
        """Get a specific person by email address.

        Args:
            email: Email address to search for
        """
        existing = self.people_service._get_existing_person_by_email(email)
        return [existing] if existing else []

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


def _is_email_address(text: str) -> bool:
    """Check if text looks like an email address."""
    return "@" in text and "." in text.split("@")[-1]
