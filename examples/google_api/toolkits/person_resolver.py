"""Person resolution utilities for resolving names/emails to email addresses."""

import logging
from typing import List, Optional

from toolkits.utils import is_email_address

from praga_core.context import ServerContext

logger = logging.getLogger(__name__)


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
            person_page = results.results[0]
            if hasattr(person_page, "email"):
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
