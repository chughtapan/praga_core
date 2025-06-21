"""People service for handling person data and page creation using Google People API."""

import hashlib
import logging
import re
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, TypedDict, Union

from praga_core.global_context import ContextMixin
from praga_core.types import PageURI

from ..auth import GoogleAuthManager
from ..pages.person import PersonPage

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


class PeopleService(ContextMixin):
    """Service for managing person data and PersonPage creation using Google People API."""

    def __init__(self) -> None:
        # Use singleton auth manager
        self.auth_manager = GoogleAuthManager()

        # Get Google API services
        self.people_service = self.auth_manager.get_people_service()
        self.gmail_service = self.auth_manager.get_gmail_service()
        self.calendar_service = self.auth_manager.get_calendar_service()

        # Register handler with context
        self.context.register_handler(self.name, self.handle_person_request)
        logger.info("People service initialized and handler registered")

    @property
    def root(self) -> str:
        """Get root from global context."""
        return self.context.root

    def handle_person_request(self, person_id: str) -> PersonPage:
        """Handle a person page request - get from database or create if not exists."""
        # Try to get from SQL cache first
        sql_cache = self.context.sql_cache
        assert sql_cache is not None

        # Construct URI from person_id
        person_uri = PageURI(root=self.root, type="person", id=person_id)
        cached_person = sql_cache.get_page(PersonPage, person_uri)
        if cached_person:
            logger.debug(f"Found existing person in cache: {person_id}")
            return cached_person

        raise RuntimeError(f"Invalid request: Person {person_id} not found.")

    def lookup_people(self, identifier: str) -> List[PersonPage]:
        """Lookup people by identifier (first name, full name, or email).

        Returns all matching people, not just the first match.
        """
        sql_cache = self.context.sql_cache
        if not sql_cache:
            logger.warning("No SQL cache available for people lookup")
            return []

        identifier_lower = identifier.lower().strip()

        # Try exact email match first (most specific)
        if _is_email_address(identifier):
            email_matches = sql_cache.find_pages_by_attribute(
                PersonPage, lambda t: t.email == identifier_lower
            )
            return email_matches

        # Try full name matches (partial/case-insensitive)
        full_name_matches = sql_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.full_name.ilike(f"%{identifier_lower}%")
        )
        if full_name_matches:
            return full_name_matches

        # Try first name matches (if not already found)
        first_name_matches = sql_cache.find_pages_by_attribute(
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
            "noreply",
            "no-reply",
            "donotreply",
            "do-not-reply",
            "notifications",
            "notification",
            "alerts",
            "support",
            "help",
            "admin",
            "system",
            "daemon",
            "postmaster",
            "webmaster",
            "mailer",
            "automated",
            "auto-",
            "robot",
            "bot",
            "service",
            "info@",
            "contact@",
            "hello@",
            "feedback@",
        ]

        # Check email patterns
        for pattern in automated_patterns:
            if pattern in email:
                return False

        # Common automated name patterns
        automated_name_patterns = [
            "via google docs",
            "via gmail",
            "via edstem",
            "via slack",
            "via teams",
            "via zoom",
            "notification",
            "alert",
            "system",
            "automated",
            "do not reply",
            "no reply",
        ]

        # Check name patterns
        for pattern in automated_name_patterns:
            if pattern in full_name:
                return False

        # Check for obviously fake names (single character, etc.)
        if len(first_name) <= 1 and len(last_name) <= 1:
            return False

        # Must have at least a reasonable first name
        if len(first_name) < 2:
            return False

        return True

    def _get_existing_person_by_email(self, email: str) -> Optional[PersonPage]:
        """Get existing person by email address."""
        sql_cache = self.context.sql_cache
        if not sql_cache:
            return None

        email_matches = sql_cache.find_pages_by_attribute(
            PersonPage, lambda t: t.email == email.lower()
        )
        return email_matches[0] if email_matches else None

    def _extract_people_info_from_google_people(
        self, identifier: str
    ) -> List[PersonInfo]:
        """Extract multiple people information from Google People API."""
        people_infos = []
        try:
            # Use searchContacts API
            results = (
                self.people_service.people()
                .searchContacts(query=identifier, readMask="names,emailAddresses")
                .execute()
            )

            contacts = results.get("results", [])
            for contact in contacts:
                person = contact.get("person", {})
                person_info = self._extract_person_from_people_api(person, identifier)
                if person_info:
                    people_infos.append(person_info)

        except Exception as e:
            logger.warning(f"Failed to extract people info from Google People API: {e}")

        return people_infos

    def _extract_person_from_people_api(
        self, person: Dict[str, Any], identifier: str
    ) -> Optional[PersonInfo]:
        """Extract person info from People API person object."""
        names = person.get("names", [])
        emails = person.get("emailAddresses", [])

        if not names or not emails:
            return None

        # Get primary name and email
        primary_name = names[0]
        first_name = primary_name.get("givenName", "")
        last_name = primary_name.get("familyName", "")
        primary_email = emails[0].get("value", "")

        # Skip if no email
        if not primary_email:
            return None

        # Check if this matches our identifier
        full_name = f"{first_name} {last_name}".strip()
        if (
            identifier.lower() in primary_email.lower()
            or identifier.lower() in full_name.lower()
        ):
            return {
                "first_name": first_name,
                "last_name": last_name,
                "email": primary_email,
                "source": "google_people",
            }

        return None

    def _extract_people_from_gmail_contacts(self, identifier: str) -> List[PersonInfo]:
        """Extract multiple people info from Gmail by searching emails from/to this person."""
        people_infos = []

        # Search in "from" field
        people_infos.extend(self._extract_people_from_gmail_field(identifier, "from"))

        # Search in "to" field
        people_infos.extend(self._extract_people_from_gmail_field(identifier, "to"))

        return people_infos

    def _extract_people_from_gmail_field(
        self, identifier: str, field: str
    ) -> List[PersonInfo]:
        """Extract people info from Gmail by searching a specific field (from/to)."""
        people_infos = []
        try:
            # Build appropriate Gmail search query
            if _is_email_address(identifier):
                query = f"{field}:{identifier}"
            else:
                query = f'{field}:"{identifier}"'

            results = (
                self.gmail_service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=10,  # Get more messages to find more people
                )
                .execute()
            )

            messages = results.get("messages", [])
            seen_emails = set()

            for message in messages:
                person_info = self._extract_person_from_gmail_message(
                    message["id"], field
                )
                if person_info and person_info["email"].lower() not in seen_emails:
                    seen_emails.add(person_info["email"].lower())
                    people_infos.append(person_info)

        except Exception as e:
            logger.warning(f"Failed to extract people info from Gmail {field}: {e}")

        return people_infos

    def _extract_person_from_gmail_message(
        self, message_id: str, field: str
    ) -> Optional[PersonInfo]:
        """Extract person info from a specific Gmail message."""
        try:
            message = (
                self.gmail_service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            headers = {
                h["name"]: h["value"]
                for h in message.get("payload", {}).get("headers", [])
            }

            header_value = headers.get("From" if field == "from" else "To", "")
            if header_value:
                display_name, email = parseaddr(header_value)
                if email:
                    return self._parse_name_and_email(display_name, email, "gmail")

        except Exception as e:
            logger.warning(
                f"Failed to extract person from Gmail message {message_id}: {e}"
            )

        return None

    def _extract_people_from_calendar_contacts(
        self, identifier: str
    ) -> List[PersonInfo]:
        """Extract multiple people info from Calendar by searching for events with attendees/organizers."""
        people_infos = []
        try:
            # Build appropriate Calendar search query
            query = identifier if _is_email_address(identifier) else f'"{identifier}"'

            results = (
                self.calendar_service.events()
                .list(
                    calendarId="primary",
                    q=query,
                    maxResults=10,  # Get more events to find more people
                )
                .execute()
            )

            events = results.get("items", [])
            seen_emails = set()

            for event in events:
                # Check attendees
                attendee_infos = self._extract_people_from_calendar_attendees(
                    event, identifier
                )
                for person_info in attendee_infos:
                    if person_info["email"].lower() not in seen_emails:
                        seen_emails.add(person_info["email"].lower())
                        people_infos.append(person_info)

                # Check organizer
                organizer_info = self._extract_from_calendar_organizer(
                    event, identifier
                )
                if (
                    organizer_info
                    and organizer_info["email"].lower() not in seen_emails
                ):
                    seen_emails.add(organizer_info["email"].lower())
                    people_infos.append(organizer_info)

        except Exception as e:
            logger.warning(f"Failed to extract people info from Calendar: {e}")

        return people_infos

    def _extract_people_from_calendar_attendees(
        self, event: Dict[str, Any], identifier: str
    ) -> List[PersonInfo]:
        """Extract multiple people info from calendar event attendees."""
        people_infos = []
        attendees = event.get("attendees", [])

        for attendee in attendees:
            email = attendee.get("email", "")
            display_name = attendee.get("displayName", "")

            # Check if this attendee matches our search
            if (
                email.lower() == identifier.lower()
                or display_name.lower() == identifier.lower()
                or (
                    not _is_email_address(identifier)
                    and identifier.lower() in display_name.lower()
                )
            ):

                person_info = self._parse_name_and_email(
                    display_name, email, "calendar"
                )
                people_infos.append(person_info)

        return people_infos

    def _extract_from_calendar_organizer(
        self, event: Dict[str, Any], identifier: str
    ) -> Optional[PersonInfo]:
        """Extract person info from calendar event organizer."""
        organizer = event.get("organizer", {})
        email = organizer.get("email", "")
        display_name = organizer.get("displayName", "")

        if (
            email.lower() == identifier.lower()
            or display_name.lower() == identifier.lower()
        ):

            return self._parse_name_and_email(display_name, email, "calendar")

        return None

    def _parse_name_and_email(
        self, display_name: str, email: str, source: str
    ) -> PersonInfo:
        """Parse display name and email into person info."""
        if display_name:
            parts = display_name.split()
            first_name = parts[0] if parts else ""
            last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
        else:
            # Use email prefix as fallback name
            name_part = email.split("@")[0]
            first_name = name_part.replace(".", " ").title()
            last_name = ""

        return {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "source": source,
        }

    def _store_and_create_page(self, person_info: PersonInfo) -> PersonPage:
        """Store person in database and create PersonPage."""
        person_id = self._generate_person_id(person_info["email"])
        full_name = f"{person_info['first_name']} {person_info['last_name']}".strip()

        # Create PersonPage with proper URI
        uri = PageURI(root=self.root, type=self.name, id=person_id)
        person_page = PersonPage(
            uri=uri,
            first_name=person_info["first_name"],
            last_name=person_info["last_name"],
            email=person_info["email"],
            full_name=full_name,
        )

        # Store in SQL cache
        sql_cache = self.context.sql_cache
        if sql_cache:
            sql_cache.store_page(person_page)

        logger.info(
            f"Created new person: {full_name} ({person_info['email']}) from {person_info.get('source', 'manual')}"
        )
        return person_page

    def _generate_person_id(self, email: str) -> str:
        """Generate a unique person ID based on email."""
        return hashlib.md5(email.lower().encode()).hexdigest()[:12]

    @property
    def name(self) -> str:
        return "person"


def _is_email_address(text: str) -> bool:
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, text.strip()))
