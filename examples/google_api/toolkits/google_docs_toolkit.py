"""Google Docs toolkit for searching and retrieving document headers and chunks."""

import logging
import os
import sys

from praga_core.agents import PaginatedResponse, RetrieverToolkit
from praga_core.context import ServerContext

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pages.google_docs import GDocChunk, GDocHeader  # noqa: E402
from services.google_docs_service import GoogleDocsService  # noqa: E402

logger = logging.getLogger(__name__)


class GoogleDocsToolkit(RetrieverToolkit):
    """Toolkit for searching and retrieving Google Docs headers and chunks."""

    def __init__(self, context: ServerContext, gdocs_service: GoogleDocsService):
        super().__init__(context)
        self.gdocs_service = gdocs_service

        # Register all document search and retrieval tools
        self.register_tool(self.search_documents_by_title)
        self.register_tool(self.search_documents_by_topic)
        self.register_tool(self.search_documents_by_owner)
        self.register_tool(self.search_recently_modified_documents)
        self.register_tool(self.search_all_documents)
        self.register_tool(self.search_chunks_in_document)

        logger.info("Google Docs toolkit initialized")

    @property
    def name(self) -> str:
        return "GoogleDocsToolkit"

    def _search_document_headers_paginated_response(
        self, search_method, *args, page: int = 0, page_size: int = 10, **kwargs
    ) -> PaginatedResponse[GDocHeader]:
        """Helper method to handle pagination for document header searches."""
        # Calculate page token by iterating through pages
        page_token = None
        if page > 0:
            current_token = None
            for _ in range(page):
                _, current_token = search_method(
                    *args, page_token=current_token, page_size=page_size, **kwargs
                )
                if not current_token:
                    # No more pages available
                    logger.debug(f"No more pages available at page {page}")
                    return PaginatedResponse(
                        results=[],
                        page_number=page,
                        has_next_page=False,
                    )
            page_token = current_token

        # Get the actual page data
        uris, next_page_token = search_method(
            *args, page_token=page_token, page_size=page_size, **kwargs
        )

        # Resolve URIs to pages using context (this will trigger ingestion if needed)
        pages = [self.context.get_page(uri) for uri in uris]
        logger.debug(f"Successfully resolved {len(pages)} document header pages")

        return PaginatedResponse(
            results=pages,
            page_number=page,
            has_next_page=bool(next_page_token),
        )

    def search_documents_by_title(
        self, title_query: str, page: int = 0
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents that match a title query.

        Args:
            title_query: Search query for document titles
            page: Page number for pagination (0-based)
        """
        return self._search_document_headers_paginated_response(
            self.gdocs_service.search_document_headers_by_title, title_query, page=page
        )

    def search_documents_by_topic(
        self, topic_query: str, page: int = 0
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents that match a topic/content query.

        Args:
            topic_query: Search query for document content/topics
            page: Page number for pagination (0-based)
        """
        return self._search_document_headers_paginated_response(
            self.gdocs_service.search_document_headers, topic_query, page=page
        )

    def search_documents_by_owner(
        self, owner_email: str, page: int = 0
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents owned by a specific user.

        Args:
            owner_email: Email address of the document owner
            page: Page number for pagination (0-based)
        """
        return self._search_document_headers_paginated_response(
            self.gdocs_service.search_document_headers_by_owner, owner_email, page=page
        )

    def search_recently_modified_documents(
        self, days: int = 7, page: int = 0
    ) -> PaginatedResponse[GDocHeader]:
        """Search for recently modified documents.

        Args:
            days: Number of days to look back for recent modifications (default: 7)
            page: Page number for pagination (0-based)
        """
        return self._search_document_headers_paginated_response(
            self.gdocs_service.search_recent_document_headers,
            days,  # Pass as positional argument
            page=page,
        )

    def search_all_documents(self, page: int = 0) -> PaginatedResponse[GDocHeader]:
        """Get all Google Docs documents (ordered by most recently modified).

        Args:
            page: Page number for pagination (0-based)
        """
        return self._search_document_headers_paginated_response(
            self.gdocs_service.search_document_headers,
            "",  # Empty query to get all documents
            page=page,
        )

    def search_chunks_in_document(
        self, document_id: str, query: str
    ) -> PaginatedResponse[GDocChunk]:
        """Search for specific content within a document's chunks.

        Args:
            document_id: The Google Docs document ID to search within
            query: Search query to find within the document chunks
        """
        # Use the service's BM25-like search for chunks
        matching_chunks = self.gdocs_service.search_chunks_in_document(
            document_id, query
        )

        return PaginatedResponse(
            results=matching_chunks,
            page_number=0,
            has_next_page=False,  # For now, return all matches in one page
        )
