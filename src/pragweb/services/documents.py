"""Documents orchestration service that coordinates between multiple providers."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from chonkie import RecursiveChunker
from chonkie.types.recursive import RecursiveChunk

from praga_core.agents import PaginatedResponse, tool
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import DocumentChunk, DocumentHeader
from pragweb.toolkit_service import ToolkitService

logger = logging.getLogger(__name__)


class DocumentService(ToolkitService):
    """Orchestration service for document operations across multiple providers."""

    def __init__(
        self, providers: Dict[str, BaseProviderClient], chunk_size: int = 4000
    ):
        if not providers:
            raise ValueError("DocumentService requires at least one provider")
        if len(providers) != 1:
            raise ValueError("DocumentService requires exactly one provider")

        self.providers = providers
        self.provider_client = list(providers.values())[0]
        self.provider_name = list(providers.keys())[0]
        self.chunk_size = chunk_size

        # Initialize Chonkie chunker with configurable chunk size
        self.chunker = RecursiveChunker(
            tokenizer_or_token_counter="gpt2",
            chunk_size=chunk_size,
        )

        super().__init__()

        # Set page types based on service name (after super init)
        self.header_page_type = f"{self.name}_header"
        self.chunk_page_type = f"{self.name}_chunk"
        self._register_handlers()
        logger.info(
            "Document service initialized with provider: %s, chunk_size: %d",
            self.provider_name,
            chunk_size,
        )

    @property
    def name(self) -> str:
        """Service name used for registration."""
        # Auto-derive service name from provider
        provider_to_service = {"google": "google_docs", "microsoft": "outlook_docs"}
        return provider_to_service.get(self.provider_name, f"{self.provider_name}_docs")

    def _register_handlers(self) -> None:
        """Register page routes and actions with context."""
        ctx = self.context

        # Register page route handlers using page type variables
        @ctx.route(self.header_page_type, cache=True)
        async def handle_document_header(page_uri: PageURI) -> DocumentHeader:
            return await self.create_document_header_page(page_uri)

        @ctx.route(self.chunk_page_type, cache=True)
        async def handle_document_chunk(page_uri: PageURI) -> DocumentChunk:
            return await self.create_document_chunk_page(page_uri)

        # Register validator for document headers
        @ctx.validator
        async def validate_document_header(page: DocumentHeader) -> bool:
            return await self._validate_document_header(page)

    async def create_document_header_page(self, page_uri: PageURI) -> DocumentHeader:
        """Create a DocumentHeader from a URI with automatic chunking and caching."""
        # Extract provider and document ID from URI
        provider_name, document_id = self._parse_document_uri(page_uri)

        if not self.provider_client:
            raise ValueError("No provider available")

        # Get document data from provider
        document_data = await self.provider_client.documents_client.get_document(
            document_id
        )

        # Get document content for chunking
        document_content = (
            await self.provider_client.documents_client.get_document_content(
                document_id
            )
        )

        # Chunk the content using Chonkie
        chunks = self._chunk_content(document_content)
        logger.info(f"Document {document_id} chunked into {len(chunks)} pieces")

        # Parse document metadata and create DocumentHeader directly
        header = self._build_document_header(
            document_data, document_content, chunks, page_uri, document_id
        )

        # Store the header first so it exists for chunk relationships
        await self.context.page_cache.store(header)

        # Create and store chunk pages asynchronously
        chunk_pages = self._build_chunk_pages(document_id, chunks, header, header.uri)
        await self._store_chunk_pages(chunk_pages, header)

        logger.info(
            f"Successfully auto-chunked document {document_id} with {len(chunks)} chunks"
        )
        return header

    async def create_document_chunk_page(self, page_uri: PageURI) -> DocumentChunk:
        """Create a DocumentChunk from a URI - should retrieve from cache only."""
        # Extract chunk index from URI for error message
        provider_name, document_id, chunk_index = self._parse_chunk_uri(page_uri)

        # Chunks should only be retrieved from cache, never created directly
        # If a chunk doesn't exist, it means the header wasn't properly ingested
        raise ValueError(
            f"Chunk {chunk_index} for document {document_id} not found in cache. "
            f"Document header must be ingested first to create chunks."
        )

    @tool()
    async def search_documents_by_title(
        self,
        title_query: str,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[DocumentHeader]:
        """Search for documents that match a title query.

        Args:
            title_query: Search query for document titles
            cursor: Cursor token for pagination (optional)

        Returns:
            Paginated response of matching document header pages
        """
        max_results = 10
        if not self.provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search documents by title
            search_results = (
                await self.provider_client.documents_client.search_documents(
                    query=f"title:{title_query}",
                    max_results=max_results,
                    page_token=cursor,
                )
            )

            # Extract document IDs
            document_ids = []
            for doc in search_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.header_page_type,
                    id=document_id,
                )
                for document_id in document_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            doc_pages = [page for page in pages if isinstance(page, DocumentHeader)]

            return PaginatedResponse(
                results=doc_pages,
                next_cursor=search_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search documents by title: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def search_documents_by_topic(
        self,
        topic_query: str,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[DocumentHeader]:
        """Search for documents that match a topic/content query.

        Args:
            topic_query: Search query for document content/topics
            cursor: Cursor token for pagination (optional)

        Returns:
            Paginated response of matching document header pages
        """
        max_results = 10
        if not self.provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search documents by content/topic
            search_results = (
                await self.provider_client.documents_client.search_documents(
                    query=topic_query,
                    max_results=max_results,
                    page_token=cursor,
                )
            )

            # Extract document IDs
            document_ids = []
            for doc in search_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.header_page_type,
                    id=document_id,
                )
                for document_id in document_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            doc_pages = [page for page in pages if isinstance(page, DocumentHeader)]

            return PaginatedResponse(
                results=doc_pages,
                next_cursor=search_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search documents by topic: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def search_documents_by_owner(
        self, owner_identifier: str, cursor: Optional[str] = None
    ) -> PaginatedResponse[DocumentHeader]:
        """Search for documents owned by a specific user.

        Args:
            owner_identifier: Email address or name of the document owner
            cursor: Cursor token for pagination (optional)
        """
        if not self.provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search documents by owner (use query parameter)
            documents_results = (
                await self.provider_client.documents_client.search_documents(
                    query=f"owner:{owner_identifier}",
                    max_results=10,
                    page_token=cursor,
                )
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.header_page_type,
                    id=document_id,
                )
                for document_id in document_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            # Cast to DocumentHeader list for type safety
            from pragweb.pages import DocumentHeader

            doc_pages = [page for page in pages if isinstance(page, DocumentHeader)]

            return PaginatedResponse(
                results=doc_pages,
                next_cursor=documents_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search documents by owner: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def search_recently_modified_documents(
        self, days: int = 7, cursor: Optional[str] = None
    ) -> PaginatedResponse[DocumentHeader]:
        """Search for recently modified documents.

        Args:
            days: Number of days to look back for recent modifications (default: 7)
            cursor: Cursor token for pagination (optional)
        """
        if not self.provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search recently modified documents (use query parameter)
            documents_results = (
                await self.provider_client.documents_client.search_documents(
                    query=f"modifiedTime > '{days} days ago'",
                    max_results=10,
                    page_token=cursor,
                )
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.header_page_type,
                    id=document_id,
                )
                for document_id in document_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            # Cast to DocumentHeader list for type safety
            from pragweb.pages import DocumentHeader

            doc_pages = [page for page in pages if isinstance(page, DocumentHeader)]

            return PaginatedResponse(
                results=doc_pages,
                next_cursor=documents_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search recently modified documents: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def search_all_documents(
        self, cursor: Optional[str] = None
    ) -> PaginatedResponse[DocumentHeader]:
        """Get all Google Docs documents (ordered by most recently modified).

        Args:
            cursor: Cursor token for pagination (optional)
        """
        if not self.provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # List all documents
            documents_results = (
                await self.provider_client.documents_client.list_documents(
                    max_results=10,
                    page_token=cursor,
                )
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=self.header_page_type,
                    id=document_id,
                )
                for document_id in document_ids
            ]

            # Resolve URIs to pages
            pages = await self.context.get_pages(uris)
            # Cast to DocumentHeader list for type safety
            from pragweb.pages import DocumentHeader

            doc_pages = [page for page in pages if isinstance(page, DocumentHeader)]

            return PaginatedResponse(
                results=doc_pages,
                next_cursor=documents_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search all documents: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def find_chunks_in_document(
        self, doc_header_uri: str, query: str
    ) -> PaginatedResponse[DocumentChunk]:
        """Search for specific content within a document's chunks.

        Args:
            doc_header_uri: The URI of the Google Docs header page to search within
            query: Search query to find within the document chunks
        """
        try:
            # Get all chunks for the document
            from praga_core.types import PageURI

            header_uri = PageURI.parse(doc_header_uri)
            document_header = await self.context.get_page(header_uri)

            if not isinstance(document_header, DocumentHeader):
                return PaginatedResponse(results=[], next_cursor=None)

            # Get chunk URIs from document header
            chunk_uris = document_header.chunk_uris

            # Resolve URIs to pages
            chunks = await self.context.get_pages(chunk_uris)
            # Cast to DocumentChunk list for type safety
            doc_chunks = [chunk for chunk in chunks if isinstance(chunk, DocumentChunk)]

            # Filter chunks that contain the query
            matching_chunks = []
            for chunk in doc_chunks:
                if (
                    isinstance(chunk, DocumentChunk)
                    and query.lower() in chunk.content.lower()
                ):
                    matching_chunks.append(chunk)

            return PaginatedResponse(
                results=matching_chunks,
                next_cursor=None,
            )
        except Exception as e:
            logger.error(f"Failed to find chunks in document: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    async def get_document_content(
        self,
        document: DocumentHeader,
    ) -> str:
        """Get the full content of a document.

        Args:
            document: Document header page

        Returns:
            Full document content as string
        """
        try:
            provider = self._get_provider_for_document(document)
            if not provider:
                return ""

            return await provider.documents_client.get_document_content(
                document_id=document.provider_document_id,
            )
        except Exception as e:
            logger.error(f"Failed to get document content: {e}")
            return ""

    def _parse_document_uri(self, page_uri: PageURI) -> tuple[str, str]:
        """Parse document URI to extract provider and document ID."""
        # URI format: google_docs_header with document_id as the ID
        return self.provider_name, page_uri.id

    def _parse_chunk_uri(self, page_uri: PageURI) -> tuple[str, str, int]:
        """Parse chunk URI to extract provider, document ID, and chunk index."""
        # URI format: google_docs_chunk with document_id_chunk_index as the ID
        # Extract document ID and chunk index from ID
        # Format: document_id_chunk_index
        last_underscore = page_uri.id.rfind("_")
        if last_underscore == -1:
            raise ValueError(f"Invalid chunk URI format: {page_uri.id}")

        document_id = page_uri.id[:last_underscore]
        chunk_index = int(page_uri.id[last_underscore + 1 :])

        return self.provider_name, document_id, chunk_index

    def _get_provider_for_document(
        self, document: DocumentHeader
    ) -> Optional[BaseProviderClient]:
        """Get provider client for a document."""
        # Since each service instance has only one provider, return it
        return self.provider_client

    def _extract_text_from_content(self, content: List[Dict[str, Any]]) -> str:
        """Extract text content from document structure (provider-agnostic).

        This method handles the common structure used by both Google Docs and
        Microsoft Word documents for extracting plain text content.
        """
        text_parts = []

        for element in content:
            if "paragraph" in element:
                # Extract text from paragraph elements
                paragraph = element["paragraph"]
                for text_element in paragraph.get("elements", []):
                    if "textRun" in text_element:
                        text_parts.append(text_element["textRun"].get("content", ""))
            elif "table" in element:
                # Extract text from table elements
                table = element["table"]
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        cell_text = self._extract_text_from_content(
                            cell.get("content", [])
                        )
                        if cell_text.strip():
                            text_parts.append(cell_text)

        return "".join(text_parts)

    def _chunk_content(self, full_content: str) -> Sequence[RecursiveChunk]:
        """Chunk document content using Chonkie."""
        return self.chunker.chunk(full_content)

    def _build_chunk_pages(
        self,
        document_id: str,
        chunks: Sequence[RecursiveChunk],
        header: DocumentHeader,
        header_uri: PageURI,
    ) -> List[DocumentChunk]:
        """Build DocumentChunk pages from chunked content."""
        chunk_pages: List[DocumentChunk] = []

        for i, chunk in enumerate(chunks):
            chunk_text = getattr(chunk, "text", str(chunk))
            chunk_title = self._get_chunk_title(chunk_text)

            # Build chunk URI
            chunk_uri = PageURI(
                root=header_uri.root,
                type=self.chunk_page_type,
                id=f"{document_id}_{i}",
                version=header_uri.version,
            )

            # Navigation URIs
            prev_chunk_uri = None
            if i > 0:
                prev_chunk_uri = PageURI(
                    root=header_uri.root,
                    type=self.chunk_page_type,
                    id=f"{document_id}_{i-1}",
                    version=header_uri.version,
                )

            next_chunk_uri = None
            if i < len(chunks) - 1:
                next_chunk_uri = PageURI(
                    root=header_uri.root,
                    type=self.chunk_page_type,
                    id=f"{document_id}_{i+1}",
                    version=header_uri.version,
                )

            # Create chunk page
            chunk_page = DocumentChunk(
                uri=chunk_uri,
                provider_document_id=document_id,
                chunk_index=i,
                chunk_title=chunk_title,
                content=chunk_text,
                doc_title=header.title,
                header_uri=header_uri,
                prev_chunk_uri=prev_chunk_uri,
                next_chunk_uri=next_chunk_uri,
                permalink=header.permalink,
            )
            chunk_pages.append(chunk_page)

        return chunk_pages

    async def _store_chunk_pages(
        self, chunk_pages: List[DocumentChunk], header: DocumentHeader
    ) -> None:
        """Store chunk pages in the cache asynchronously."""
        if not chunk_pages:
            return

        # Ensure DocumentChunk type is registered first to avoid race condition
        await self.context.page_cache._registry.ensure_registered(DocumentChunk)

        # Store all chunks in parallel using context
        tasks = [
            self.context.page_cache.store(chunk_page, parent_uri=header.uri)
            for chunk_page in chunk_pages
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for exceptions and log them
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to store chunk {i}: {result}")
                raise result

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

    def _build_document_header(
        self,
        document_data: Dict[str, Any],
        document_content: str,
        chunks: Sequence[RecursiveChunk],
        page_uri: PageURI,
        document_id: str,
    ) -> DocumentHeader:
        """Build DocumentHeader from document data and chunks."""
        # Extract metadata from document data
        title = document_data.get("title", "Untitled Document")

        # Build chunk URIs
        chunk_uris = []
        for i in range(len(chunks)):
            chunk_uris.append(
                PageURI(
                    root=page_uri.root,
                    type=self.chunk_page_type,
                    id=f"{document_id}_{i}",
                    version=page_uri.version or 1,
                )
            )

        # Create summary from content
        summary = (
            document_content[:500] + "..."
            if len(document_content) > 500
            else document_content
        )
        word_count = len(document_content.split()) if document_content else 0

        # Extract timestamps and owner info (provider-specific)
        created_time = datetime.now(timezone.utc)  # Fallback
        modified_time = datetime.now(timezone.utc)  # Fallback
        owner = None

        # Try to get actual metadata from provider if available
        try:
            # For Google Docs, we might have metadata in the document_data
            if "createdTime" in document_data:
                created_time = self._parse_datetime(document_data["createdTime"])
            if "modifiedTime" in document_data:
                modified_time = self._parse_datetime(document_data["modifiedTime"])
            if "owners" in document_data and document_data["owners"]:
                owner = document_data["owners"][0].get("emailAddress")
        except Exception:
            pass  # Use fallback values

        # Ensure the URI has a version
        if page_uri.version is None:
            page_uri = PageURI(
                root=page_uri.root,
                type=page_uri.type,
                id=page_uri.id,
                version=1,
            )

        return DocumentHeader(
            uri=page_uri,
            provider_document_id=document_id,
            title=title,
            summary=summary,
            created_time=created_time,
            modified_time=modified_time,
            owner=owner,
            word_count=word_count,
            chunk_count=len(chunks),
            chunk_uris=chunk_uris,
            permalink=self._build_permalink(document_id),
        )

    def _parse_datetime(self, dt_str: str) -> datetime:
        """Parse datetime string from provider API."""
        if dt_str.endswith("Z"):
            return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        else:
            return datetime.fromisoformat(dt_str)

    def _build_permalink(self, document_id: str) -> str:
        """Build permalink URL for document."""
        if self.provider_name == "google":
            return f"https://docs.google.com/document/d/{document_id}/edit"
        elif self.provider_name == "microsoft":
            # Microsoft Word Online URL format
            return f"https://office365.com/word?resid={document_id}"
        else:
            return f"https://docs.{self.provider_name}.com/document/{document_id}"

    async def _validate_document_header(self, document: DocumentHeader) -> bool:
        """Validate that a document header is up to date (provider-agnostic)."""
        try:
            provider = self._get_provider_for_document(document)
            if not provider:
                return False

            # Get document metadata from provider
            doc_data = await provider.documents_client.get_document(
                document.provider_document_id
            )

            # Extract modified time from document data (handle both Google and Microsoft formats)
            api_modified_time_str = doc_data.get("modifiedTime") or doc_data.get(
                "lastModifiedDateTime"
            )
            if not api_modified_time_str:
                return True  # If no modified time available, assume valid

            # Parse API modified time (handle both ISO formats)
            from datetime import datetime

            if api_modified_time_str.endswith("Z"):
                api_modified_time = datetime.fromisoformat(
                    api_modified_time_str.replace("Z", "+00:00")
                )
            else:
                api_modified_time = datetime.fromisoformat(api_modified_time_str)

            # Compare with header modified time
            header_modified_time = document.modified_time

            # Return True if API time is older or equal (header is up to date)
            return api_modified_time <= header_modified_time

        except Exception as e:
            logger.warning(f"Failed to validate document header: {e}")
            return False
