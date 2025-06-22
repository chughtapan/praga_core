"""Utility functions for toolkit operations."""

import logging
import re
from typing import List, cast

from praga_core.global_context import get_global_context

from .people import PeopleService, PersonPage

logger = logging.getLogger(__name__)


def is_email_address(text: str) -> bool:
    """Check if a string is a valid email address format."""
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(email_pattern, text.strip()))


def resolve_person_to_emails(person_identifier: str) -> List[str]:
    """Resolve a person identifier (name or email) to an email address.

    Args:
        person_identifier: Email address or person's name

    Returns:
        Email address if found, None otherwise
    """  # Search for the person using global context
    try:
        context = get_global_context()
        service = cast(PeopleService, context.get_service("people"))
        people = service.toolkit.find_or_create_person(person_identifier)
        if not people:
            return []
        emails = [cast(PersonPage, person).email for person in people]
        return emails
    except Exception as e:
        logger.debug(f"Failed to resolve person '{person_identifier}': {e}")

    return []


def resolve_person_identifier(person_identifier: str) -> str:
    """Preprocess a person identifier (name or email) to a consistent format."""
    if is_email_address(person_identifier):
        return person_identifier
    else:
        emails = resolve_person_to_emails(person_identifier)
        if not emails:
            return person_identifier
        return " OR ".join([person_identifier] + emails)
