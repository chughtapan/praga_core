"""Tests for Google Documents integration with the new architecture."""

import tempfile
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.page_cache.schema import Base, clear_table_registry
from praga_core.types import PageURI
from pragweb.pages import (
    DocumentChunk,
    DocumentHeader,
    DocumentPermission,
    DocumentType,
)
from pragweb.services import DocumentService


class MockGoogleDocumentsClient:
    """Mock Google Documents client for testing."""

    def __init__(self):
        self.documents = {}
        self.files = {}

    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get document by ID."""
        return self.documents.get(document_id, {})

    async def get_document_content(self, document_id: str) -> str:
        """Get document content as text."""
        doc = self.documents.get(document_id, {})
        return doc.get("content", "")

    async def search_documents(
        self, query: str, max_results: int = 10, page_token: str = None
    ) -> Dict[str, Any]:
        """Search documents."""
        return {"files": [], "nextPageToken": None}

    async def list_documents(
        self, max_results: int = 10, page_token: str = None
    ) -> Dict[str, Any]:
        """List documents."""
        return {"files": [], "nextPageToken": None}

    async def create_document(self, title: str, content: str = None) -> Dict[str, Any]:
        """Create a new document."""
        return {"id": "new_doc_123"}

    async def update_document(self, document_id: str, **updates) -> Dict[str, Any]:
        """Update a document."""
        return {"id": document_id}

    async def delete_document(self, document_id: str) -> bool:
        """Delete a document."""
        return True

    def parse_document_to_header_page(
        self, document_data: Dict[str, Any], page_uri: PageURI
    ) -> DocumentHeader:
        """Parse document data to DocumentHeader."""
        return DocumentHeader(
            uri=page_uri,
            provider_document_id=document_data.get("id", "test_doc"),
            title=document_data.get("title", "Test Document"),
            summary=document_data.get("summary", "Test summary"),
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=datetime.now(timezone.utc),
            modified_time=datetime.now(timezone.utc),
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/test_doc/edit",
        )

    def parse_document_to_chunks(
        self, document_data: Dict[str, Any], header_uri: PageURI
    ) -> list[DocumentChunk]:
        """Parse document data to chunks."""
        chunk_uri = PageURI(
            root=header_uri.root,
            type="google_docs_chunk",
            id=f"{document_data.get('id', 'test_doc')}_0",
        )
        return [
            DocumentChunk(
                uri=chunk_uri,
                header_uri=header_uri,
                provider_document_id=document_data.get("id", "test_doc"),
                provider="google",
                content=document_data.get("content", "Test content"),
                chunk_index=0,
                chunk_title="Test Chunk",
                doc_title=document_data.get("title", "Test Document"),
                word_count=10,
                permalink="https://docs.google.com/document/d/test_doc/edit",
            )
        ]


class MockGoogleProviderClient:
    """Mock Google provider client."""

    def __init__(self):
        self._documents_client = MockGoogleDocumentsClient()

    @property
    def documents_client(self):
        return self._documents_client

    @property
    def email_client(self):
        return Mock()

    @property
    def calendar_client(self):
        return Mock()

    @property
    def people_client(self):
        return Mock()

    async def test_connection(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "google"


class TestGoogleDocumentsService:
    """Test suite for Google Documents service with new architecture."""

    @pytest.fixture
    async def service(self):
        """Create service with test context and mock providers."""
        clear_global_context()

        # Clear SQLAlchemy metadata and table registry between tests
        Base.metadata.clear()
        clear_table_registry()

        # Create temporary file for each test to ensure complete isolation
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            temp_db_path = tmp_file.name

        cache_url = f"sqlite+aiosqlite:///{temp_db_path}"

        # Create real context with isolated temporary database
        context = await ServerContext.create(root="example", cache_url=cache_url)
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create service
        service = DocumentService(providers)

        yield service

        clear_global_context()
        # Clear metadata and registry again after test
        Base.metadata.clear()
        clear_table_registry()

        # Clean up temporary database file
        import os

        try:
            os.unlink(temp_db_path)
        except:
            pass  # Best effort cleanup

    @pytest.mark.asyncio
    async def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.name == "google_docs"
        assert len(service.providers) == 1
        assert "google" in service.providers

    @pytest.mark.asyncio
    async def test_service_registration(self, service):
        """Test that service registers with context."""
        context = service.context
        registered_service = context.get_service("google_docs")
        assert registered_service is service

    @pytest.mark.asyncio
    async def test_create_document_header_page(self, service):
        """Test creating a document header page from URI."""
        # Set up mock document data
        document_data = {
            "id": "test_document",
            "title": "Test Document",
            "content": "Test content",
        }

        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value=document_data
        )

        # Mock parse_document_to_header_page to return DocumentHeader
        from datetime import datetime, timezone

        expected_header = DocumentHeader(
            uri=PageURI(
                root="test://example", type="google_docs_header", id="test_document"
            ),
            provider_document_id="test_document",
            title="Test Document",
            summary="Test document summary",
            created_time=datetime.now(timezone.utc),
            modified_time=datetime.now(timezone.utc),
            owner="test@example.com",
            word_count=50,
            chunk_count=1,
            chunk_uris=[
                PageURI(
                    root="test://example",
                    type="google_docs_chunk",
                    id="test_document_0",
                )
            ],
            permalink="https://docs.google.com/document/d/test_document",
        )
        service.providers["google"].documents_client.parse_document_to_header_page = (
            AsyncMock(return_value=expected_header)
        )

        # Create page URI with new format (google is embedded in type, not ID)
        page_uri = PageURI(
            root="test://example", type="google_docs_header", id="test_document"
        )

        # Test page creation
        header_page = await service.create_document_header_page(page_uri)

        assert isinstance(header_page, DocumentHeader)
        # The header URI should have version=1 after processing
        expected_uri = PageURI(
            root=page_uri.root, type=page_uri.type, id=page_uri.id, version=1
        )
        assert header_page.uri == expected_uri
        assert header_page.title == "Test Document"

        # Verify API was called
        service.providers[
            "google"
        ].documents_client.get_document.assert_called_once_with("test_document")

    @pytest.mark.asyncio
    async def test_create_document_chunk_page(self, service):
        """Test creating a document chunk page from URI."""
        # Set up mock document data
        document_data = {
            "id": "test_document",
            "title": "Test Document",
            "content": "Test chunk content",
        }

        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value=document_data
        )
        service.providers["google"].documents_client.get_document_content = AsyncMock(
            return_value="Test chunk content"
        )

        # Mock parse_document_to_header_page to return DocumentHeader
        from datetime import datetime, timezone

        expected_header = DocumentHeader(
            uri=PageURI(
                root=service.context.root, type="google_docs_header", id="test_document"
            ),
            provider_document_id="test_document",
            title="Test Document",
            summary="Test document summary",
            created_time=datetime.now(timezone.utc),
            modified_time=datetime.now(timezone.utc),
            owner="test@example.com",
            word_count=50,
            chunk_count=1,
            chunk_uris=[
                PageURI(
                    root=service.context.root,
                    type="google_docs_chunk",
                    id="test_document_0",
                )
            ],
            permalink="https://docs.google.com/document/d/test_document",
        )
        service.providers["google"].documents_client.parse_document_to_header_page = (
            AsyncMock(return_value=expected_header)
        )

        # First create the header page to ensure proper setup
        header_uri = PageURI(
            root=service.context.root, type="google_docs_header", id="test_document"
        )
        header_page = await service.create_document_header_page(header_uri)

        # Verify header was created
        assert isinstance(header_page, DocumentHeader)
        assert header_page.title == "Test Document"

        # Now create the chunk page URI
        page_uri = PageURI(
            root=service.context.root, type="google_docs_chunk", id="test_document_0"
        )

        # Test chunk page retrieval from cache (chunks were created when header was created)
        chunk_page = await service.context.get_page(page_uri)

        assert isinstance(chunk_page, DocumentChunk)
        assert chunk_page.uri.type == "google_docs_chunk"
        assert chunk_page.content == "Test chunk content"
        assert chunk_page.chunk_index == 0

    @pytest.mark.asyncio
    async def test_search_documents_by_title(self, service):
        """Test searching for documents by title."""
        # Mock search results
        mock_results = {
            "files": [
                {"id": "doc1", "name": "Document 1"},
                {"id": "doc2", "name": "Document 2"},
            ],
            "nextPageToken": "next_token",
        }

        service.providers["google"].documents_client.search_documents = AsyncMock(
            return_value=mock_results
        )

        # Mock the context.get_pages to return mock document headers
        from datetime import datetime, timezone

        mock_headers = [
            DocumentHeader(
                uri=PageURI(
                    root="test://example", type="google_docs_header", id="doc1"
                ),
                provider_document_id="doc1",
                title="Document 1",
                summary="Document 1 summary",
                created_time=datetime.now(timezone.utc),
                modified_time=datetime.now(timezone.utc),
                owner="test@example.com",
                word_count=100,
                chunk_count=1,
                chunk_uris=[
                    PageURI(
                        root="test://example", type="google_docs_chunk", id="doc1_0"
                    )
                ],
                permalink="https://docs.google.com/document/d/doc1",
            ),
            DocumentHeader(
                uri=PageURI(
                    root="test://example", type="google_docs_header", id="doc2"
                ),
                provider_document_id="doc2",
                title="Document 2",
                summary="Document 2 summary",
                created_time=datetime.now(timezone.utc),
                modified_time=datetime.now(timezone.utc),
                owner="test@example.com",
                word_count=200,
                chunk_count=1,
                chunk_uris=[
                    PageURI(
                        root="test://example", type="google_docs_chunk", id="doc2_0"
                    )
                ],
                permalink="https://docs.google.com/document/d/doc2",
            ),
        ]
        service.context.get_pages = AsyncMock(return_value=mock_headers)

        # Test search by title
        result = await service.search_documents_by_title("test query")

        assert isinstance(result.results, list)
        assert len(result.results) == 2
        assert result.next_cursor == "next_token"

        # Verify the search was called correctly with title prefix
        service.providers[
            "google"
        ].documents_client.search_documents.assert_called_once_with(
            query="title:test query",
            max_results=10,
            page_token=None,
        )

    @pytest.mark.asyncio
    async def test_search_documents_by_topic(self, service):
        """Test searching for documents by topic."""
        # Mock search results
        mock_results = {
            "files": [{"id": "doc1", "name": "Document 1"}],
            "nextPageToken": None,
        }

        service.providers["google"].documents_client.search_documents = AsyncMock(
            return_value=mock_results
        )

        # Test search by topic
        result = await service.search_documents_by_topic("test topic")

        assert isinstance(result.results, list)

        # Verify the search was called correctly with topic query
        service.providers[
            "google"
        ].documents_client.search_documents.assert_called_once_with(
            query="test topic",
            max_results=10,
            page_token=None,
        )

    @pytest.mark.asyncio
    async def test_get_document_content(self, service):
        """Test getting document content."""
        # Create a mock document header
        mock_header = DocumentHeader(
            uri=PageURI(
                root="test://example", type="google_docs_header", id="test_doc"
            ),
            provider_document_id="test_doc",
            title="Test Document",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=datetime.now(timezone.utc),
            modified_time=datetime.now(timezone.utc),
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/test_doc/edit",
        )

        service.providers["google"].documents_client.get_document_content = AsyncMock(
            return_value="Full document content"
        )

        # Test get content
        content = await service.get_document_content(mock_header)

        assert content == "Full document content"

        # Verify API was called
        service.providers[
            "google"
        ].documents_client.get_document_content.assert_called_once_with(
            document_id="test_doc"
        )

    @pytest.mark.asyncio
    async def test_parse_document_uri(self, service):
        """Test parsing document URI."""
        page_uri = PageURI(
            root="test://example", type="google_docs_header", id="doc123"
        )

        provider_name, document_id = service._parse_document_uri(page_uri)

        assert provider_name == "google"
        assert document_id == "doc123"

    @pytest.mark.asyncio
    async def test_parse_chunk_uri(self, service):
        """Test parsing chunk URI."""
        page_uri = PageURI(
            root="test://example", type="google_docs_chunk", id="doc123_0"
        )

        provider_name, document_id, chunk_index = service._parse_chunk_uri(page_uri)

        assert provider_name == "google"
        assert document_id == "doc123"
        assert chunk_index == 0

    @pytest.mark.asyncio
    async def test_invalid_chunk_uri_format(self, service):
        """Test handling of invalid chunk URI formats."""
        page_uri = PageURI(
            root="test://example", type="google_docs_chunk", id="invalidformat"
        )

        with pytest.raises(ValueError, match="Invalid chunk URI format"):
            service._parse_chunk_uri(page_uri)

    @pytest.mark.asyncio
    async def test_empty_providers(self, service):
        """Test handling of service with no providers."""
        # Clear providers and provider_client to simulate error
        service.providers = {}
        service.provider_client = None

        page_uri = PageURI(
            root="test://example", type="google_docs_header", id="doc123"
        )

        with pytest.raises(ValueError, match="No provider available"):
            await service.create_document_header_page(page_uri)

    @pytest.mark.asyncio
    async def test_search_with_no_results(self, service):
        """Test search when no documents are found."""
        # Mock empty results
        service.providers["google"].documents_client.search_documents = AsyncMock(
            return_value={"files": []}
        )

        result = await service.search_documents_by_title("test")

        assert len(result.results) == 0
        assert result.next_cursor is None

    def test_extract_text_from_content_paragraph(self, service):
        """Test text extraction from paragraph content."""
        content = [
            {
                "paragraph": {
                    "elements": [
                        {"textRun": {"content": "Hello "}},
                        {"textRun": {"content": "world!"}},
                    ]
                }
            }
        ]

        result = service._extract_text_from_content(content)
        assert result == "Hello world!"

    def test_extract_text_from_content_table(self, service):
        """Test text extraction from table content."""
        content = [
            {
                "table": {
                    "tableRows": [
                        {
                            "tableCells": [
                                {
                                    "content": [
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {"textRun": {"content": "Cell 1"}}
                                                ]
                                            }
                                        }
                                    ]
                                },
                                {
                                    "content": [
                                        {
                                            "paragraph": {
                                                "elements": [
                                                    {"textRun": {"content": "Cell 2"}}
                                                ]
                                            }
                                        }
                                    ]
                                },
                            ]
                        }
                    ]
                }
            }
        ]

        result = service._extract_text_from_content(content)
        assert result == "Cell 1Cell 2"

    def test_get_chunk_title_short_content(self, service):
        """Test chunk title generation for short content."""
        content = "This is a short sentence."
        result = service._get_chunk_title(content)
        assert result == "This is a short sentence."

    def test_get_chunk_title_long_content(self, service):
        """Test chunk title generation for long content."""
        content = (
            "This is a very long sentence that exceeds fifty characters in length."
        )
        result = service._get_chunk_title(content)
        assert result == "This is a very long sentence that exceeds fifty..."

    @pytest.mark.asyncio
    async def test_validate_document_header_equal_modified_time(self, service):
        """Should return True if API modified time == header modified time."""
        test_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        test_doc_id = "test123"

        header = DocumentHeader(
            uri=PageURI(
                root="test://example", type="google_docs_header", id=test_doc_id
            ),
            provider_document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=test_time,
            modified_time=test_time,
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )

        google_time = (
            test_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value={"modifiedTime": google_time}
        )

        result = await service._validate_document_header(header)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_document_header_api_time_older(self, service):
        """Should return True if API modified time < header modified time."""
        api_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        header_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        test_doc_id = "test123"

        header = DocumentHeader(
            uri=PageURI(
                root="test://example", type="google_docs_header", id=test_doc_id
            ),
            provider_document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=api_time,
            modified_time=header_time,
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )

        google_time = api_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value={"modifiedTime": google_time}
        )

        result = await service._validate_document_header(header)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_document_header_api_time_newer(self, service):
        """Should return False if API modified time > header modified time."""
        api_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        header_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        test_doc_id = "test123"

        header = DocumentHeader(
            uri=PageURI(
                root="test://example", type="google_docs_header", id=test_doc_id
            ),
            provider_document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=header_time,
            modified_time=header_time,
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )

        google_time = api_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value={"modifiedTime": google_time}
        )

        result = await service._validate_document_header(header)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_document_header_api_error(self, service):
        """Should return False if API call fails."""
        test_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        test_doc_id = "test123"

        header = DocumentHeader(
            uri=PageURI(
                root="test://example", type="google_docs_header", id=test_doc_id
            ),
            provider_document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=test_time,
            modified_time=test_time,
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )

        service.providers["google"].documents_client.get_document = AsyncMock(
            side_effect=Exception("API Error")
        )

        result = await service._validate_document_header(header)
        assert result is False

    @pytest.mark.asyncio
    async def test_automatic_chunking_on_header_creation(self, service):
        """Test that chunks are automatically created and cached when header is created."""
        # Set up mock document data with long content that will definitely be chunked
        # Chonkie with 4000 token chunks should split this content
        long_content = (
            "This is a test document with many words that should be chunked. " * 500
        )  # Create content that will be chunked
        document_data = {
            "id": "test_document",
            "title": "Test Document",
            "content": long_content,
        }

        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value=document_data
        )
        service.providers["google"].documents_client.get_document_content = AsyncMock(
            return_value=long_content
        )

        # Create page URI using the context's root
        page_uri = PageURI(
            root=service.context.root, type="google_docs_header", id="test_document"
        )

        # Test header creation through context (should automatically chunk)
        # This goes through the route system which handles versions properly
        header_page = await service.context.get_page(page_uri)

        # Verify header has chunk information
        assert isinstance(header_page, DocumentHeader)
        assert header_page.chunk_count > 1  # Should be chunked due to length
        assert len(header_page.chunk_uris) == header_page.chunk_count

        # Verify all chunk URIs follow the correct pattern
        for i, chunk_uri in enumerate(header_page.chunk_uris):
            assert chunk_uri.type == "google_docs_chunk"
            assert chunk_uri.id == f"test_document_{i}"
            assert chunk_uri.root == service.context.root

        # Verify chunks are actually cached
        for chunk_uri in header_page.chunk_uris:
            cached_chunk = await service.context.get_page(chunk_uri)
            assert cached_chunk is not None
            assert isinstance(cached_chunk, DocumentChunk)
            assert cached_chunk.chunk_index >= 0
            assert len(cached_chunk.content) > 0
            assert cached_chunk.doc_title == "Test Document"
            assert cached_chunk.header_uri == header_page.uri

    def test_chunk_content_method(self, service):
        """Test that content is properly chunked using Chonkie."""
        content = "This is a test document. " * 100  # Create content to chunk
        chunks = service._chunk_content(content)

        assert len(chunks) > 0
        # Verify chunks have text content
        for chunk in chunks:
            chunk_text = getattr(chunk, "text", str(chunk))
            assert len(chunk_text) > 0

    def test_build_document_header(self, service):
        """Test document header building with metadata."""

        from chonkie.types.recursive import RecursiveChunk

        document_data = {
            "id": "test_doc",
            "title": "Test Document",
            "createdTime": "2024-01-01T00:00:00Z",
            "modifiedTime": "2024-01-02T00:00:00Z",
            "owners": [{"emailAddress": "test@example.com"}],
        }

        page_uri = PageURI(
            root="test://example", type="google_docs_header", id="test_doc"
        )

        # Mock chunks with proper RecursiveChunk constructor
        mock_chunks = [
            RecursiveChunk("Chunk 1 content", 0, 16, 4),
            RecursiveChunk("Chunk 2 content", 16, 32, 4),
        ]
        content = "Test document content"

        header = service._build_document_header(
            document_data, content, mock_chunks, page_uri, "test_doc"
        )

        assert header.title == "Test Document"
        assert header.chunk_count == 2
        assert len(header.chunk_uris) == 2
        assert header.owner == "test@example.com"
        assert header.word_count == 3  # "Test document content"
        assert "test_doc" in header.permalink

    @pytest.mark.asyncio
    async def test_document_update_triggers_chunk_updates(self, service):
        """Test that updating parent document triggers chunk updates on next retrieval."""
        document_id = "test_doc_update"

        # Original document content
        original_content = "Original content that will be replaced. " * 20
        original_document_data = {
            "id": document_id,
            "title": "Test Document",
            "content": original_content,
            "modifiedTime": "2024-01-01T00:00:00Z",
        }

        # Updated document content
        updated_content = "Updated content with different text. " * 25
        updated_document_data = {
            "id": document_id,
            "title": "Test Document Updated",
            "content": updated_content,
            "modifiedTime": "2024-01-02T00:00:00Z",  # Newer timestamp
        }

        # Create page URI
        page_uri = PageURI(
            root=service.context.root, type="google_docs_header", id=document_id
        )

        # Step 1: Mock API to return original document data
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value=original_document_data
        )
        service.providers["google"].documents_client.get_document_content = AsyncMock(
            return_value=original_content
        )

        # Step 2: Create initial document header and chunks
        original_header = await service.context.get_page(page_uri)
        assert isinstance(original_header, DocumentHeader)
        assert original_header.title == "Test Document"
        assert len(original_header.chunk_uris) > 0

        # Verify original chunks exist and contain original content
        original_chunks = await service.context.get_pages(original_header.chunk_uris)
        original_first_chunk = original_chunks[0]
        assert isinstance(original_first_chunk, DocumentChunk)
        assert "Original content" in original_first_chunk.content

        # Step 3: Update API mock to return updated document data
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value=updated_document_data
        )
        service.providers["google"].documents_client.get_document_content = AsyncMock(
            return_value=updated_content
        )

        # Step 4: Manually invalidate the header to simulate validation failure
        # In real usage, this would happen when the validator detects newer modified time
        await service.context.page_cache.invalidate(original_header.uri)

        # Step 5: Retrieve document again - should get updated version
        updated_header = await service.context.get_page(page_uri)
        assert isinstance(updated_header, DocumentHeader)
        assert updated_header.title == "Test Document Updated"

        # Step 6: Verify chunks are updated with new content
        updated_chunks = await service.context.get_pages(updated_header.chunk_uris)
        updated_first_chunk = updated_chunks[0]
        assert isinstance(updated_first_chunk, DocumentChunk)
        assert "Updated content" in updated_first_chunk.content
        assert "Original content" not in updated_first_chunk.content

        # Step 7: Verify chunk count may have changed due to different content length
        # Updated content is longer, so we might get more chunks
        assert len(updated_chunks) >= len(original_chunks)

        # Step 8: Verify all chunk URIs reference the new header version
        for chunk in updated_chunks:
            assert chunk.header_uri == updated_header.uri
            assert chunk.doc_title == "Test Document Updated"

    @pytest.mark.asyncio
    async def test_validation_with_stale_document_returns_false(self, service):
        """Test that validation returns False when document is modified externally."""
        document_id = "stale_doc_test"

        # Create document with older timestamp
        old_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        header = DocumentHeader(
            uri=PageURI(
                root=service.context.root, type="google_docs_header", id=document_id
            ),
            provider_document_id=document_id,
            title="Stale Document",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=old_time,
            modified_time=old_time,  # Older timestamp
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )

        # Mock API to return newer timestamp
        newer_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        google_time = (
            newer_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value={"modifiedTime": google_time}
        )

        # Validation should return False because API time is newer
        result = await service._validate_document_header(header)
        assert result is False

    @pytest.mark.asyncio
    async def test_validation_with_current_document_returns_true(self, service):
        """Test that validation returns True when document is current."""
        document_id = "current_doc_test"

        # Create document with current timestamp
        current_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        header = DocumentHeader(
            uri=PageURI(
                root=service.context.root, type="google_docs_header", id=document_id
            ),
            provider_document_id=document_id,
            title="Current Document",
            summary="Test summary",
            content_type=DocumentType.DOCUMENT,
            provider="google",
            created_time=current_time,
            modified_time=current_time,  # Current timestamp
            owner="test@example.com",
            current_user_permission=DocumentPermission.EDITOR,
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )

        # Mock API to return same timestamp
        google_time = (
            current_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        service.providers["google"].documents_client.get_document = AsyncMock(
            return_value={"modifiedTime": google_time}
        )

        # Validation should return True because times match
        result = await service._validate_document_header(header)
        assert result is True
