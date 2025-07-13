"""Utility functions for pragweb services."""

import logging
import re
from typing import List

from praga_core.global_context import get_global_context

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
        List of email addresses if found, empty list otherwise
    """
    try:
        context = get_global_context()
        service = context.get_service("people")
        if not service:
            return []

        # Use the new PaginatedResponse return type from PeopleService
        import asyncio

        from pragweb.services import PeopleService

        loop = asyncio.get_event_loop()
        if isinstance(service, PeopleService):
            result = loop.run_until_complete(
                service.resolve_person_identifier(person_identifier)
            )
        else:
            return []

        if not result.results:
            return []

        emails = [person.email for person in result.results if hasattr(person, "email")]
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
