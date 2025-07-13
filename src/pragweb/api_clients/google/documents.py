"""Google-specific documents client implementation."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.api_clients.base import BaseDocumentsClient
from pragweb.pages import DocumentChunk, DocumentHeader

from .auth import GoogleAuthManager


class GoogleDocumentsClient(BaseDocumentsClient):
    """Google-specific documents client implementation."""

    def __init__(self, auth_manager: GoogleAuthManager):
        self.auth_manager = auth_manager
        self._executor = ThreadPoolExecutor(
            max_workers=10, thread_name_prefix="google-docs-client"
        )

    @property
    def _docs(self) -> Any:
        """Get Docs service instance."""
        return self.auth_manager.get_docs_service()

    @property
    def _drive(self) -> Any:
        """Get Drive service instance."""
        return self.auth_manager.get_drive_service()

    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get a Google Document by ID."""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (self._docs.documents().get(documentId=document_id).execute()),
        )
        return dict(result)

    async def list_documents(
        self, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List Google Documents."""
        query = "mimeType='application/vnd.google-apps.document'"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._drive.files()
                .list(
                    q=query,
                    pageSize=max_results,
                    pageToken=page_token,
                    fields="nextPageToken, files(id, name, createdTime, modifiedTime, owners, webViewLink, size, mimeType, parents)",
                )
                .execute()
            ),
        )
        return dict(result)

    async def search_documents(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search Google Documents."""
        search_query = f"mimeType='application/vnd.google-apps.document' and fullText contains '{query}'"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (
                self._drive.files()
                .list(
                    q=search_query,
                    pageSize=max_results,
                    pageToken=page_token,
                    fields="nextPageToken, files(id, name, createdTime, modifiedTime, owners, webViewLink, size, mimeType, parents)",
                )
                .execute()
            ),
        )
        return dict(result)

    async def get_document_content(self, document_id: str) -> str:
        """Get full Google Document content."""
        doc = await self.get_document(document_id)

        # Extract text content from document structure
        content = ""
        if "body" in doc:
            content = self._extract_text_from_body(doc["body"])

        return content

    def _extract_text_from_body(self, body: Dict[str, Any]) -> str:
        """Extract text content from document body."""
        text = ""

        for content_item in body.get("content", []):
            if "paragraph" in content_item:
                paragraph = content_item["paragraph"]
                for element in paragraph.get("elements", []):
                    if "textRun" in element:
                        text += element["textRun"].get("content", "")
            elif "table" in content_item:
                # Handle table content
                table = content_item["table"]
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        text += self._extract_text_from_body(cell)

        return text

    async def create_document(
        self, title: str, content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new Google Document."""
        doc_body = {"title": title}

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: (self._docs.documents().create(body=doc_body).execute()),
        )

        # If content provided, add it to the document
        if content:
            document_id = result["documentId"]
            requests = [{"insertText": {"location": {"index": 1}, "text": content}}]

            await loop.run_in_executor(
                self._executor,
                lambda: (
                    self._docs.documents()
                    .batchUpdate(documentId=document_id, body={"requests": requests})
                    .execute()
                ),
            )

        return dict(result)

    async def update_document(self, document_id: str, **updates: Any) -> Dict[str, Any]:
        """Update a Google Document."""
        requests = []

        if "title" in updates:
            requests.append(
                {
                    "updateDocumentStyle": {
                        "documentStyle": {"title": updates["title"]},
                        "fields": "title",
                    }
                }
            )

        if "content" in updates:
            # Replace all content
            requests.append(
                {"deleteContentRange": {"range": {"startIndex": 1, "endIndex": -1}}}
            )
            requests.append(
                {"insertText": {"location": {"index": 1}, "text": updates["content"]}}
            )

        if requests:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self._executor,
                lambda: (
                    self._docs.documents()
                    .batchUpdate(documentId=document_id, body={"requests": requests})
                    .execute()
                ),
            )
            return dict(result)

        return {}

    async def delete_document(self, document_id: str) -> bool:
        """Delete a Google Document."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                self._executor,
                lambda: (self._drive.files().delete(fileId=document_id).execute()),
            )
            return True
        except Exception:
            return False

    async def parse_document_to_header_page(
        self, document_data: Dict[str, Any], page_uri: PageURI
    ) -> DocumentHeader:
        """Parse Google Document data to DocumentHeader."""
        # Extract document metadata
        title = document_data.get("title", "")
        doc_id = document_data.get("documentId", "")

        # Get additional metadata from Drive API (async)
        loop = asyncio.get_event_loop()
        drive_metadata = await loop.run_in_executor(
            self._executor,
            lambda: self._drive.files()
            .get(fileId=doc_id, fields="createdTime,modifiedTime,owners")
            .execute(),
        )

        # Extract required metadata fields
        if "createdTime" not in drive_metadata:
            raise ValueError(f"Document {doc_id} missing createdTime metadata")
        if "modifiedTime" not in drive_metadata:
            raise ValueError(f"Document {doc_id} missing modifiedTime metadata")
        if "owners" not in drive_metadata or not drive_metadata["owners"]:
            raise ValueError(f"Document {doc_id} missing owners metadata")

        created_time = datetime.fromisoformat(
            drive_metadata["createdTime"].replace("Z", "+00:00")
        ).replace(tzinfo=None)
        modified_time = datetime.fromisoformat(
            drive_metadata["modifiedTime"].replace("Z", "+00:00")
        ).replace(tzinfo=None)
        owner = drive_metadata["owners"][0].get("emailAddress")

        if not owner:
            raise ValueError(f"Document {doc_id} owner missing email address")

        # Extract content for summary
        content = ""
        if "body" in document_data:
            content = self._extract_text_from_body(document_data["body"])

        summary = content[:500] if content else ""
        word_count = len(content.split()) if content else 0

        # Create chunks (for now, just one chunk with all content)
        chunks = self._create_chunks(content, page_uri, title)
        chunk_count = len(chunks)

        chunk_uris = []
        for i in range(chunk_count):
            chunk_uris.append(
                PageURI(
                    root=page_uri.root,
                    type="document_chunk",
                    id=f"{doc_id}_{i}",
                    version=page_uri.version,
                )
            )

        return DocumentHeader(
            uri=page_uri,
            provider_document_id=doc_id,
            title=title,
            summary=summary,
            created_time=created_time,
            modified_time=modified_time,
            owner=owner,
            word_count=word_count,
            chunk_count=chunk_count,
            chunk_uris=chunk_uris,
            permalink=f"https://docs.google.com/document/d/{doc_id}",
        )

    def parse_document_to_chunks(
        self, document_data: Dict[str, Any], header_uri: PageURI
    ) -> List[DocumentChunk]:
        """Parse Google Document data to DocumentChunk list."""
        content = ""
        if "body" in document_data:
            content = self._extract_text_from_body(document_data["body"])

        # Extract title from document data
        title = document_data.get("title", "")
        return self._create_chunks(content, header_uri, title)

    def _create_chunks(
        self, content: str, header_uri: PageURI, doc_title: str
    ) -> List[DocumentChunk]:
        """Create chunks from document content."""
        chunks = []
        doc_id = header_uri.id

        # Simple chunking strategy: split by paragraphs, max 1000 words per chunk
        paragraphs = content.split("\n\n")
        current_chunk = ""
        chunk_index = 0

        for paragraph in paragraphs:
            if len(current_chunk.split()) + len(paragraph.split()) > 1000:
                if current_chunk:
                    # Create chunk
                    chunk_title_words = current_chunk.split()[:5]  # First 5 words
                    chunk_title = " ".join(chunk_title_words) + "..."

                    chunk_uri = PageURI(
                        root=header_uri.root,
                        type="document_chunk",
                        id=f"{doc_id}_{chunk_index}",
                        version=header_uri.version,
                    )

                    prev_chunk_uri = None
                    if chunk_index > 0:
                        prev_chunk_uri = PageURI(
                            root=header_uri.root,
                            type="document_chunk",
                            id=f"{doc_id}_{chunk_index - 1}",
                            version=header_uri.version,
                        )

                    chunks.append(
                        DocumentChunk(
                            uri=chunk_uri,
                            provider_document_id=doc_id,
                            chunk_index=chunk_index,
                            chunk_title=chunk_title,
                            content=current_chunk,
                            doc_title=doc_title,
                            header_uri=header_uri,
                            prev_chunk_uri=prev_chunk_uri,
                            next_chunk_uri=None,  # Will be set later
                            permalink=f"https://docs.google.com/document/d/{doc_id}",
                        )
                    )

                    chunk_index += 1
                    current_chunk = paragraph
            else:
                current_chunk += "\n\n" + paragraph if current_chunk else paragraph

        # Add final chunk
        if current_chunk:
            chunk_title_words = current_chunk.split()[:5]
            chunk_title = " ".join(chunk_title_words) + "..."

            chunk_uri = PageURI(
                root=header_uri.root,
                type="document_chunk",
                id=f"{doc_id}_{chunk_index}",
                version=header_uri.version,
            )

            prev_chunk_uri = None
            if chunk_index > 0:
                prev_chunk_uri = PageURI(
                    root=header_uri.root,
                    type="document_chunk",
                    id=f"{doc_id}_{chunk_index - 1}",
                    version=header_uri.version,
                )

            chunks.append(
                DocumentChunk(
                    uri=chunk_uri,
                    provider_document_id=doc_id,
                    chunk_index=chunk_index,
                    chunk_title=chunk_title,
                    content=current_chunk,
                    doc_title=doc_title,
                    header_uri=header_uri,
                    prev_chunk_uri=prev_chunk_uri,
                    next_chunk_uri=None,  # Will be set later
                    permalink=f"https://docs.google.com/document/d/{doc_id}",
                )
            )

        # Update next_chunk_uri for all chunks except the last one
        for i in range(len(chunks) - 1):
            chunks[i].next_chunk_uri = chunks[i + 1].uri

        return chunks
