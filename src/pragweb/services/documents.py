"""Documents orchestration service that coordinates between multiple providers."""

import logging
from typing import Any, Dict, List, Optional

from praga_core.agents import PaginatedResponse, tool
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import DocumentChunk, DocumentHeader
from pragweb.toolkit_service import ToolkitService

logger = logging.getLogger(__name__)


class DocumentService(ToolkitService):
    """Orchestration service for document operations across multiple providers."""

    def __init__(self, providers: Dict[str, BaseProviderClient]):
        if not providers:
            raise ValueError("DocumentService requires at least one provider")
        if len(providers) != 1:
            raise ValueError("DocumentService requires exactly one provider")

        self.providers = providers
        super().__init__()
        self._register_handlers()
        logger.info(
            "Document service initialized with providers: %s", list(providers.keys())
        )

    @property
    def name(self) -> str:
        """Service name used for registration."""
        # Auto-derive service name from provider
        provider_name = list(self.providers.keys())[0]
        provider_to_service = {"google": "google_docs", "microsoft": "outlook_docs"}
        return provider_to_service.get(provider_name, f"{provider_name}_docs")

    def _register_handlers(self) -> None:
        """Register page routes and actions with context."""
        ctx = self.context

        # Register page route handlers using dynamic service name
        service_name = self.name

        @ctx.route(f"{service_name}_header", cache=True)
        async def handle_document_header(page_uri: PageURI) -> DocumentHeader:
            return await self.create_document_header_page(page_uri)

        @ctx.route(f"{service_name}_chunk", cache=True)
        async def handle_document_chunk(page_uri: PageURI) -> DocumentChunk:
            return await self.create_document_chunk_page(page_uri)

        # Register document actions
        @ctx.action()
        async def update_document(
            document: DocumentHeader,
            title: Optional[str] = None,
            content: Optional[str] = None,
        ) -> bool:
            """Update a document."""
            try:
                provider = self._get_provider_for_document(document)
                if not provider:
                    return False

                updates = {}
                if title is not None:
                    updates["title"] = title
                if content is not None:
                    updates["content"] = content

                await provider.documents_client.update_document(
                    document_id=document.provider_document_id,
                    **updates,
                )

                return True
            except Exception as e:
                logger.error(f"Failed to update document: {e}")
                return False

        @ctx.action()
        async def delete_document(document: DocumentHeader) -> bool:
            """Delete a document."""
            try:
                provider = self._get_provider_for_document(document)
                if not provider:
                    return False

                return await provider.documents_client.delete_document(
                    document_id=document.provider_document_id,
                )
            except Exception as e:
                logger.error(f"Failed to delete document: {e}")
                return False

    async def create_document_header_page(self, page_uri: PageURI) -> DocumentHeader:
        """Create a DocumentHeader from a URI."""
        # Extract provider and document ID from URI
        provider_name, document_id = self._parse_document_uri(page_uri)

        provider = self.providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name} not available")

        # Get document data from provider
        document_data = await provider.documents_client.get_document(document_id)

        # Parse to DocumentHeader
        return await provider.documents_client.parse_document_to_header_page(
            document_data, page_uri
        )

    async def create_document_chunk_page(self, page_uri: PageURI) -> DocumentChunk:
        """Create a DocumentChunk from a URI."""
        # Extract provider, document ID, and chunk index from URI
        provider_name, document_id, chunk_index = self._parse_chunk_uri(page_uri)

        provider = self.providers.get(provider_name)
        if not provider:
            raise ValueError(f"Provider {provider_name} not available")

        # Get document data from provider
        document_data = await provider.documents_client.get_document(document_id)

        # Create header URI for parsing chunks
        header_uri = PageURI(
            root=page_uri.root,
            type=f"{self.name}_header",
            id=document_id,
            version=page_uri.version,
        )

        # Parse to DocumentChunk list and return the requested chunk
        chunks = provider.documents_client.parse_document_to_chunks(
            document_data, header_uri
        )

        if chunk_index >= len(chunks):
            raise ValueError(f"Chunk index {chunk_index} out of range")

        return chunks[chunk_index]

    @tool()
    async def search_documents(
        self,
        query: str,
        provider: str = "google",
        max_results: int = 10,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[DocumentHeader]:
        """Search for documents across providers.

        Args:
            query: Search query string
            provider: Provider to search (google, microsoft, etc.)
            max_results: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            Paginated response of matching document header pages
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search documents
            search_results = await provider_client.documents_client.search_documents(
                query=query,
                max_results=max_results,
                page_token=cursor,
            )

            # Extract document IDs
            document_ids = []
            for doc in search_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=f"{self.name}_header",
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
                next_cursor=search_results.get("nextPageToken"),
            )
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            return PaginatedResponse(results=[], next_cursor=None)

    @tool()
    async def get_all_documents(
        self,
        provider: str = "google",
        max_results: int = 10,
        cursor: Optional[str] = None,
    ) -> PaginatedResponse[DocumentHeader]:
        """Get all documents from a provider.

        Args:
            provider: Provider to search (google, microsoft, etc.)
            max_results: Maximum number of results to return
            cursor: Pagination cursor

        Returns:
            Paginated response of document header pages
        """
        provider_client = self.providers.get(provider)
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # List documents
            documents_results = await provider_client.documents_client.list_documents(
                max_results=max_results,
                page_token=cursor,
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=f"{self.name}_header",
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
        provider_client = list(self.providers.values())[0] if self.providers else None
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search documents by owner (use query parameter)
            documents_results = await provider_client.documents_client.search_documents(
                query=f"owner:{owner_identifier}",
                max_results=10,
                page_token=cursor,
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=f"{self.name}_header",
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
        provider_client = list(self.providers.values())[0] if self.providers else None
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # Search recently modified documents (use query parameter)
            documents_results = await provider_client.documents_client.search_documents(
                query=f"modifiedTime > '{days} days ago'",
                max_results=10,
                page_token=cursor,
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=f"{self.name}_header",
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
        provider_client = list(self.providers.values())[0] if self.providers else None
        if not provider_client:
            return PaginatedResponse(results=[], next_cursor=None)

        try:
            # List all documents
            documents_results = await provider_client.documents_client.list_documents(
                max_results=10,
                page_token=cursor,
            )

            # Extract document IDs
            document_ids = []
            for doc in documents_results.get("files", []):
                document_ids.append(doc["id"])

            # Create URIs
            uris = [
                PageURI(
                    root=self.context.root,
                    type=f"{self.name}_header",
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

            chunks = await self.get_document_chunks(document_header)

            # Filter chunks that contain the query
            matching_chunks = []
            for chunk in chunks:
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

    @tool()
    async def get_document_chunks(
        self,
        document: DocumentHeader,
    ) -> List[DocumentChunk]:
        """Get all chunks for a document.

        Args:
            document: Document header page

        Returns:
            List of document chunks
        """
        try:
            # Get chunk URIs from document header
            chunk_uris = document.chunk_uris

            # Resolve URIs to pages
            chunks = await self.context.get_pages(chunk_uris)
            # Cast to DocumentChunk list for type safety
            from pragweb.pages import DocumentChunk

            doc_chunks = [chunk for chunk in chunks if isinstance(chunk, DocumentChunk)]

            return doc_chunks
        except Exception as e:
            logger.error(f"Failed to get document chunks: {e}")
            return []

    @tool()
    async def search_document_content(
        self,
        query: str,
        document: DocumentHeader,
    ) -> List[DocumentChunk]:
        """Search within a document's content.

        Args:
            query: Search query string
            document: Document header page

        Returns:
            List of document chunks matching the query
        """
        try:
            # Get all chunks for the document
            chunks = await self.get_document_chunks(document)

            # Filter chunks that contain the query
            from pragweb.pages import DocumentChunk

            matching_chunks = []
            for chunk in chunks:
                if (
                    isinstance(chunk, DocumentChunk)
                    and query.lower() in chunk.content.lower()
                ):
                    matching_chunks.append(chunk)

            return matching_chunks
        except Exception as e:
            logger.error(f"Failed to search document content: {e}")
            return []

    def _parse_document_uri(self, page_uri: PageURI) -> tuple[str, str]:
        """Parse document URI to extract provider and document ID."""
        # URI format: google_docs_header with document_id as the ID
        # Extract provider from service name
        if not self.providers:
            raise ValueError("No provider available for service")
        provider_name = list(self.providers.keys())[0]
        return provider_name, page_uri.id

    def _parse_chunk_uri(self, page_uri: PageURI) -> tuple[str, str, int]:
        """Parse chunk URI to extract provider, document ID, and chunk index."""
        # URI format: google_docs_chunk with document_id_chunk_index as the ID
        provider_name = list(self.providers.keys())[0] if self.providers else "google"

        # Extract document ID and chunk index from ID
        # Format: document_id_chunk_index
        last_underscore = page_uri.id.rfind("_")
        if last_underscore == -1:
            raise ValueError(f"Invalid chunk URI format: {page_uri.id}")

        document_id = page_uri.id[:last_underscore]
        chunk_index = int(page_uri.id[last_underscore + 1 :])

        return provider_name, document_id, chunk_index

    def _get_provider_for_document(
        self, document: DocumentHeader
    ) -> Optional[BaseProviderClient]:
        """Get provider client for a document."""
        # Since each service instance has only one provider, return it
        return list(self.providers.values())[0] if self.providers else None

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

    def _get_chunk_title(self, content: str, max_length: int = 50) -> str:
        """Generate a title for a document chunk from its content (provider-agnostic)."""
        # Remove extra whitespace and newlines
        clean_content = " ".join(content.split())

        if len(clean_content) <= max_length:
            return clean_content

        # Truncate and add ellipsis
        return clean_content[: max_length - 3] + "..."

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
