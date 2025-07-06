"""Tests for GoogleDocsService."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.docs.page import GDocChunk, GDocHeader
from pragweb.google_api.docs.service import GoogleDocsService


class TestGoogleDocsService:
    """Test suite for GoogleDocsService."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}  # Mock services dictionary
        self.mock_page_cache = Mock()
        self.mock_page_cache.get = AsyncMock()
        self.mock_page_cache.store = AsyncMock()
        self.mock_context.page_cache = self.mock_page_cache
        self.mock_context.invalidate_pages_by_prefix = Mock()

        # Mock the register_service method to actually register
        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service

        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()

        # Mock the client methods
        self.mock_api_client.get_document = AsyncMock()
        self.mock_api_client.get_file_metadata = AsyncMock()
        self.mock_api_client.get_latest_revision_id = AsyncMock()
        self.mock_api_client.search_documents = Mock()
        self.mock_api_client.search_documents_by_title = Mock()
        self.mock_api_client.search_documents_by_owner = Mock()
        self.mock_api_client.search_recent_documents = Mock()

        self.service = GoogleDocsService(self.mock_api_client, chunk_size=100)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test GoogleDocsService initialization."""
        assert self.service.api_client is self.mock_api_client
        assert self.service.chunker is not None
        assert self.service.name == "google_docs"

        # Verify service is registered in context
        assert "google_docs" in self.mock_context.services
        assert self.mock_context.services["google_docs"] is self.service

    def test_init_default_chunk_size(self):
        """Test initialization with default chunk size."""
        service = GoogleDocsService(self.mock_api_client)
        # The chunker should be initialized (we can't easily test chunk_size as it's internal)
        assert service.chunker is not None

    @pytest.mark.asyncio
    async def test_handle_header_request_not_cached(self):
        """Test handle_header_request ingests document when called directly (cache is handled by context)."""
        mock_header = Mock(spec=GDocHeader)
        with patch.object(self.service, "_ingest_document", return_value=mock_header):
            expected_uri = PageURI(
                root="test-root", type="gdoc_header", id="doc123", version=1
            )
            result = await self.service.handle_header_request(expected_uri)
        assert result is mock_header

    @pytest.mark.asyncio
    async def test_validate_gdoc_header_equal_modified_time(self):
        """Should return True if API modified time == header modified time."""
        test_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        test_doc_id = "test123"
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id=test_doc_id),
            document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            created_time=test_time,
            modified_time=test_time,
            owner="test@example.com",
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )
        google_time = (
            test_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        self.mock_api_client.get_file_metadata.return_value = {
            "modifiedTime": google_time
        }
        result = await self.service._validate_gdoc_header(header)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_gdoc_header_api_time_older(self):
        """Should return True if API modified time < header modified time."""
        api_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        header_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        test_doc_id = "test123"
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id=test_doc_id),
            document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            created_time=header_time,
            modified_time=header_time,
            owner="test@example.com",
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )
        google_time = api_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.mock_api_client.get_file_metadata.return_value = {
            "modifiedTime": google_time
        }
        result = await self.service._validate_gdoc_header(header)
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_gdoc_header_api_time_newer(self):
        """Should return False if API modified time > header modified time."""
        header_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        api_time = datetime(2024, 1, 2, tzinfo=timezone.utc)
        test_doc_id = "test123"
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id=test_doc_id),
            document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            created_time=header_time,
            modified_time=header_time,
            owner="test@example.com",
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )
        google_time = api_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        self.mock_api_client.get_file_metadata.return_value = {
            "modifiedTime": google_time
        }
        result = await self.service._validate_gdoc_header(header)
        assert result is False

    @pytest.mark.asyncio
    async def test_validate_gdoc_header_api_error(self):
        """Should return False if API call fails."""
        test_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        test_doc_id = "test123"
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id=test_doc_id),
            document_id=test_doc_id,
            title="Test Doc",
            summary="Test summary",
            created_time=test_time,
            modified_time=test_time,
            owner="test@example.com",
            word_count=100,
            chunk_count=1,
            chunk_uris=[],
            permalink="https://docs.google.com/test",
        )
        self.mock_api_client.get_file_metadata.side_effect = Exception("API Error")
        result = await self.service._validate_gdoc_header(header)
        assert result is False

    @pytest.mark.asyncio
    async def test_ingest_document_success(self):
        """Test successful document ingestion."""
        test_doc_id = "test123"
        test_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
        google_time = (
            test_time.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        # Mock API responses
        self.mock_api_client.get_document.return_value = {
            "title": "Test Document",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [{"textRun": {"content": "Hello world!"}}]
                        }
                    }
                ]
            },
        }
        self.mock_api_client.get_file_metadata.return_value = {
            "name": "Test Document",
            "createdTime": google_time,
            "modifiedTime": google_time,
            "owners": [{"emailAddress": "test@example.com"}],
        }
        # Mock context methods
        self.mock_context.create_page_uri = AsyncMock()
        test_header_uri = PageURI(root="test-root", type="gdoc_header", id=test_doc_id)
        test_chunk_uri = PageURI(
            root="test-root", type="gdoc_chunk", id=f"{test_doc_id}(0)"
        )
        self.mock_context.create_page_uri.side_effect = [test_chunk_uri]
        # Perform ingestion
        result = await self.service._ingest_document(test_header_uri)
        # Verify API calls
        self.mock_api_client.get_document.assert_awaited_once_with(test_doc_id)
        self.mock_api_client.get_file_metadata.assert_awaited_once_with(test_doc_id)
        # Verify result
        assert isinstance(result, GDocHeader)
        assert result.document_id == test_doc_id
        assert result.title == "Test Document"
        assert result.modified_time == test_time
        assert result.created_time == test_time
        assert result.owner == "test@example.com"
        assert result.chunk_count == 1
        assert isinstance(result.chunk_uris, list)
        assert len(result.chunk_uris) == 1
        assert all(isinstance(uri, PageURI) for uri in result.chunk_uris)

    def test_extract_text_from_content_paragraph(self):
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

        result = self.service._extract_text_from_content(content)
        assert result == "Hello world!"

    def test_extract_text_from_content_table(self):
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

        result = self.service._extract_text_from_content(content)
        assert result == "Cell 1Cell 2"

    def test_get_chunk_title_short_content(self):
        """Test chunk title generation for short content."""
        content = "This is a short sentence."
        result = self.service._get_chunk_title(content)
        assert result == "This is a short sentence."

    def test_get_chunk_title_long_content(self):
        """Test chunk title generation for long content."""
        content = (
            "This is a very long sentence that exceeds fifty characters in length."
        )
        result = self.service._get_chunk_title(content)
        assert result == "This is a very long sentence that exceeds fifty..."

    @pytest.mark.asyncio
    async def test_search_documents_generic(self):
        """Test searching documents with generic method."""
        mock_files = [
            {"id": "doc1", "name": "Document 1"},
            {"id": "doc2", "name": "Document 2"},
        ]
        self.mock_api_client.search_documents = AsyncMock(
            return_value=(mock_files, "next_token")
        )

        uris, next_token = await self.service.search_documents({"query": "test query"})

        # Verify API call
        self.mock_api_client.search_documents.assert_awaited_once_with(
            search_params={"query": "test query"}, page_token=None, page_size=20
        )

        # Verify URIs created
        assert len(uris) == 2
        assert uris[0] == PageURI(root="test-root", type="gdoc_header", id="doc1")
        assert uris[1] == PageURI(root="test-root", type="gdoc_header", id="doc2")
        assert next_token == "next_token"

    @pytest.mark.asyncio
    async def test_search_documents_by_title(self):
        """Test searching documents by title."""
        mock_files = [{"id": "doc1", "name": "Test Document"}]
        self.mock_api_client.search_documents = AsyncMock(
            return_value=(mock_files, None)
        )

        uris, next_token = await self.service.search_documents({"title_query": "Test"})

        self.mock_api_client.search_documents.assert_awaited_once_with(
            search_params={"title_query": "Test"}, page_token=None, page_size=20
        )
        assert len(uris) == 1
        assert next_token is None

    @pytest.mark.asyncio
    async def test_search_documents_by_owner(self):
        """Test searching documents by owner with email."""
        mock_files = [{"id": "doc1", "name": "Owned Document"}]
        self.mock_api_client.search_documents = AsyncMock(
            return_value=(mock_files, None)
        )

        # Service layer should not do person identifier resolution anymore
        uris, next_token = await self.service.search_documents(
            {"owner_email": "owner@example.com"}
        )

        self.mock_api_client.search_documents.assert_awaited_once_with(
            search_params={"owner_email": "owner@example.com"},
            page_token=None,
            page_size=20,
        )
        assert len(uris) == 1

    @pytest.mark.asyncio
    async def test_search_documents_by_owner_with_name(self):
        """Test searching documents by owner with person name."""
        mock_files = [{"id": "doc1", "name": "Owned Document"}]
        self.mock_api_client.search_documents = AsyncMock(
            return_value=(mock_files, None)
        )

        # Service layer should not do person identifier resolution anymore
        uris, next_token = await self.service.search_documents(
            {"owner_email": "John Doe"}
        )

        self.mock_api_client.search_documents.assert_awaited_once_with(
            search_params={"owner_email": "John Doe"},
            page_token=None,
            page_size=20,
        )
        assert len(uris) == 1

    @pytest.mark.asyncio
    async def test_search_recent_documents(self):
        """Test searching recent documents."""
        mock_files = [{"id": "doc1", "name": "Recent Document"}]
        self.mock_api_client.search_documents = AsyncMock(
            return_value=(mock_files, None)
        )

        uris, next_token = await self.service.search_documents({"days": 14})

        self.mock_api_client.search_documents.assert_awaited_once_with(
            search_params={"days": 14}, page_token=None, page_size=20
        )
        assert len(uris) == 1

    @pytest.mark.asyncio
    async def test_search_chunks_in_document(self):
        """Test searching chunks within a document."""
        # Mock existing chunks in document
        mock_chunk1 = Mock(spec=GDocChunk)
        mock_chunk1.document_id = "doc123"
        mock_chunk1.content = "This contains the search term"

        mock_chunk2 = Mock(spec=GDocChunk)
        mock_chunk2.document_id = "doc123"
        mock_chunk2.content = "This does not contain the query"

        mock_chunk3 = Mock(spec=GDocChunk)
        mock_chunk3.document_id = "doc123"
        mock_chunk3.content = "Another chunk with search and term words"

        # Mock the new fluent interface: find().where().all()
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(return_value=[mock_chunk1, mock_chunk2, mock_chunk3])
        self.mock_page_cache.find.return_value = mock_query

        # Mock handle_header_request to ensure document is ingested
        with patch.object(self.service, "handle_header_request", new=AsyncMock()):
            # Use proper URI format: root/type:id@version
            doc_header_uri = "test-root/gdoc_header:doc123@1"
            result = await self.service.search_chunks_in_document(
                doc_header_uri, "search term"
            )

        # Should return chunks that match the search terms
        # mock_chunk1 and mock_chunk3 should match better than mock_chunk2
        assert len(result) >= 2  # At least the matching chunks
        assert mock_chunk1 in result
        assert mock_chunk3 in result

    @pytest.mark.asyncio
    async def test_search_chunks_in_document_no_chunks(self):
        """Test searching chunks when document has no chunks."""
        # Mock the new fluent interface: find().where().all()
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(return_value=[])
        self.mock_page_cache.find.return_value = mock_query

        with patch.object(self.service, "handle_header_request", new=AsyncMock()):
            doc_header_uri = "test-root/gdoc_header:doc123@1"
            result = await self.service.search_chunks_in_document(
                doc_header_uri, "query"
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_search_chunks_in_document_invalid_uri(self):
        """Test searching chunks with invalid URI."""
        with pytest.raises(ValueError, match="Invalid document header URI"):
            await self.service.search_chunks_in_document("invalid-uri", "query")

    @pytest.mark.asyncio
    async def test_search_chunks_in_document_wrong_uri_type(self):
        """Test searching chunks with wrong URI type."""
        chunk_uri = "test-root/gdoc_chunk:doc123(0)@1"
        with pytest.raises(
            ValueError, match="Expected gdoc_header URI, got gdoc_chunk"
        ):
            await self.service.search_chunks_in_document(chunk_uri, "query")

    def test_toolkit_property(self):
        """Test toolkit property returns self (merged functionality)."""
        toolkit = self.service.toolkit
        assert toolkit is self.service
        # Verify it has the toolkit methods
        assert hasattr(toolkit, "search_documents_by_title")
        assert hasattr(toolkit, "search_documents_by_topic")
        assert hasattr(toolkit, "search_documents_by_owner")
        assert hasattr(toolkit, "search_recently_modified_documents")
        assert hasattr(toolkit, "search_all_documents")
        assert hasattr(toolkit, "find_chunks_in_document")

    def test_name_property(self):
        """Test name property returns correct service name."""
        assert self.service.name == "google_docs"


class TestGoogleDocsToolkit:
    """Test suite for GoogleDocsService toolkit methods (now integrated into GoogleDocsService)."""

    def setup_method(self):
        """Set up test environment."""
        # Clear any existing global context first
        clear_global_context()

        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_context.get_page = Mock()
        self.mock_context.get_pages = AsyncMock()

        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service
        set_global_context(self.mock_context)
        # Re-instantiate service after setting context
        self.mock_api_client = Mock()
        self.mock_api_client.search_documents = Mock()
        self.service = GoogleDocsService(self.mock_api_client)
        self.toolkit = self.service

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    @pytest.mark.asyncio
    async def test_search_documents_by_title(self):
        """Test search_documents_by_title tool."""
        # Create real GDocHeader instances for testing
        header1 = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document 1",
            summary="Test summary 1",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="test@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )
        header2 = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc2", version=1),
            document_id="doc2",
            title="Test Document 2",
            summary="Test summary 2",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="test@example.com",
            word_count=200,
            chunk_count=10,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc2/edit",
            revision_id="rev2",
        )

        # Mock search results
        mock_headers = [header1, header2]
        self.mock_context.get_page.side_effect = mock_headers
        self.mock_context.get_pages.return_value = mock_headers

        # Mock service search method
        mock_uris = [header1.uri, header2.uri]
        with patch.object(
            self.service,
            "search_documents",
            new=AsyncMock(return_value=(mock_uris, "next_token")),
        ) as mock_search:
            result = await self.toolkit.search_documents_by_title("test title")

            # Verify service method called
            mock_search.assert_awaited_once_with(
                {"title_query": "test title"}, None, 10
            )

        # Verify result structure
        assert result.results == mock_headers
        assert result.next_cursor == "next_token"

    @pytest.mark.asyncio
    async def test_search_documents_by_topic(self):
        """Test search_documents_by_topic tool."""
        # Create real GDocHeader instance for testing
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document",
            summary="Test summary",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="test@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )

        mock_headers = [header]
        self.mock_context.get_page.return_value = mock_headers[0]
        self.mock_context.get_pages.return_value = mock_headers

        mock_uris = [header.uri]
        with patch.object(
            self.service,
            "search_documents",
            new=AsyncMock(return_value=(mock_uris, None)),
        ) as mock_search:
            result = await self.toolkit.search_documents_by_topic("test topic")

            mock_search.assert_awaited_once_with({"query": "test topic"}, None, 10)

        assert result.results == mock_headers
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_search_documents_by_owner(self):
        """Test search_documents_by_owner tool."""
        # Create real GDocHeader instance for testing
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document",
            summary="Test summary",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="owner@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )

        mock_headers = [header]
        self.mock_context.get_page.return_value = mock_headers[0]
        self.mock_context.get_pages.return_value = mock_headers

        mock_uris = [header.uri]
        # Mock resolve_person_identifier
        with (
            patch(
                "pragweb.google_api.docs.service.resolve_person_identifier"
            ) as mock_resolve,
            patch.object(
                self.service,
                "search_documents",
                new=AsyncMock(return_value=(mock_uris, None)),
            ) as mock_search,
        ):

            mock_resolve.return_value = "owner@example.com"
            result = await self.toolkit.search_documents_by_owner("owner@example.com")

            mock_resolve.assert_called_once_with("owner@example.com")
            mock_search.assert_awaited_once_with(
                {"owner_email": "owner@example.com"}, None, 10
            )

        assert result.results == mock_headers

    @pytest.mark.asyncio
    async def test_search_documents_by_owner_with_name(self):
        """Test search_documents_by_owner tool with person name."""
        # Create real GDocHeader instance for testing
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document",
            summary="Test summary",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="john.doe@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )

        mock_headers = [header]
        self.mock_context.get_page.return_value = mock_headers[0]
        self.mock_context.get_pages.return_value = mock_headers

        mock_uris = [header.uri]
        # Mock resolve_person_identifier to resolve name to email query
        with (
            patch(
                "pragweb.google_api.docs.service.resolve_person_identifier"
            ) as mock_resolve,
            patch.object(
                self.service,
                "search_documents",
                new=AsyncMock(return_value=(mock_uris, None)),
            ) as mock_search,
        ):

            mock_resolve.return_value = "John Doe OR john.doe@example.com"
            result = await self.toolkit.search_documents_by_owner("John Doe")

            mock_resolve.assert_called_once_with("John Doe")
            mock_search.assert_awaited_once_with(
                {"owner_email": "John Doe OR john.doe@example.com"}, None, 10
            )

        assert result.results == mock_headers

    @pytest.mark.asyncio
    async def test_search_recently_modified_documents(self):
        """Test search_recently_modified_documents tool."""
        # Create real GDocHeader instance for testing
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document",
            summary="Test summary",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="test@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )

        mock_headers = [header]
        self.mock_context.get_page.return_value = mock_headers[0]
        self.mock_context.get_pages.return_value = mock_headers

        mock_uris = [header.uri]
        with patch.object(
            self.service,
            "search_documents",
            new=AsyncMock(return_value=(mock_uris, None)),
        ) as mock_search:
            result = await self.toolkit.search_recently_modified_documents()

            mock_search.assert_awaited_once_with({"days": 7}, None, 10)

        assert result.results == mock_headers

    @pytest.mark.asyncio
    async def test_search_all_documents(self):
        """Test search_all_documents tool."""
        # Create real GDocHeader instance for testing
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document",
            summary="Test summary",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="test@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )

        mock_headers = [header]
        self.mock_context.get_page.return_value = mock_headers[0]
        self.mock_context.get_pages.return_value = mock_headers

        mock_uris = [header.uri]
        with patch.object(
            self.service,
            "search_documents",
            new=AsyncMock(return_value=(mock_uris, None)),
        ) as mock_search:
            result = await self.toolkit.search_all_documents()

            mock_search.assert_awaited_once_with({"query": ""}, None, 10)

        assert result.results == mock_headers

    @pytest.mark.asyncio
    async def test_find_chunks_in_document(self):
        """Test find_chunks_in_document tool."""
        mock_chunks = [Mock(spec=GDocChunk), Mock(spec=GDocChunk)]
        from unittest.mock import AsyncMock

        with patch.object(
            self.service,
            "search_chunks_in_document",
            new=AsyncMock(return_value=mock_chunks),
        ) as mock_search:
            result = await self.toolkit.find_chunks_in_document("uri", "query")
            mock_search.assert_called_once_with("uri", "query")
        assert result.results == mock_chunks
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_pagination_no_more_pages(self):
        self.mock_context.get_pages = AsyncMock(return_value=[])
        with patch.object(
            self.service, "search_documents", new=AsyncMock(return_value=([], None))
        ):
            result = await self.toolkit.search_documents_by_title("Test")
        assert result.results == []
        assert result.next_cursor is None

    @pytest.mark.asyncio
    async def test_pagination_with_cursor(self):
        # Create real GDocHeader instance for testing
        header = GDocHeader(
            uri=PageURI(root="test-root", type="gdoc_header", id="doc1", version=1),
            document_id="doc1",
            title="Test Document",
            summary="Test summary",
            created_time=datetime.now(),
            modified_time=datetime.now(),
            owner="test@example.com",
            word_count=100,
            chunk_count=5,
            chunk_uris=[],
            permalink="https://docs.google.com/document/d/doc1/edit",
            revision_id="rev1",
        )

        # Mock service returns results with next cursor
        self.mock_context.get_page.return_value = header
        self.mock_context.get_pages.return_value = [header]

        with patch.object(
            self.service,
            "search_documents",
            new=AsyncMock(return_value=([header.uri], "next_cursor_token")),
        ) as mock_search:
            result = await self.toolkit.search_documents_by_title("Test")
            mock_search.assert_awaited_once_with({"title_query": "Test"}, None, 10)
        assert len(result.results) == 1
        assert result.next_cursor == "next_cursor_token"


class TestGoogleDocsCacheInvalidation:
    """Test suite for Google Docs cache invalidation functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_page_cache = Mock()
        self.mock_context.page_cache = self.mock_page_cache
        self.mock_context.invalidate_pages_by_prefix = Mock()

        # Mock the register_service method
        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service

        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient with revision support
        self.mock_api_client = Mock()
        self.mock_api_client.get_document = Mock()
        self.mock_api_client.get_file_metadata = Mock()
        self.mock_api_client.get_file_revisions = Mock()
        self.mock_api_client.get_latest_revision_id = Mock()
        self.mock_api_client.check_file_revision = Mock()

        self.service = GoogleDocsService(self.mock_api_client, chunk_size=100)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_api_client_revision_methods(self):
        """Test that API client has revision tracking methods."""
        # Test get_file_revisions
        mock_revisions = [
            {"id": "1", "modifiedTime": "2023-01-01T00:00:00.000Z"},
            {"id": "2", "modifiedTime": "2023-01-02T00:00:00.000Z"},
        ]
        self.mock_api_client.get_file_revisions.return_value = mock_revisions

        revisions = self.mock_api_client.get_file_revisions("doc123")
        assert revisions == mock_revisions

        # Test get_latest_revision_id
        self.mock_api_client.get_latest_revision_id.return_value = "2"
        latest_id = self.mock_api_client.get_latest_revision_id("doc123")
        assert latest_id == "2"

        # Test check_file_revision
        self.mock_api_client.check_file_revision.return_value = True
        is_current = self.mock_api_client.check_file_revision("doc123", "2")
        assert is_current is True
