"""Simplified provenance tracking for page relationships."""

import logging
from typing import List, Optional, Set

from sqlalchemy.orm import Session, sessionmaker

from ..types import Page, PageURI
from .exceptions import ProvenanceError
from .registry import PageRegistry
from .schema import PageRelationships
from .storage import PageStorage

logger = logging.getLogger(__name__)


class ProvenanceManager:
    """Handles provenance tracking and relationship validation."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: PageStorage,
        registry: PageRegistry,
    ):
        self._session_factory = session_factory
        self._storage = storage
        self._registry = registry

    def validate_relationship(self, page: Page, parent_uri: PageURI) -> None:
        """Validate that a page can have the specified parent.

        Args:
            page: The page that will be stored
            parent_uri: The proposed parent URI

        Raises:
            ProvenanceError: If the relationship is invalid
        """
        self._validate_parent_exists(parent_uri)
        self._validate_child_not_exists(page.uri)
        self._validate_page_types(page, parent_uri)
        self._validate_parent_version(parent_uri)
        self._check_for_cycles(page.uri, parent_uri)

    def _validate_parent_exists(self, parent_uri: PageURI) -> None:
        """Check if parent page exists in any registered type."""
        for page_type in self._registry.registered_types:
            try:
                page = self._storage.get(page_type, parent_uri, ignore_validity=True)
                if page is not None:
                    return
            except Exception:
                continue

        raise ProvenanceError(f"Parent page {parent_uri} does not exist in cache")

    def _validate_child_not_exists(self, child_uri: PageURI) -> None:
        """Check that child page doesn't already exist."""
        for page_type in self._registry.registered_types:
            try:
                page = self._storage.get(page_type, child_uri, ignore_validity=True)
                if page is not None:
                    raise ProvenanceError(
                        f"Child page {child_uri} already exists in cache"
                    )
            except Exception:
                continue

    def _validate_page_types(self, page: Page, parent_uri: PageURI) -> None:
        """Check that child and parent are not the same page type."""
        parent_page = None
        for page_type in self._registry.registered_types:
            try:
                parent_page = self._storage.get(
                    page_type, parent_uri, ignore_validity=True
                )
                if parent_page is not None:
                    break
            except Exception:
                continue

        if parent_page is not None:
            parent_type = parent_page.__class__.__name__
            child_type = page.__class__.__name__
            if parent_type == child_type:
                raise ProvenanceError(
                    f"Parent and child cannot be the same page type: {parent_type}"
                )

    def _validate_parent_version(self, parent_uri: PageURI) -> None:
        """Check parent has valid version."""
        if parent_uri.version is None or parent_uri.version <= 0:
            raise ProvenanceError(
                f"Parent URI must have a fixed version number (>0), got: {parent_uri.version}"
            )

    def _check_for_cycles(
        self,
        child_uri: PageURI,
        parent_uri: PageURI,
        visited: Optional[Set[PageURI]] = None,
    ) -> None:
        """Check if adding this relationship would create a cycle."""
        if visited is None:
            visited = set()

        if parent_uri in visited:
            raise ProvenanceError(
                f"Adding {child_uri} -> {parent_uri} would create a cycle"
            )

        visited.add(parent_uri)

        # Check if parent has its own parent
        with self._session_factory() as session:
            parent_relationship = (
                session.query(PageRelationships)
                .filter_by(source_uri=str(parent_uri), relationship_type="parent")
                .first()
            )

            if parent_relationship:
                grandparent_uri = PageURI.parse(str(parent_relationship.target_uri))
                self._check_for_cycles(child_uri, grandparent_uri, visited.copy())

    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all child pages for a given parent."""
        children = []

        with self._session_factory() as session:
            child_relationships = (
                session.query(PageRelationships)
                .filter_by(target_uri=str(parent_uri), relationship_type="parent")
                .all()
            )

            for relationship in child_relationships:
                child_uri = PageURI.parse(str(relationship.source_uri))
                # Try to get the child page by iterating through registered types
                for page_type in self._registry.registered_types:
                    try:
                        page = self._storage.get(
                            page_type, child_uri, ignore_validity=True
                        )
                        if page is not None:
                            children.append(page)
                            break
                    except Exception:
                        continue

        return children

    def get_lineage(self, page_uri: PageURI) -> List[Page]:
        """Get the lineage chain from root to the specified page as Page objects.

        Returns the pages in order from root to child. Since cycles are prevented
        during relationship creation, this is guaranteed to be a linear chain.

        Args:
            page_uri: The URI of the page to get lineage for

        Returns:
            List of pages in order from root to child
        """
        lineage = []
        current_uri: Optional[PageURI] = page_uri

        while current_uri:
            # Try to find the page of this URI in any registered type
            page = self._find_page_by_uri(current_uri)
            if page:
                lineage.append(page)

            # Find parent relationship
            with self._session_factory() as session:
                parent_relationship = (
                    session.query(PageRelationships)
                    .filter_by(source_uri=str(current_uri), relationship_type="parent")
                    .first()
                )

                current_uri = (
                    PageURI.parse(str(parent_relationship.target_uri))
                    if parent_relationship
                    else None
                )

        # Reverse to get root-to-child order
        lineage.reverse()
        return lineage

    def _find_page_by_uri(self, uri: PageURI) -> Optional[Page]:
        """Find a page by URI across all registered types.

        Args:
            uri: The URI to look up

        Returns:
            The page if found, None otherwise
        """
        for page_type in self._registry.registered_types:
            try:
                page = self._storage.get(page_type, uri, ignore_validity=True)
                if page is not None:
                    return page
            except Exception:
                continue
        return None
