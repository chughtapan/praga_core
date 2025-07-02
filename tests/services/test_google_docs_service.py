"""Tests for GoogleDocsService."""

from unittest.mock import Mock, patch

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
        self.mock_context.page_cache = self.mock_page_cache

        # Mock the register_service method to actually register
        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service

        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()

        # Mock the client methods
        self.mock_api_client.get_document = Mock()
        self.mock_api_client.get_file_metadata = Mock()
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

    def test_handle_header_request_cached(self):
        """Test handle_header_request returns cached header."""
        mock_header = Mock(spec=GDocHeader)
        self.mock_page_cache.get_page.return_value = mock_header

        result = self.service.handle_header_request("doc123")

        # Verify cache lookup
        expected_uri = PageURI(root="test-root", type="gdoc_header", id="doc123")
        self.mock_page_cache.get_page.assert_called_once_with(GDocHeader, expected_uri)
        assert result is mock_header

    def test_handle_header_request_not_cached(self):
        """Test handle_header_request ingests document when not cached."""
        self.mock_page_cache.get_page.return_value = None
        mock_header = Mock(spec=GDocHeader)

        with patch.object(self.service, "_ingest_document", return_value=mock_header):
            result = self.service.handle_header_request("doc123")

        assert result is mock_header

    def test_handle_chunk_request_cached(self):
        """Test handle_chunk_request returns cached chunk."""
        mock_chunk = Mock(spec=GDocChunk)
        self.mock_page_cache.get_page.return_value = mock_chunk

        result = self.service.handle_chunk_request("chunk123")

        expected_uri = PageURI(root="test-root", type="gdoc_chunk", id="chunk123")
        self.mock_page_cache.get_page.assert_called_once_with(GDocChunk, expected_uri)
        assert result is mock_chunk

    def test_handle_chunk_request_not_found(self):
        """Test handle_chunk_request raises error when chunk not found."""
        # Use valid chunk ID format: document_id(chunk_index)
        self.mock_page_cache.get_page.return_value = None

        # Mock that document ingestion doesn't create the chunk
        with patch.object(self.service, "_ingest_document"):
            with pytest.raises(
                ValueError, match="Chunk doc123\\(0\\) not found after ingestion"
            ):
                self.service.handle_chunk_request("doc123(0)")

    def test_ingest_document_success(self):
        """Test successful document ingestion."""
        # Mock API responses
        mock_doc_data = {
            "title": "Test Document",
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [{"textRun": {"content": "Hello world! "}}]
                        }
                    }
                ]
            },
        }
        mock_file_metadata = {
            "name": "Test Document",
            "createdTime": "2023-01-01T00:00:00.000Z",
            "modifiedTime": "2023-01-02T00:00:00.000Z",
            "owners": [
                {"displayName": "Test User", "emailAddress": "test@example.com"}
            ],
        }

        self.mock_api_client.get_document.return_value = mock_doc_data
        self.mock_api_client.get_file_metadata.return_value = mock_file_metadata

        # Create a real PageURI for testing
        test_doc_id = "doc123"
        header_uri = PageURI(root="test-root", type="gdoc_header", id=test_doc_id)
        chunk_uri = PageURI(root="test-root", type="gdoc_chunk", id=f"{test_doc_id}(0)")

        # Mock the service's chunker directly
        mock_chunk = Mock()
        mock_chunk.text = "Hello world!"
        mock_chunk.token_count = 3
        self.service.chunker.chunk = Mock(return_value=[mock_chunk])

        # Mock context's create_page_uri to return our real URIs
        self.mock_context.create_page_uri = Mock()
        self.mock_context.create_page_uri.side_effect = [header_uri, chunk_uri]

        # Mock page cache store_page method
        self.mock_page_cache.store_page = Mock()

        result = self.service._ingest_document(test_doc_id)

        # Verify API calls made
        self.mock_api_client.get_document.assert_called_once_with(test_doc_id)
        self.mock_api_client.get_file_metadata.assert_called_once_with(test_doc_id)

        # Verify chunk creation (text extraction strips trailing space)
        self.service.chunker.chunk.assert_called_once_with("Hello world!")

        # Verify pages were stored (header + 1 chunk)
        assert self.mock_page_cache.store_page.call_count == 2

        # Verify return type
        assert isinstance(result, GDocHeader)
        assert result.document_id == test_doc_id
        assert result.title == "Test Document"

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

    def test_search_documents_generic(self):
        """Test searching documents with generic method."""
        mock_files = [
            {"id": "doc1", "name": "Document 1"},
            {"id": "doc2", "name": "Document 2"},
        ]
        self.mock_api_client.search_documents.return_value = (mock_files, "next_token")

        uris, next_token = self.service.search_documents({"query": "test query"})

        # Verify API call
        self.mock_api_client.search_documents.assert_called_once_with(
            search_params={"query": "test query"}, page_token=None, page_size=20
        )

        # Verify URIs created
        assert len(uris) == 2
        assert uris[0] == PageURI(root="test-root", type="gdoc_header", id="doc1")
        assert uris[1] == PageURI(root="test-root", type="gdoc_header", id="doc2")
        assert next_token == "next_token"

    def test_search_documents_by_title(self):
        """Test searching documents by title."""
        mock_files = [{"id": "doc1", "name": "Test Document"}]
        self.mock_api_client.search_documents.return_value = (mock_files, None)

        uris, next_token = self.service.search_documents({"title_query": "Test"})

        self.mock_api_client.search_documents.assert_called_once_with(
            search_params={"title_query": "Test"}, page_token=None, page_size=20
        )
        assert len(uris) == 1
        assert next_token is None

    def test_search_documents_by_owner(self):
        """Test searching documents by owner with email."""
        mock_files = [{"id": "doc1", "name": "Owned Document"}]
        self.mock_api_client.search_documents.return_value = (mock_files, None)

        # Service layer should not do person identifier resolution anymore
        uris, next_token = self.service.search_documents(
            {"owner_email": "owner@example.com"}
        )

        self.mock_api_client.search_documents.assert_called_once_with(
            search_params={"owner_email": "owner@example.com"},
            page_token=None,
            page_size=20,
        )
        assert len(uris) == 1

    def test_search_documents_by_owner_with_name(self):
        """Test searching documents by owner with person name."""
        mock_files = [{"id": "doc1", "name": "Owned Document"}]
        self.mock_api_client.search_documents.return_value = (mock_files, None)

        # Service layer should not do person identifier resolution anymore
        uris, next_token = self.service.search_documents({"owner_email": "John Doe"})

        self.mock_api_client.search_documents.assert_called_once_with(
            search_params={"owner_email": "John Doe"},
            page_token=None,
            page_size=20,
        )
        assert len(uris) == 1

    def test_search_recent_documents(self):
        """Test searching recent documents."""
        mock_files = [{"id": "doc1", "name": "Recent Document"}]
        self.mock_api_client.search_documents.return_value = (mock_files, None)

        uris, next_token = self.service.search_documents({"days": 14})

        self.mock_api_client.search_documents.assert_called_once_with(
            search_params={"days": 14}, page_token=None, page_size=20
        )
        assert len(uris) == 1

    def test_search_chunks_in_document(self):
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

        self.mock_page_cache.find_pages_by_attribute.return_value = [
            mock_chunk1,
            mock_chunk2,
            mock_chunk3,
        ]

        # Mock handle_header_request to ensure document is ingested
        with patch.object(self.service, "handle_header_request"):
            # Use proper URI format: root/type:id@version
            doc_header_uri = "test-root/gdoc_header:doc123@1"
            result = self.service.search_chunks_in_document(
                doc_header_uri, "search term"
            )

        # Should return chunks that match the search terms
        # mock_chunk1 and mock_chunk3 should match better than mock_chunk2
        assert len(result) >= 2  # At least the matching chunks
        assert mock_chunk1 in result
        assert mock_chunk3 in result

    def test_search_chunks_in_document_no_chunks(self):
        """Test searching chunks when document has no chunks."""
        self.mock_page_cache.find_pages_by_attribute.return_value = []

        with patch.object(self.service, "handle_header_request"):
            doc_header_uri = "test-root/gdoc_header:doc123@1"
            result = self.service.search_chunks_in_document(doc_header_uri, "query")

        assert result == []

    def test_search_chunks_in_document_invalid_uri(self):
        """Test searching chunks with invalid URI."""
        with pytest.raises(ValueError, match="Invalid document header URI"):
            self.service.search_chunks_in_document("invalid-uri", "query")

    def test_search_chunks_in_document_wrong_uri_type(self):
        """Test searching chunks with wrong URI type."""
        chunk_uri = "test-root/gdoc_chunk:doc123(0)@1"
        with pytest.raises(
            ValueError, match="Expected gdoc_header URI, got gdoc_chunk"
        ):
            self.service.search_chunks_in_document(chunk_uri, "query")

    def test_toolkit_property(self):
        """Test toolkit property returns GoogleDocsToolkit."""
        toolkit = self.service.toolkit
        assert toolkit.google_docs_service is self.service
        assert toolkit.name == "GoogleDocsToolkit"

    def test_name_property(self):
        """Test name property returns correct service name."""
        assert self.service.name == "google_docs"


