"""People toolkit for retrieving and managing person information."""

import logging
from typing import List

from praga_core.agents import RetrieverToolkit, tool

from ..pages.person import PersonPage
from ..services.people_service import PeopleService

logger = logging.getLogger(__name__)


class PeopleToolkit(RetrieverToolkit):
    """Toolkit for retrieving and managing person information."""

    def __init__(self, people_service: PeopleService):
        super().__init__()  # No explicit context - will use global context
        self.people_service = people_service

        logger.info("People toolkit initialized")

    @property
    def name(self) -> str:
        return "PeopleToolkit"

    @tool()
    def search_people(self, query: str) -> List[PersonPage]:
        """Search for people with comprehensive lookup strategy.

        This method will:
        1. Try exact lookup in local database first (returns all matches)
        2. Search local database with fuzzy matching (returns all matches)
        3. If nothing found locally, try to create new person by pulling from APIs:
           - Google People API
           - Gmail messages
           - Calendar events
           - Raises ValueError if no valid data found in any API

        Args:
            query: Search query - can be:
                  - Email address (e.g., "john.doe@example.com")
                  - Name (e.g., "John", "John Doe")
                  - Partial name for fuzzy matching

        Returns:
            List[PersonPage]: List of matching people

        Raises:
            ValueError: If person cannot be found locally or in any API source
        """
        logger.debug(f"Searching people for query: '{query}'")

        # Step 1: Try lookup in local database (returns all matches)
        existing_people = self.people_service.lookup_people(query)
        if existing_people:
            logger.debug(
                f"Found {len(existing_people)} people in database matching '{query}'"
            )
            return existing_people

        # Step 2: Nothing found locally, try to pull from APIs
        logger.debug(
            f"No existing people found, attempting to create person for: '{query}'"
        )
        try:
            new_people = self.people_service.create_person(query)
            logger.info(
                f"Successfully created {len(new_people)} people for '{query}': {[p.full_name for p in new_people]}"
            )
            return new_people
        except ValueError as e:
            logger.warning(f"Failed to create person for '{query}': {e}")
            # Re-raise the error so calling code knows the person couldn't be found
            raise e
