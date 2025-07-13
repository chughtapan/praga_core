"""Tests for Google Documents integration with the new architecture."""

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
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

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create service
        service = DocumentService(providers)

        yield service

        clear_global_context()

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

        # Create page URI with new format (google is embedded in type, not ID)
        page_uri = PageURI(
            root="test://example", type="google_docs_header", id="test_document"
        )

        # Test page creation
        header_page = await service.create_document_header_page(page_uri)

        assert isinstance(header_page, DocumentHeader)
        assert header_page.uri == page_uri
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

        # Create page URI with new format (chunk URI includes chunk index)
        page_uri = PageURI(
            root="test://example", type="google_docs_chunk", id="test_document_0"
        )

        # Test page creation
        chunk_page = await service.create_document_chunk_page(page_uri)

        assert isinstance(chunk_page, DocumentChunk)
        assert chunk_page.uri.type == "google_docs_chunk"
        assert chunk_page.content == "Test chunk content"
        assert chunk_page.chunk_index == 0

    @pytest.mark.asyncio
    async def test_search_documents(self, service):
        """Test searching for documents."""
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

        # Test search
        result = await service.search_documents("test query", "google")

        assert isinstance(result.results, list)
        assert result.next_cursor == "next_token"

        # Verify the search was called correctly
        service.providers[
            "google"
        ].documents_client.search_documents.assert_called_once_with(
            query="test query",
            max_results=10,
            page_token=None,
        )

    @pytest.mark.asyncio
    async def test_get_all_documents(self, service):
        """Test getting all documents."""
        # Mock list results
        mock_results = {
            "files": [{"id": "doc1", "name": "Document 1"}],
            "nextPageToken": None,
        }

        service.providers["google"].documents_client.list_documents = AsyncMock(
            return_value=mock_results
        )

        # Test get all
        result = await service.get_all_documents("google", max_results=5)

        assert isinstance(result.results, list)

        # Verify the list was called correctly
        service.providers[
            "google"
        ].documents_client.list_documents.assert_called_once_with(
            max_results=5,
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
        # Clear providers to simulate error
        service.providers = {}

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

        result = await service.search_documents("test", "google")

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
