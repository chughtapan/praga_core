"""Google Docs service for handling document data and page creation using Google Docs API."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from chonkie import RecursiveChunker

from praga_core.agents import PaginatedResponse, RetrieverToolkit, tool
from praga_core.types import Page, PageURI
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from ..utils import resolve_person_identifier
from .page import GDocChunk, GDocHeader

logger = logging.getLogger(__name__)


class GoogleDocsService(ToolkitService):
    """Service for managing Google Docs data and page creation using Google Docs API."""

    def __init__(self, api_client: GoogleAPIClient, chunk_size: int = 4000) -> None:
        super().__init__()
        self.api_client = api_client
        self.chunk_size = chunk_size

        # Initialize Chonkie chunker with configurable chunk size
        self.chunker = RecursiveChunker(
            tokenizer_or_token_counter="gpt2",
            chunk_size=chunk_size,
        )

        # Register handlers using decorators
        self._register_handlers()
        self.context.page_cache.register_page_type(GDocHeader)
        self.context.page_cache.register_page_type(GDocChunk)
        logger.info("Google Docs service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        def validate_gdoc_header(page: Page) -> bool:
            """Validate a Google Docs header page by checking if revision is current."""
            try:
                if not isinstance(page, GDocHeader):
                    return False
                result = self.api_client.check_file_revision(
                    page.document_id, page.revision_id
                )
                return bool(result)
            except Exception as e:
                logger.warning(f"Failed to validate header {page.uri}: {e}")
                return False

        def validate_gdoc_chunk(page: Page) -> bool:
            """Validate a Google Docs chunk page by checking if parent document revision is current."""
            try:
                if not isinstance(page, GDocChunk):
                    return False
                result = self.api_client.check_file_revision(
                    page.document_id, page.doc_revision_id
                )
                return bool(result)
            except Exception as e:
                logger.warning(f"Failed to validate chunk {page.uri}: {e}")
                return False

        @self.context.handler("gdoc_header", invalidator=validate_gdoc_header)
        def handle_gdoc_header(document_id: str) -> GDocHeader:
            return self.handle_header_request(document_id)

        @self.context.handler("gdoc_chunk", invalidator=validate_gdoc_chunk)
        def handle_gdoc_chunk(chunk_id: str) -> GDocChunk:
            return self.handle_chunk_request(chunk_id)

    def handle_header_request(self, document_id: str) -> GDocHeader:
        """Handle a Google Docs header page request - get from cache or ingest if not exists."""
        page_cache = self.context.page_cache

        # Register page types with cache

        # Construct URI from document_id
        header_uri = PageURI(root=self.context.root, type="gdoc_header", id=document_id)
        cached_header = page_cache.get_page(GDocHeader, header_uri)
        if cached_header:
            logger.debug(f"Found existing document header in cache: {document_id}")
            return cached_header

        # Not in cache, ingest the document (ingest on touch)
        logger.info(f"Document {document_id} not in cache, ingesting...")
        header_page = self._ingest_document(document_id)
        return header_page

    def handle_chunk_request(self, chunk_id: str) -> GDocChunk:
        """Handle a Google Docs chunk page request - get from cache or ingest if not exists."""
        page_cache = self.context.page_cache

        # Construct URI from chunk_id
        chunk_uri = PageURI(root=self.context.root, type="gdoc_chunk", id=chunk_id)
        cached_chunk = page_cache.get_page(GDocChunk, chunk_uri)
        if cached_chunk:
            logger.debug(f"Found existing document chunk in cache: {chunk_id}")
            return cached_chunk

        # Parse chunk_id to get document_id
        if "(" not in chunk_id or not chunk_id.endswith(")"):
            raise ValueError(f"Invalid chunk ID format: {chunk_id}")

        document_id = chunk_id[: chunk_id.rfind("(")]

        # Not in cache, ingest the document (ingest on touch)
        logger.info(
            f"Chunk {chunk_id} not in cache, ingesting document {document_id}..."
        )
        self._ingest_document(document_id)

        # Now try to get the chunk again
        cached_chunk = page_cache.get_page(GDocChunk, chunk_uri)
        if not cached_chunk:
            raise ValueError(f"Chunk {chunk_id} not found after ingestion")

        return cached_chunk

    def _ingest_document(self, document_id: str) -> GDocHeader:
        """Ingest a document by fetching content, chunking, and storing in page cache."""
        logger.info(f"Starting ingestion for document: {document_id}")

        try:
            # Fetch the document content from Docs API
            doc = self.api_client.get_document(document_id)

            # Fetch file metadata from Drive API
            file_metadata = self.api_client.get_file_metadata(document_id)

            # Get the latest revision ID for cache invalidation
            revision_id = self.api_client.get_latest_revision_id(document_id)
            if not revision_id:
                logger.warning(f"Could not get revision ID for document {document_id}")
                revision_id = "unknown"

        except Exception as e:
            raise ValueError(f"Failed to fetch document {document_id}: {e}")

        # Extract basic information
        title = doc.get("title", "Untitled Document")

        # Extract text content
        content_elements = doc.get("body", {}).get("content", [])
        full_content = self._extract_text_from_content(content_elements)

        # Calculate word count
        word_count = len(full_content.split()) if full_content else 0

        # Parse timestamps
        created_time = datetime.fromisoformat(
            file_metadata["createdTime"].replace("Z", "+00:00")
        )
        modified_time = datetime.fromisoformat(
            file_metadata["modifiedTime"].replace("Z", "+00:00")
        )

        # Get owner information
        owners = file_metadata.get("owners", [])
        owner = owners[0].get("emailAddress") if owners else None

        # Chunk the content using Chonkie
        chunks = self.chunker.chunk(full_content)
        chunk_count = len(chunks)

        logger.info(f"Document {document_id} chunked into {chunk_count} pieces")

        # Create permalink
        permalink = f"https://docs.google.com/document/d/{document_id}/edit"

        # Create header URI that will be used as parent for chunks
        header_uri = self.context.create_page_uri(
            GDocHeader, "gdoc_header", id=document_id
        )

        # Store chunks in page cache first
        chunk_pages = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{document_id}({i})"
            # Type cast: chunk is from chonkie chunker, has .text and .token_count attributes
            chunk_text = getattr(chunk, "text", str(chunk))
            chunk_token_count = getattr(chunk, "token_count", 0)
            chunk_title = self._get_chunk_title(chunk_text)

            # Create next/prev chunk URIs
            prev_chunk_uri = None
            if i > 0:
                prev_chunk_uri = PageURI(
                    root=self.context.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({i - 1})",
                )

            next_chunk_uri = None
            if i < chunk_count - 1:
                next_chunk_uri = PageURI(
                    root=self.context.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({i + 1})",
                )

            # Create chunk page
            chunk_uri = self.context.create_page_uri(
                GDocChunk, "gdoc_chunk", id=chunk_id
            )
            chunk_page = GDocChunk(
                uri=chunk_uri,
                document_id=document_id,
                chunk_index=i,
                chunk_title=chunk_title,
                content=chunk_text,
                doc_title=title,
                token_count=chunk_token_count,
                prev_chunk_uri=prev_chunk_uri,
                next_chunk_uri=next_chunk_uri,
                header_uri=header_uri,
                permalink=permalink,
                doc_revision_id=revision_id,
            )

            chunk_pages.append(chunk_page)

        # Create chunk URIs for header
        chunk_uris = [chunk.uri for chunk in chunk_pages]

        # Create summary (first 500 chars + chunk info)
        summary = full_content[:500]
        if len(full_content) > 500:
            summary += "..."
        summary += f" [{chunk_count} chunks]"

        # Create and store header page first (to satisfy parent existence requirement)
        header_page = GDocHeader(
            uri=header_uri,
            document_id=document_id,
            title=title,
            summary=summary,
            created_time=created_time,
            modified_time=modified_time,
            owner=owner,
            word_count=word_count,
            chunk_count=chunk_count,
            chunk_uris=chunk_uris,
            permalink=permalink,
            revision_id=revision_id,
        )

        # Store header in page cache first
        self.context.page_cache.store_page(header_page)

        # Now store chunks with header as parent for provenance tracking
        for chunk_page in chunk_pages:
            self.context.page_cache.store_page(chunk_page, parent_uri=header_uri)

        logger.info(
            f"Successfully ingested document {document_id} with {chunk_count} chunks"
        )
        return header_page

    def _extract_text_from_content(self, content: List[Dict[str, Any]]) -> str:
        """Extract plain text from Google Docs content structure."""
        text_parts: List[str] = []

        def extract_from_element(element: Dict[str, Any]) -> None:
            if "paragraph" in element:
                paragraph = element["paragraph"]
                if "elements" in paragraph:
                    for elem in paragraph["elements"]:
                        if "textRun" in elem and "content" in elem["textRun"]:
                            text_parts.append(elem["textRun"]["content"])
            elif "table" in element:
                # Handle table content
                table = element["table"]
                if "tableRows" in table:
                    for row in table["tableRows"]:
                        if "tableCells" in row:
                            for cell in row["tableCells"]:
                                if "content" in cell:
                                    for cell_element in cell["content"]:
                                        extract_from_element(cell_element)

        for item in content:
            extract_from_element(item)

        return "".join(text_parts).strip()

    def _get_chunk_title(self, content: str) -> str:
        """Generate a chunk title from the first few words or sentence."""
        # Take first sentence or first 50 characters, whichever is shorter
        sentences = content.split(". ")
        first_sentence = sentences[0].strip()

        if len(first_sentence) <= 50:
            return first_sentence
        else:
            # Take first 50 characters and add ellipsis
            return content[:47].strip() + "..."

    def search_documents(
        self,
        search_params: Dict[str, Any],
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Generic document search method that delegates to API client."""
        try:
            # Delegate directly to API client
            files, next_page_token = self.api_client.search_documents(
                search_params=search_params,
                page_token=page_token,
                page_size=page_size,
            )

            logger.debug(
                f"Drive API returned {len(files)} documents, next_token: {bool(next_page_token)}"
            )

            # Convert to Header PageURIs (ingestion will happen when header is accessed)
            uris = [
                PageURI(root=self.context.root, type="gdoc_header", id=file["id"])
                for file in files
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise

    def search_chunks_in_document(
        self, doc_header_uri: str, query: str
    ) -> List[GDocChunk]:
        """Search for chunks within a specific document using simple text matching."""
        # Parse the URI to extract document ID
        try:
            parsed_uri = PageURI.parse(doc_header_uri)
            if parsed_uri.type != "gdoc_header":
                raise ValueError(f"Expected gdoc_header URI, got {parsed_uri.type}")
            document_id = parsed_uri.id
        except Exception as e:
            raise ValueError(f"Invalid document header URI '{doc_header_uri}': {e}")

        # Ensure document is ingested (ingest on touch)
        self.handle_header_request(document_id)

        # Get all chunks for this document from page cache
        page_cache = self.context.page_cache

        # Find all chunks for this document
        chunk_pages = page_cache.find_pages_by_attribute(
            GDocChunk, lambda chunk: chunk.document_id == document_id
        )

        if not chunk_pages:
            return []

        # Simple text matching scoring
        query_terms = query.lower().split()
        scored_chunks = []

        for chunk_page in chunk_pages:
            content_lower = chunk_page.content.lower()
            score = 0

            # Simple term frequency scoring
            for term in query_terms:
                # Term frequency
                tf = content_lower.count(term)
                if tf > 0:
                    # Simple TF-IDF approximation
                    score += tf * (1 + len(term))  # Longer terms get higher weight

            if score > 0:
                scored_chunks.append((score, chunk_page))

        # Sort by score (descending) and return top 10 matches
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        result_chunks = [chunk for score, chunk in scored_chunks[:10]]

        return result_chunks

    def invalidate_document(self, document_id: str) -> int:
        """Manually invalidate all cached pages for a specific document.

        Args:
            document_id: Google Docs document ID to invalidate

        Returns:
            Number of pages invalidated
        """
        invalidated_count = 0

        # Invalidate header page
        header_uri_prefix = f"{self.context.root}/gdoc_header:{document_id}"
        invalidated_count += self.context.invalidate_pages_by_prefix(header_uri_prefix)

        # Invalidate all chunk pages for this document
        chunk_uri_prefix = f"{self.context.root}/gdoc_chunk:{document_id}"
        invalidated_count += self.context.invalidate_pages_by_prefix(chunk_uri_prefix)

        logger.info(
            f"Manually invalidated {invalidated_count} pages for document {document_id}"
        )
        return invalidated_count

    def check_document_freshness(self, document_id: str) -> Dict[str, Any]:
        """Check if a cached document is still fresh compared to the online version.

        Args:
            document_id: Google Docs document ID to check

        Returns:
            Dictionary with freshness information
        """
        try:
            # Get cached header if it exists
            header_uri = PageURI(
                root=self.context.root, type="gdoc_header", id=document_id
            )
            cached_header = self.context.page_cache.get_page(GDocHeader, header_uri)

            if not cached_header:
                return {
                    "cached": False,
                    "fresh": False,
                    "message": "Document not in cache",
                }

            # Check if cached revision matches current revision
            current_revision_id = self.api_client.get_latest_revision_id(document_id)
            is_fresh = current_revision_id == cached_header.revision_id

            return {
                "cached": True,
                "fresh": is_fresh,
                "cached_revision": cached_header.revision_id,
                "current_revision": current_revision_id,
                "cached_modified_time": cached_header.modified_time.isoformat(),
                "message": (
                    "Document is fresh"
                    if is_fresh
                    else "Document has been modified online"
                ),
            }

        except Exception as e:
            return {
                "cached": bool(cached_header) if "cached_header" in locals() else False,
                "fresh": False,
                "error": str(e),
                "message": f"Error checking document freshness: {e}",
            }

    def refresh_document(self, document_id: str) -> GDocHeader:
        """Force refresh a document by invalidating cache and re-ingesting.

        Args:
            document_id: Google Docs document ID to refresh

        Returns:
            Freshly ingested document header
        """
        logger.info(f"Force refreshing document {document_id}")

        # Invalidate all cached pages for this document
        self.invalidate_document(document_id)

        # Re-ingest the document
        return self._ingest_document(document_id)

    @property
    def toolkit(self) -> "GoogleDocsToolkit":
        """Get the Google Docs toolkit."""
        return GoogleDocsToolkit(self)

    @property
    def name(self) -> str:
        return "google_docs"


class GoogleDocsToolkit(RetrieverToolkit):
    """Toolkit for searching and retrieving Google Docs headers and chunks."""

    def __init__(self, google_docs_service: GoogleDocsService):
        super().__init__()
        self.google_docs_service = google_docs_service
        logger.info("Google Docs toolkit initialized")

    @property
    def name(self) -> str:
        return "GoogleDocsToolkit"

    def _search_documents_paginated_response(
        self,
        search_params: Dict[str, Any],
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> PaginatedResponse[GDocHeader]:
        """Search documents and return a paginated response."""
        # Get the page data using the cursor directly
        uris, next_page_token = self.google_docs_service.search_documents(
            search_params, cursor, page_size
        )

        # Resolve URIs to pages using context (this will trigger ingestion if needed)
        pages: List[GDocHeader] = []
        for uri in uris:
            page_obj = self.context.get_page(uri)
            if not isinstance(page_obj, GDocHeader):
                raise TypeError(f"Expected GDocHeader but got {type(page_obj)}")
            pages.append(page_obj)
        logger.debug(f"Successfully resolved {len(pages)} document header pages")

        return PaginatedResponse(
            results=pages,
            next_cursor=next_page_token,
        )

    @tool()
    def search_documents_by_title(
        self, title_query: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents that match a title query.

        Args:
            title_query: Search query for document titles
            cursor: Cursor token for pagination (optional)
        """
        return self._search_documents_paginated_response(
            {"title_query": title_query}, cursor=cursor
        )

    @tool()
    def search_documents_by_topic(
        self, topic_query: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents that match a topic/content query.

        Args:
            topic_query: Search query for document content/topics
            cursor: Cursor token for pagination (optional)
        """
        return self._search_documents_paginated_response(
            {"query": topic_query}, cursor=cursor
        )

    @tool()
    def search_documents_by_owner(
        self, owner_identifier: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents owned by a specific user.

        Args:
            owner_identifier: Email address or name of the document owner
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        resolved_owner = resolve_person_identifier(owner_identifier)
        return self._search_documents_paginated_response(
            {"owner_email": resolved_owner}, cursor=cursor
        )

    @tool()
    def search_recently_modified_documents(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for recently modified documents.

        Args:
            days: Number of days to look back for recent modifications (default: 7)
            cursor: Cursor token for pagination (optional)
        """
        return self._search_documents_paginated_response({"days": days}, cursor=cursor)

    @tool()
    def search_all_documents(
        self, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Get all Google Docs documents (ordered by most recently modified).

        Args:
            cursor: Cursor token for pagination (optional)
        """
        return self._search_documents_paginated_response({"query": ""}, cursor=cursor)

    @tool()
    def search_chunks_in_document(
        self, doc_header_uri: str, query: str
    ) -> PaginatedResponse[GDocChunk]:
        """Search for specific content within a document's chunks.

        Args:
            doc_header_uri: The URI of the Google Docs header page to search within
            query: Search query to find within the document chunks
        """
        # Use the service's text matching search for chunks
        matching_chunks = self.google_docs_service.search_chunks_in_document(
            doc_header_uri, query
        )

        return PaginatedResponse(
            results=matching_chunks,
            next_cursor=None,
        )

    def check_document_freshness(self, document_id: str) -> Dict[str, Any]:
        """Check if a cached Google Docs document is still fresh compared to the online version.

        Args:
            document_id: Google Docs document ID to check

        Returns:
            Dictionary containing freshness information including cached status,
            revision IDs, and modification times
        """
        return self.google_docs_service.check_document_freshness(document_id)

    def invalidate_document_cache(self, document_id: str) -> Dict[str, Any]:
        """Manually invalidate all cached pages for a specific Google Docs document.

        Args:
            document_id: Google Docs document ID to invalidate

        Returns:
            Dictionary with invalidation results
        """
        try:
            invalidated_count = self.google_docs_service.invalidate_document(
                document_id
            )
            return {
                "success": True,
                "document_id": document_id,
                "invalidated_pages": invalidated_count,
                "message": f"Successfully invalidated {invalidated_count} cached pages",
            }
        except Exception as e:
            return {
                "success": False,
                "document_id": document_id,
                "error": str(e),
                "message": f"Failed to invalidate document cache: {e}",
            }

    @tool()
    def refresh_document(self, document_id: str) -> List[Page]:
        """Force refresh a Google Docs document by invalidating cache and re-ingesting.

        Args:
            document_id: Google Docs document ID to refresh

        Returns:
            Freshly ingested document header page
        """
        header = self.google_docs_service.refresh_document(document_id)
        return [header]
