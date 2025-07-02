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
        registry: Optional[PageRegistry] = None,
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
        # Check parent exists (using any available type)
        parent_exists = self._check_parent_exists(parent_uri)
        if not parent_exists:
            raise ProvenanceError(f"Parent page {parent_uri} does not exist in cache")

        # Check child doesn't already exist
        child_exists = self._check_child_exists(page.uri)
        if child_exists:
            raise ProvenanceError(f"Child page {page.uri} already exists in cache")

        # Check that child and parent are not the same page type
        if self._registry:
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

        # Check parent has valid version
        if parent_uri.version is None or parent_uri.version <= 0:
            raise ProvenanceError(
                f"Parent URI must have a fixed version number (>0), got: {parent_uri.version}"
            )

        # Check for cycles
        self._check_for_cycles(page.uri, parent_uri)

    def _check_parent_exists(self, parent_uri: PageURI) -> bool:
        """Check if parent page exists in any registered type."""
        # Check if the page actually exists in storage
        if self._registry:
            for page_type in self._registry.registered_types:
                try:
                    page = self._storage.get(
                        page_type, parent_uri, ignore_validity=True
                    )
                    if page is not None:
                        return True
                except Exception:
                    continue

        # Fallback: check relationships table
        with self._session_factory() as session:
            existing = (
                session.query(PageRelationships)
                .filter(
                    (PageRelationships.source_uri == str(parent_uri))
                    | (PageRelationships.target_uri == str(parent_uri))
                )
                .first()
            )
            return existing is not None

    def _check_child_exists(self, child_uri: PageURI) -> bool:
        """Check if child page already exists."""
        # Check if the page actually exists in storage
        if self._registry:
            for page_type in self._registry.registered_types:
                try:
                    page = self._storage.get(page_type, child_uri, ignore_validity=True)
                    if page is not None:
                        return True
                except Exception:
                    continue

        # Fallback: check relationships table
        with self._session_factory() as session:
            existing = (
                session.query(PageRelationships)
                .filter_by(source_uri=str(child_uri))
                .first()
            )
            return existing is not None

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
                if self._registry:
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
        """Get the lineage chain from root to the specified page as Page objects."""
        lineage = []
        current_uri: Optional[PageURI] = page_uri
        visited: Set[str] = set()  # Prevent infinite loops
        max_depth = 50  # Safety limit

        while current_uri and len(visited) < max_depth:
            # Prevent infinite loops
            uri_str = str(current_uri)
            if uri_str in visited:
                break
            visited.add(uri_str)

            # Find the page for this URI (ignore validity to build complete lineage)
            page = None
            if self._registry:
                for page_type in self._registry.registered_types:
                    try:
                        page = self._storage.get(
                            page_type, current_uri, ignore_validity=True
                        )
                        if page is not None:
                            break
                    except Exception:
                        continue

            if page:
                lineage.append(page)  # Append to build child-to-root order

            # Find parent relationship
            with self._session_factory() as session:
                parent_relationship = (
                    session.query(PageRelationships)
                    .filter_by(source_uri=uri_str, relationship_type="parent")
                    .first()
                )

                if parent_relationship:
                    try:
                        current_uri = PageURI.parse(str(parent_relationship.target_uri))
                    except Exception:
                        current_uri = None
                else:
                    current_uri = None

        # Reverse to get root-to-child order
        lineage.reverse()
        return lineage