class TestGoogleDocsToolkit:
    """Test suite for GoogleDocsToolkit."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.get_page = Mock()

        set_global_context(self.mock_context)

        # Create mock service
        self.mock_service = Mock(spec=GoogleDocsService)
        self.mock_service.context = self.mock_context

        # Import here to avoid circular import issues
        from pragweb.google_api.docs.service import GoogleDocsToolkit

        self.toolkit = GoogleDocsToolkit(self.mock_service)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test GoogleDocsToolkit initialization."""
        assert self.toolkit.google_docs_service is self.mock_service
        assert self.toolkit.name == "GoogleDocsToolkit"

    def test_search_documents_by_title(self):
        """Test search_documents_by_title tool."""
        # Mock search results
        mock_headers = [Mock(spec=GDocHeader), Mock(spec=GDocHeader)]
        self.mock_context.get_page.side_effect = mock_headers

        # Mock service search method
        mock_uris = [Mock(spec=PageURI), Mock(spec=PageURI)]
        self.mock_service.search_documents.return_value = (
            mock_uris,
            "next_token",
        )

        result = self.toolkit.search_documents_by_title("test title")

        # Verify service method called
        self.mock_service.search_documents.assert_called_once_with(
            {"title_query": "test title"}, None, 10
        )

        # Verify result structure
        assert result.results == mock_headers
        assert result.next_cursor == "next_token"

    def test_search_documents_by_topic(self):
        """Test search_documents_by_topic tool."""
        mock_headers = [Mock(spec=GDocHeader)]
        self.mock_context.get_page.return_value = mock_headers[0]

        mock_uris = [Mock(spec=PageURI)]
        self.mock_service.search_documents.return_value = (mock_uris, None)

        result = self.toolkit.search_documents_by_topic("test topic")

        self.mock_service.search_documents.assert_called_once_with(
            {"query": "test topic"}, None, 10
        )
        assert result.results == mock_headers
        assert result.next_cursor is None

    def test_search_documents_by_owner(self):
        """Test search_documents_by_owner tool."""
        mock_headers = [Mock(spec=GDocHeader)]
        self.mock_context.get_page.return_value = mock_headers[0]

        mock_uris = [Mock(spec=PageURI)]
        self.mock_service.search_documents.return_value = (
            mock_uris,
            None,
        )

        # Mock resolve_person_identifier
        with patch(
            "pragweb.google_api.docs.service.resolve_person_identifier"
        ) as mock_resolve:
            mock_resolve.return_value = "owner@example.com"

            result = self.toolkit.search_documents_by_owner("owner@example.com")

        mock_resolve.assert_called_once_with("owner@example.com")
        self.mock_service.search_documents.assert_called_once_with(
            {"owner_email": "owner@example.com"}, None, 10
        )
        assert result.results == mock_headers

    def test_search_documents_by_owner_with_name(self):
        """Test search_documents_by_owner tool with person name."""
        mock_headers = [Mock(spec=GDocHeader)]
        self.mock_context.get_page.return_value = mock_headers[0]

        mock_uris = [Mock(spec=PageURI)]
        self.mock_service.search_documents.return_value = (
            mock_uris,
            None,
        )

        # Mock resolve_person_identifier to resolve name to email query
        with patch(
            "pragweb.google_api.docs.service.resolve_person_identifier"
        ) as mock_resolve:
            mock_resolve.return_value = "John Doe OR john.doe@example.com"

            result = self.toolkit.search_documents_by_owner("John Doe")

        mock_resolve.assert_called_once_with("John Doe")
        self.mock_service.search_documents.assert_called_once_with(
            {"owner_email": "John Doe OR john.doe@example.com"}, None, 10
        )
        assert result.results == mock_headers

    def test_search_recently_modified_documents(self):
        """Test search_recently_modified_documents tool."""
        mock_headers = [Mock(spec=GDocHeader)]
        self.mock_context.get_page.return_value = mock_headers[0]

        mock_uris = [Mock(spec=PageURI)]
        self.mock_service.search_documents.return_value = (
            mock_uris,
            None,
        )

        result = self.toolkit.search_recently_modified_documents(days=14)

        self.mock_service.search_documents.assert_called_once_with(
            {"days": 14}, None, 10
        )
        assert result.results == mock_headers

    def test_search_all_documents(self):
        """Test search_all_documents tool."""
        mock_headers = [Mock(spec=GDocHeader)]
        self.mock_context.get_page.return_value = mock_headers[0]

        mock_uris = [Mock(spec=PageURI)]
        self.mock_service.search_documents.return_value = (mock_uris, None)

        result = self.toolkit.search_all_documents()

        self.mock_service.search_documents.assert_called_once_with(
            {"query": ""}, None, 10
        )
        assert result.results == mock_headers

    def test_search_chunks_in_document(self):
        """Test search_chunks_in_document tool."""
        mock_chunks = [Mock(spec=GDocChunk), Mock(spec=GDocChunk)]
        self.mock_service.search_chunks_in_document.return_value = mock_chunks

        doc_header_uri = "test-root/gdoc_header:doc123@1"
        result = self.toolkit.search_chunks_in_document(doc_header_uri, "test query")

        self.mock_service.search_chunks_in_document.assert_called_once_with(
            doc_header_uri, "test query"
        )
        assert result.results == mock_chunks
        assert result.next_cursor is None

    def test_pagination_no_more_pages(self):
        """Test pagination when no more pages are available."""
        # Mock that there are no more pages
        self.mock_service.search_documents.return_value = ([], None)

        result = self.toolkit.search_documents_by_title("test", cursor="some_cursor")

        assert result.results == []
        assert result.next_cursor is None

    def test_pagination_with_cursor(self):
        """Test pagination using cursor."""
        # Mock service returns results with next cursor
        self.mock_service.search_documents.return_value = (
            [Mock(spec=PageURI)],
            "next_cursor_token",
        )
        self.mock_context.get_page.return_value = Mock(spec=GDocHeader)

        result = self.toolkit.search_documents_by_title("test", cursor="current_cursor")

        # Should be called once with the cursor
        self.mock_service.search_documents.assert_called_once_with(
            {"title_query": "test"}, "current_cursor", 10
        )
        assert len(result.results) == 1
        assert result.next_cursor == "next_cursor_token"
