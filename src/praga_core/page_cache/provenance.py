"""Provenance tracking logic for page relationships."""

from typing import TYPE_CHECKING, List, Optional

from ..types import Page, PageURI
from .exceptions import ProvenanceError
from .schema import PageRelationships

if TYPE_CHECKING:
    from .core import PageCache


class ProvenanceTracker:
    """Handles provenance tracking validation and queries."""

    def __init__(self, cache: "PageCache") -> None:
        """Initialize provenance tracker.

        Args:
            cache: PageCache instance to operate on
        """
        self.cache = cache

    def validate_provenance(self, page: Page, parent_uri: PageURI) -> None:
        """Validate provenance tracking pre-checks.

        Args:
            page: The page being stored
            parent_uri: The parent URI to validate

        Raises:
            ProvenanceError: If any validation fails
        """
        # Pre-check 1: Ensure parent exists in cache
        parent_page = self.cache.get_page_by_uri_any_type(parent_uri)
        if parent_page is None:
            raise ProvenanceError(f"Parent page {parent_uri} does not exist in cache")

        # Pre-check 2: Ensure child does not already exist in cache
        child_page = self.cache.get_page_by_uri_any_type(page.uri)
        if child_page is not None:
            raise ProvenanceError(f"Child page {page.uri} already exists in cache")

        # Pre-check 3: Check that child and parent are not the same page type
        parent_type = parent_page.__class__.__name__
        child_type = page.__class__.__name__
        if parent_type == child_type:
            raise ProvenanceError(
                f"Parent and child cannot be the same page type: {parent_type}"
            )

        # Pre-check 4: Check that parent URI has a fixed version number (not 0 or negative)
        if parent_uri.version <= 0:
            raise ProvenanceError(
                f"Parent URI must have a fixed version number (>0), got: {parent_uri.version}"
            )

        # Pre-check 5: Check adding this relationship won't create a loop
        self.check_for_cycles(page.uri, parent_uri)

    def check_for_cycles(
        self,
        child_uri: PageURI,
        parent_uri: PageURI,
        visited: Optional[set[PageURI]] = None,
    ) -> None:
        """Check if adding a parent-child relationship would create a cycle.

        Args:
            child_uri: The child URI
            parent_uri: The parent URI
            visited: Set of already visited URIs (for recursion)

        Raises:
            ProvenanceError: If a cycle would be created
        """
        if visited is None:
            visited = set()

        # If we've seen this parent before, we have a cycle
        if parent_uri in visited:
            raise ProvenanceError(
                f"Adding relationship {child_uri} -> {parent_uri} would create a cycle"
            )

        visited.add(parent_uri)

        # Use relationships table to efficiently find parent of parent
        with self.cache.get_session() as session:
            parent_relationship = (
                session.query(PageRelationships)
                .filter_by(source_uri=str(parent_uri), relationship_type="parent")
                .first()
            )

            if parent_relationship:
                grandparent_uri = PageURI.parse(str(parent_relationship.target_uri))
                self.check_for_cycles(child_uri, grandparent_uri, visited.copy())

    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all pages that have the specified page as their parent.

        Args:
            parent_uri: The parent URI to find children for

        Returns:
            List of child pages
        """
        children = []

        # Use relationships table to efficiently find all children
        with self.cache.get_session() as session:
            child_relationships = (
                session.query(PageRelationships)
                .filter_by(target_uri=str(parent_uri), relationship_type="parent")
                .all()
            )

            # For each child URI, get the actual page
            for relationship in child_relationships:
                child_uri = PageURI.parse(str(relationship.source_uri))
                child_page = self.cache.get_page_by_uri_any_type(child_uri)
                if child_page:
                    children.append(child_page)

        return children

    def get_provenance_chain(self, page_uri: PageURI) -> List[Page]:
        """Get the full provenance chain for a page (from root to the specified page).

        Args:
            page_uri: The page URI to get the provenance chain for

        Returns:
            List of pages in the provenance chain, from root ancestor to the specified page
        """
        chain: List[Page] = []
        current_uri: Optional[PageURI] = page_uri

        while current_uri:
            # Get the current page
            page = self.cache.get_page_by_uri_any_type(current_uri)
            if page is None:
                break

            chain.insert(0, page)  # Insert at beginning to build chain from root

            # Use relationships table to efficiently find parent
            with self.cache.get_session() as session:
                parent_relationship = (
                    session.query(PageRelationships)
                    .filter_by(source_uri=str(current_uri), relationship_type="parent")
                    .first()
                )

                if parent_relationship:
                    current_uri = PageURI.parse(str(parent_relationship.target_uri))
                else:
                    current_uri = None

        return chain
