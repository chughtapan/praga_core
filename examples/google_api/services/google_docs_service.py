"""Google Docs service with chunking, caching, and ingestion using Chonkie."""

import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from chonkie import RecursiveChunker
from sqlmodel import Field, Session, SQLModel, create_engine, select

from praga_core.context import ServerContext
from praga_core.types import PageURI

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import GoogleAuthManager  # noqa: E402
from pages.google_docs import GDocChunk, GDocHeader  # noqa: E402

logger = logging.getLogger(__name__)


# SQLModel for document storage
class DocumentRecord(SQLModel, table=True):
    """SQLModel for storing document metadata."""

    __tablename__ = "documents"

    document_id: str = Field(primary_key=True)
    title: str
    content: str  # Full document content
    created_time: datetime
    modified_time: datetime
    owner: Optional[str] = None
    word_count: int
    chunk_count: int
    ingested: bool = Field(default=False)


class ChunkRecord(SQLModel, table=True):
    """SQLModel for storing document chunks."""

    __tablename__ = "chunks"

    id: str = Field(primary_key=True)  # document_id:chunk_index
    document_id: str = Field(foreign_key="documents.document_id", index=True)
    chunk_index: int
    chunk_title: str
    content: str
    token_count: int


class GoogleDocsService:
    """Service for Google Docs with chunking, caching, and ingestion."""

    def __init__(self, context: ServerContext):
        self.context = context
        self.root = context.root
        self.auth_manager = GoogleAuthManager()
        self.docs_service = self.auth_manager.get_docs_service()
        self.drive_service = self.auth_manager.get_drive_service()

        # Setup SQLite in-memory database
        self.engine = create_engine("sqlite:///:memory:")
        SQLModel.metadata.create_all(self.engine)

        # Initialize Chonkie chunker with ~4K tokens and document structure awareness
        self.chunker = RecursiveChunker(
            tokenizer_or_token_counter="gpt2",
            chunk_size=4000,  # ~4K tokens
        )

        # Register handlers with context
        self.context.register_handler("gdoc_header", self.create_header_page)
        self.context.register_handler("gdoc_chunk", self.create_chunk_page)
        logger.info("Google Docs service initialized with chunking and caching")

    def _extract_text_from_content(self, content: List[Dict[str, Any]]) -> str:
        """Extract plain text from Google Docs content structure."""
        text_parts = []

        def extract_from_element(element):
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

    def ingest_document(self, document_id: str) -> None:
        """Ingest a document by fetching content, chunking, and storing in cache."""
        logger.info(f"Starting ingestion for document: {document_id}")

        try:
            # Fetch the document content from Docs API
            doc = self.docs_service.documents().get(documentId=document_id).execute()

            # Fetch file metadata from Drive API
            file_metadata = (
                self.drive_service.files()
                .get(fileId=document_id, fields="name,createdTime,modifiedTime,owners")
                .execute()
            )

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

        # Store document and chunks in database
        with Session(self.engine) as session:
            # Store document metadata
            doc_record = DocumentRecord(
                document_id=document_id,
                title=title,
                content=full_content,
                created_time=created_time,
                modified_time=modified_time,
                owner=owner,
                word_count=word_count,
                chunk_count=chunk_count,
                ingested=True,
            )
            session.merge(doc_record)  # Use merge to handle duplicates

            # Store chunks
            for i, chunk in enumerate(chunks):
                chunk_id = f"{document_id}({i})"
                chunk_title = self._get_chunk_title(chunk.text)

                chunk_record = ChunkRecord(
                    id=chunk_id,
                    document_id=document_id,
                    chunk_index=i,
                    chunk_title=chunk_title,
                    content=chunk.text,
                    token_count=chunk.token_count,
                )
                session.merge(chunk_record)  # Use merge to handle duplicates

            session.commit()

        logger.info(
            f"Successfully ingested document {document_id} with {chunk_count} chunks"
        )

    def create_header_page(self, document_id: str) -> GDocHeader:
        """Create a GDocHeader page from cache or ingest if needed."""
        # Check if document is in cache
        with Session(self.engine) as session:
            doc_record = session.get(DocumentRecord, document_id)

            if not doc_record or not doc_record.ingested:
                # Document not cached, ingest it
                self.ingest_document(document_id)
                doc_record = session.get(DocumentRecord, document_id)

            if not doc_record:
                raise ValueError(f"Failed to ingest document {document_id}")

            # Get all chunks for this document to create URIs
            stmt = (
                select(ChunkRecord)
                .where(ChunkRecord.document_id == document_id)
                .order_by(ChunkRecord.chunk_index)
            )
            chunk_records = session.exec(stmt).all()

            # Create chunk URIs
            chunk_uris = [
                PageURI(
                    root=self.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({chunk.chunk_index})",
                )
                for chunk in chunk_records
            ]

            # Create summary (first 500 chars + chunk info)
            summary = doc_record.content[:500]
            if len(doc_record.content) > 500:
                summary += "..."
            summary += f" [{doc_record.chunk_count} chunks]"

            # Create permalink
            permalink = f"https://docs.google.com/document/d/{document_id}/edit"

            # Create and return header page
            uri = PageURI(root=self.root, type="gdoc_header", id=document_id)
            return GDocHeader(
                uri=uri,
                document_id=document_id,
                title=doc_record.title,
                summary=summary,
                created_time=doc_record.created_time,
                modified_time=doc_record.modified_time,
                owner=doc_record.owner,
                word_count=doc_record.word_count,
                chunk_count=doc_record.chunk_count,
                chunk_uris=chunk_uris,
                permalink=permalink,
            )

    def create_chunk_page(self, chunk_id: str) -> GDocChunk:
        """Create a GDocChunk page from cache."""
        # Parse chunk_id (format: "document_id(chunk_index)")
        if "(" not in chunk_id or not chunk_id.endswith(")"):
            raise ValueError(f"Invalid chunk ID format: {chunk_id}")

        document_id = chunk_id[: chunk_id.rfind("(")]
        chunk_index_str = chunk_id[chunk_id.rfind("(") + 1 : -1]
        try:
            chunk_index = int(chunk_index_str)
        except ValueError:
            raise ValueError(f"Invalid chunk index in ID: {chunk_id}")

        with Session(self.engine) as session:
            # Get the chunk
            chunk_record = session.get(ChunkRecord, chunk_id)
            if not chunk_record:
                # Try to ingest the document if chunk not found
                self.ingest_document(document_id)
                chunk_record = session.get(ChunkRecord, chunk_id)

            if not chunk_record:
                raise ValueError(f"Chunk {chunk_id} not found after ingestion")

            # Get document for title and other info
            doc_record = session.get(DocumentRecord, document_id)
            if not doc_record:
                raise ValueError(f"Document {document_id} not found")

            # Create next/prev chunk URIs
            prev_chunk_uri = None
            if chunk_index > 0:
                prev_chunk_uri = PageURI(
                    root=self.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({chunk_index - 1})",
                )

            next_chunk_uri = None
            if chunk_index < doc_record.chunk_count - 1:
                next_chunk_uri = PageURI(
                    root=self.root,
                    type="gdoc_chunk",
                    id=f"{document_id}({chunk_index + 1})",
                )

            # Create header URI
            header_uri = PageURI(root=self.root, type="gdoc_header", id=document_id)

            # Create permalink
            permalink = f"https://docs.google.com/document/d/{document_id}/edit"

            # Create and return chunk page
            uri = PageURI(root=self.root, type="gdoc_chunk", id=chunk_id)
            return GDocChunk(
                uri=uri,
                document_id=document_id,
                chunk_index=chunk_index,
                chunk_title=chunk_record.chunk_title,
                content=chunk_record.content,
                doc_title=doc_record.title,
                token_count=chunk_record.token_count,
                prev_chunk_uri=prev_chunk_uri,
                next_chunk_uri=next_chunk_uri,
                header_uri=header_uri,
                permalink=permalink,
            )

    def search_document_headers(
        self, query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search documents and return header URIs (using Drive API for discovery)."""
        try:
            # Build Drive API query for Google Docs
            drive_query = (
                "mimeType='application/vnd.google-apps.document' and trashed=false"
            )

            if query.strip():
                # Add fullText search if query provided
                drive_query += f" and fullText contains '{query}'"

            logger.debug(
                f"Drive search query: '{drive_query}', page_token: {page_token}"
            )

            # Search for files with pagination
            search_params = {
                "q": drive_query,
                "pageSize": page_size,
                "fields": "nextPageToken,files(id,name,modifiedTime)",
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                search_params["pageToken"] = page_token

            results = self.drive_service.files().list(**search_params).execute()
            files = results.get("files", [])
            next_page_token = results.get("nextPageToken")

            logger.debug(
                f"Drive API returned {len(files)} documents, next_token: {bool(next_page_token)}"
            )

            # Convert to Header PageURIs (ingestion will happen when header is accessed)
            uris = [
                PageURI(root=self.root, type="gdoc_header", id=file["id"])
                for file in files
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching documents: {e}")
            raise

    def search_document_headers_by_title(
        self, title_query: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search documents by title."""
        try:
            drive_query = f"mimeType='application/vnd.google-apps.document' and trashed=false and name contains '{title_query}'"

            search_params = {
                "q": drive_query,
                "pageSize": page_size,
                "fields": "nextPageToken,files(id,name,modifiedTime)",
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                search_params["pageToken"] = page_token

            results = self.drive_service.files().list(**search_params).execute()
            files = results.get("files", [])
            next_page_token = results.get("nextPageToken")

            uris = [
                PageURI(root=self.root, type="gdoc_header", id=file["id"])
                for file in files
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching documents by title: {e}")
            raise

    def search_document_headers_by_owner(
        self, owner_email: str, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search documents by owner email."""
        try:
            # Use the "from" operator to search by owner
            drive_query = f"mimeType='application/vnd.google-apps.document' and trashed=false and '{owner_email}' in owners"

            search_params = {
                "q": drive_query,
                "pageSize": page_size,
                "fields": "nextPageToken,files(id,name,modifiedTime)",
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                search_params["pageToken"] = page_token

            results = self.drive_service.files().list(**search_params).execute()
            files = results.get("files", [])
            next_page_token = results.get("nextPageToken")

            uris = [
                PageURI(root=self.root, type="gdoc_header", id=file["id"])
                for file in files
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching documents by owner: {e}")
            raise

    def search_recent_document_headers(
        self, days: int = 7, page_token: Optional[str] = None, page_size: int = 20
    ) -> Tuple[List[PageURI], Optional[str]]:
        """Search for recently modified documents."""
        try:
            from datetime import timedelta

            recent_date = (datetime.now() - timedelta(days=days)).isoformat() + "Z"

            drive_query = f"mimeType='application/vnd.google-apps.document' and trashed=false and modifiedTime > '{recent_date}'"

            search_params = {
                "q": drive_query,
                "pageSize": page_size,
                "fields": "nextPageToken,files(id,name,modifiedTime)",
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                search_params["pageToken"] = page_token

            results = self.drive_service.files().list(**search_params).execute()
            files = results.get("files", [])
            next_page_token = results.get("nextPageToken")

            uris = [
                PageURI(root=self.root, type="gdoc_header", id=file["id"])
                for file in files
            ]

            return uris, next_page_token

        except Exception as e:
            logger.error(f"Error searching recent documents: {e}")
            raise

    def search_chunks_in_document(
        self, document_id: str, query: str
    ) -> List[GDocChunk]:
        """Search for chunks within a specific document using BM25-like scoring."""
        # Ensure document is ingested
        with Session(self.engine) as session:
            doc_record = session.get(DocumentRecord, document_id)
            if not doc_record or not doc_record.ingested:
                self.ingest_document(document_id)

            # Get all chunks for this document
            stmt = (
                select(ChunkRecord)
                .where(ChunkRecord.document_id == document_id)
                .order_by(ChunkRecord.chunk_index)
            )
            chunk_records = session.exec(stmt).all()

            if not chunk_records:
                return []

            # Simple BM25-like scoring
            query_terms = query.lower().split()
            scored_chunks = []

            for chunk_record in chunk_records:
                content_lower = chunk_record.content.lower()
                score = 0

                # Simple term frequency scoring
                for term in query_terms:
                    # Term frequency
                    tf = content_lower.count(term)
                    if tf > 0:
                        # Simple TF-IDF approximation
                        score += tf * (1 + len(term))  # Longer terms get higher weight

                if score > 0:
                    scored_chunks.append((score, chunk_record))

            # Sort by score (descending) and convert to GDocChunk objects
            scored_chunks.sort(key=lambda x: x[0], reverse=True)

            result_chunks = []
            for score, chunk_record in scored_chunks[:10]:  # Return top 10 matches
                chunk_page = self.create_chunk_page(chunk_record.id)
                result_chunks.append(chunk_page)

            return result_chunks

    def get_document_header(self, document_id: str) -> GDocHeader:
        """Handler method for getting document headers."""
        return self.create_header_page(document_id)

    def get_document_chunk(self, chunk_id: str) -> GDocChunk:
        """Handler method for getting document chunks."""
        return self.create_chunk_page(chunk_id)

    @property
    def name(self) -> str:
        return "gdocs"
