"""Provenance tracking logic for page relationships."""

from typing import List, Optional, TYPE_CHECKING

from ..types import Page, PageURI
from .exceptions import ProvenanceError

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
            raise ProvenanceError(
                f"Parent page {parent_uri} does not exist in cache"
            )
        
        # Pre-check 2: Ensure child does not already exist in cache
        child_page = self.cache.get_page_by_uri_any_type(page.uri)
        if child_page is not None:
            raise ProvenanceError(
                f"Child page {page.uri} already exists in cache"
            )
        
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

    def check_for_cycles(self, child_uri: PageURI, parent_uri: PageURI, visited: Optional[set] = None) -> None:
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
        
        # Get the parent page and check if it has a parent
        parent_page = self.cache.get_page_by_uri_any_type(parent_uri)
        if parent_page and parent_page.parent_uri:
            self.check_for_cycles(child_uri, parent_page.parent_uri, visited.copy())

    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all pages that have the specified page as their parent.
        
        Args:
            parent_uri: The parent URI to find children for
            
        Returns:
            List of child pages
        """
        children = []
        
        # Check all registered page types for children
        for page_type_name in self.cache.registered_page_types:
            if (page_type_name in self.cache.table_registry and 
                page_type_name in self.cache.page_classes):
                table_class = self.cache.table_registry[page_type_name]
                page_class = self.cache.page_classes[page_type_name]
                
                with self.cache.get_session() as session:
                    entities = session.query(table_class).filter_by(parent_uri=str(parent_uri)).all()
                    
                    # Convert entities back to Page instances
                    for entity in entities:
                        page_data = {"uri": PageURI.parse(entity.uri)}
                        for field_name, field_info in page_class.model_fields.items():
                            if field_name not in ("uri",):
                                value = getattr(entity, field_name)
                                converted_value = self.cache.convert_page_uris_from_storage(
                                    value, field_info.annotation
                                )
                                page_data[field_name] = converted_value

                        children.append(page_class(**page_data))
        
        return children

    def get_provenance_chain(self, page_uri: PageURI) -> List[Page]:
        """Get the full provenance chain for a page (from root to the specified page).
        
        Args:
            page_uri: The page URI to get the provenance chain for
            
        Returns:
            List of pages in the provenance chain, from root ancestor to the specified page
        """
        chain = []
        current_uri = page_uri
        
        while current_uri:
            page = self.cache.get_page_by_uri_any_type(current_uri)
            if page is None:
                break
            
            chain.insert(0, page)  # Insert at beginning to build chain from root
            current_uri = page.parent_uri
        
        return chain