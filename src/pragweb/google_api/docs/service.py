"""Google Docs service for handling document data and page creation using Google Docs API."""

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Tuple

from chonkie import RecursiveChunker
from chonkie.types.recursive import RecursiveChunk

from praga_core.agents import PaginatedResponse, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService

from ..client import GoogleAPIClient
from ..utils import resolve_person_identifier
from .page import GDocChunk, GDocHeader

logger = logging.getLogger(__name__)


class IngestedDocInfo(NamedTuple):
    doc: dict[str, Any]
    file_metadata: dict[str, Any]
    created_time: datetime
    modified_time: datetime
    title: str
    full_content: str
    word_count: int
    owner: Optional[str]
    permalink: str


class GoogleDocsService(ToolkitService):
    """Service for managing Google Docs data and page creation using Google Docs API."""

    @staticmethod
    def _parse_google_datetime(dt_str: str) -> datetime:
        """Parse Google API datetime string (handles both Z and offset, always returns aware)."""
        if dt_str.endswith("Z"):
            dt = datetime.fromisoformat(dt_str[:-1] + "+00:00")
        else:
            dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

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
        logger.info("Google Docs service initialized and handlers registered")

    def _register_handlers(self) -> None:
        """Register handlers with context using decorators."""

        ctx = self.context

        @ctx.route("gdoc_header", cache=True)
        async def handle_gdoc_header(page_uri: PageURI) -> GDocHeader:
            return await self.handle_header_request(page_uri)

        @ctx.validator
        async def validate_gdoc_header(page: GDocHeader) -> bool:
            return await self._validate_gdoc_header(page)

        @ctx.route("gdoc_chunk", cache=True)
        async def handle_gdoc_chunk(page_uri: PageURI) -> GDocChunk:
            return await self.handle_chunk_request(page_uri)

    async def handle_header_request(self, page_uri: PageURI) -> GDocHeader:
        """Handle a Google Docs header page request - ingest if not exists."""
        # Note: Cache checking is now handled by ServerContext.get_page()
        # This method is only called when the page is not in cache or caching is disabled

        # Not in cache, ingest the document (ingest on touch)
        logger.info(f"Document {page_uri.id} not in cache, ingesting...")
        header_page = await self._ingest_document(page_uri)
        return header_page

    async def handle_chunk_request(self, page_uri: PageURI) -> GDocChunk:
        """Handle a Google Docs chunk page request - ingest if not exists."""
        # Note: Cache checking is now handled by ServerContext.get_page()
        # This method is only called when the page is not in cache or caching is disabled

        raise NotImplementedError("Chunk requests should be handled in the cache")

    async def _validate_gdoc_header(self, page: GDocHeader) -> bool:
        """Validate that a GDocHeader page is still current by checking modified time."""
        try:
            # Get latest file metadata from API
            file_metadata = await self.api_client.get_file_metadata(page.document_id)
            if not file_metadata:
                logger.warning(
                    f"Could not get file metadata for document {page.document_id}"
                )
                return False
            # Parse the modifiedTime from metadata
            latest_modified_time = self._parse_google_datetime(
                file_metadata.get("modifiedTime", "")
            )
            # Compare with stored modified time
            return bool(latest_modified_time <= page.modified_time)
        except Exception as e:
            logger.error(
                f"Failed to validate header {page.uri}: {e}\n{traceback.format_exc()}"
            )
            return False

    async def _ingest_document(self, header_page_uri: PageURI) -> GDocHeader:
        """Ingest a document by fetching content, chunking, and storing in page cache."""
        document_id = header_page_uri.id
        logger.info(f"Starting async ingestion for document: {document_id}")

        doc_info = await self._fetch_and_extract_document_info(document_id)
        chunks = self._chunk_content(doc_info.full_content)
        logger.info(f"Document {document_id} chunked into {len(chunks)} pieces")
        header_page, chunk_pages = self._build_header_and_chunk_pages(
            header_page_uri,
            document_id,
            doc_info,
            chunks,
        )
        await self._store_pages(header_page, chunk_pages)
        logger.info(
            f"Successfully ingested document {document_id} with {len(chunks)} chunks"
        )
        return header_page

    async def _fetch_and_extract_document_info(
        self, document_id: str
    ) -> IngestedDocInfo:
        try:
            doc = await self.api_client.get_document(document_id)
            file_metadata = await self.api_client.get_file_metadata(document_id)
            created_time = self._parse_google_datetime(
                file_metadata.get("createdTime", "")
            )
            modified_time = self._parse_google_datetime(
                file_metadata.get("modifiedTime", "")
            )
            title = doc.get("title", "Untitled Document")
            content_elements = doc.get("body", {}).get("content", [])
            full_content = self._extract_text_from_content(content_elements)
            word_count = len(full_content.split()) if full_content else 0
            owners = file_metadata.get("owners", [])
            owner = owners[0].get("emailAddress") if owners else None
            permalink = f"https://docs.google.com/document/d/{document_id}/edit"
            return IngestedDocInfo(
                doc=doc,
                file_metadata=file_metadata,
                created_time=created_time,
                modified_time=modified_time,
                title=title,
                full_content=full_content,
                word_count=word_count,
                owner=owner,
                permalink=permalink,
            )
        except Exception as e:
            raise ValueError(f"Failed to fetch document {document_id}: {e}")

    def _chunk_content(self, full_content: str) -> Sequence[RecursiveChunk]:
        return self.chunker.chunk(full_content)

    def _build_header_and_chunk_pages(
        self,
        header_page_uri: PageURI,
        document_id: str,
        doc_info: IngestedDocInfo,
        chunks: Sequence[RecursiveChunk],
    ) -> tuple[GDocHeader, list[GDocChunk]]:
        header_uri = header_page_uri
        chunk_uris = [
            PageURI(
                root=header_uri.root,
                type="gdoc_chunk",
                id=f"{document_id}({i})",
                version=header_uri.version,
            )
            for i in range(len(chunks))
        ]
        header_page = GDocHeader(
            uri=header_uri,
            document_id=document_id,
            title=doc_info.title,
            summary=(
                doc_info.full_content[:500] + "..."
                if len(doc_info.full_content) > 500
                else doc_info.full_content
            ),
            created_time=doc_info.created_time,
            modified_time=doc_info.modified_time,
            owner=doc_info.owner,
            word_count=doc_info.word_count,
            chunk_count=len(chunks),
            chunk_uris=chunk_uris,
            permalink=doc_info.permalink,
        )
        chunk_pages: list[GDocChunk] = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{document_id}({i})"
            chunk_text = getattr(chunk, "text", str(chunk))
            chunk_title = self._get_chunk_title(chunk_text)
            prev_chunk_uri = (
                PageURI(
                    root=self.context.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({i - 1})",
                    version=header_uri.version,
                )
                if i > 0
                else None
            )
            next_chunk_uri = (
                PageURI(
                    root=self.context.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({i + 1})",
                    version=header_uri.version,
                )
                if i < len(chunks) - 1
                else None
            )
            chunk_uri = PageURI(
                root=header_uri.root,
                type="gdoc_chunk",
                id=chunk_id,
                version=header_uri.version,
            )
            chunk_page = GDocChunk(
                uri=chunk_uri,
                document_id=document_id,
                chunk_index=i,
                chunk_title=chunk_title,
                content=chunk_text,
                doc_title=doc_info.title,
                prev_chunk_uri=prev_chunk_uri,
                next_chunk_uri=next_chunk_uri,
                header_uri=header_uri,
                permalink=doc_info.permalink,
            )
            chunk_pages.append(chunk_page)
        return header_page, chunk_pages

    async def _store_pages(
        self, header_page: GDocHeader, chunk_pages: list[GDocChunk]
    ) -> None:
        await self.page_cache.store(header_page)
        tasks = [
            self.page_cache.store(chunk_page, parent_uri=header_page.uri)
            for chunk_page in chunk_pages
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

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

    async def search_documents(
        self,
        search_params: Dict[str, Any],
        page_token: Optional[str] = None,
        page_size: int = 20,
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Generic document search method that delegates to API client."""
        try:
            # Delegate directly to API client
            files, next_page_token = await self.api_client.search_documents(
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

    async def search_chunks_in_document(
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
        header_uri = PageURI(root=self.context.root, type="gdoc_header", id=document_id)
        await self.handle_header_request(header_uri)

        # Get all chunks for this document from page cache
        page_cache = self.context.page_cache

        # Find all chunks for this document
        chunk_pages = await (
            page_cache.find(GDocChunk)
            .where(lambda chunk: chunk.document_id == document_id)
            .all()
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

    async def _search_documents_paginated_response(
        self,
        search_params: Dict[str, Any],
        cursor: Optional[str] = None,
        page_size: int = 10,
    ) -> PaginatedResponse[GDocHeader]:
        """Search documents and return a paginated response."""
        # Get the page data using the cursor directly
        uris, next_page_token = await self.search_documents(
            search_params, cursor, page_size
        )

        # Resolve URIs to pages using context async (this will trigger ingestion if needed)
        pages = await self.context.get_pages(uris)

        # Type check the results
        for page_obj in pages:
            if not isinstance(page_obj, GDocHeader):
                raise TypeError(f"Expected GDocHeader but got {type(page_obj)}")

        logger.debug(f"Successfully resolved {len(pages)} document header pages")

        return PaginatedResponse(
            results=pages,  # type: ignore
            next_cursor=next_page_token,
        )

    @tool()
    async def search_documents_by_title(
        self, title_query: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents that match a title query.

        Args:
            title_query: Search query for document titles
            cursor: Cursor token for pagination (optional)
        """
        return await self._search_documents_paginated_response(
            {"title_query": title_query}, cursor=cursor
        )

    @tool()
    async def search_documents_by_topic(
        self, topic_query: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents that match a topic/content query.

        Args:
            topic_query: Search query for document content/topics
            cursor: Cursor token for pagination (optional)
        """
        return await self._search_documents_paginated_response(
            {"query": topic_query}, cursor=cursor
        )

    @tool()
    async def search_documents_by_owner(
        self, owner_identifier: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for documents owned by a specific user.

        Args:
            owner_identifier: Email address or name of the document owner
            cursor: Cursor token for pagination (optional)
        """
        # Resolve person identifier to email address if needed
        resolved_owner = resolve_person_identifier(owner_identifier)
        return await self._search_documents_paginated_response(
            {"owner_email": resolved_owner}, cursor=cursor
        )

    @tool()
    async def search_recently_modified_documents(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Search for recently modified documents.

        Args:
            days: Number of days to look back for recent modifications (default: 7)
            cursor: Cursor token for pagination (optional)
        """
        return await self._search_documents_paginated_response(
            {"days": days}, cursor=cursor
        )

    @tool()
    async def search_all_documents(
        self, cursor: Optional[str] = None
    ) -> PaginatedResponse[GDocHeader]:
        """Get all Google Docs documents (ordered by most recently modified).

        Args:
            cursor: Cursor token for pagination (optional)
        """
        return await self._search_documents_paginated_response(
            {"query": ""}, cursor=cursor
        )

    @tool()
    async def find_chunks_in_document(
        self, doc_header_uri: str, query: str
    ) -> PaginatedResponse[GDocChunk]:
        """Search for specific content within a document's chunks.

        Args:
            doc_header_uri: The URI of the Google Docs header page to search within
            query: Search query to find within the document chunks
        """
        # Use the service's text matching search for chunks
        matching_chunks = await self.search_chunks_in_document(doc_header_uri, query)

        return PaginatedResponse(
            results=matching_chunks,
            next_cursor=None,
        )

    @property
    def name(self) -> str:
        return "google_docs"
