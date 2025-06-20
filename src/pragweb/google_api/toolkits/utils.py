"""Utility functions for toolkit operations."""

import logging
import re
from typing import List, Optional

from praga_core.context import ServerContext

from ..pages.person import PersonPage

logger = logging.getLogger(__name__)


def is_email_address(text: str) -> bool:
    """Check if a string is a valid email address format."""
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, text.strip()))


def resolve_person_to_email(
    person_identifier: str, context: ServerContext
) -> Optional[str]:
    """Resolve a person identifier (name or email) to an email address.

    Args:
        person_identifier: Email address or person's name
        context: Server context for searching

    Returns:
        Email address if found, None otherwise
    """
    # If it's already an email, return it
    if is_email_address(person_identifier):
        return person_identifier.strip()

    # Search for the person using context.search
    try:
        results = context.search(f"Find person {person_identifier}")
        if results.results:
            # Return the first match's email
            person_page = context.get_page(results.results[0].uri)
            if isinstance(person_page, PersonPage):
                return person_page.email
    except Exception as e:
        logger.debug(f"Failed to resolve person '{person_identifier}': {e}")

    return None


def resolve_person_to_emails(
    person_identifiers: List[str], context: ServerContext
) -> List[str]:
    """Resolve multiple person identifiers to email addresses.

    Args:
        person_identifiers: List of email addresses or person names
        context: Server context for searching

    Returns:
        List of resolved email addresses (excludes any that couldn't be resolved)
    """
    resolved_emails = []

    for identifier in person_identifiers:
        email = resolve_person_to_email(identifier, context)
        if email:
            resolved_emails.append(email)

    return resolved_emails
