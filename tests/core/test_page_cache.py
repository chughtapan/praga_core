"""Tests for the PageCache class.

This module contains comprehensive tests for the PageCache functionality,
including page storage, retrieval, SqlAlchemy queries, and error handling.
"""

import tempfile
from datetime import datetime
from typing import Any, List, Optional

import pytest
from pydantic import BaseModel, Field

from praga_core.page_cache import (
    PageCache,
    PageCacheError,
    ProvenanceError,
)
from praga_core.page_cache.schema import PageRelationships
from praga_core.page_cache.serialization import (
    deserialize_from_storage,
    serialize_for_storage,
)
from praga_core.types import Page, PageURI


def clear_global_registry() -> None:
    """Clear the global table registry and reset SQLAlchemy metadata.

    This function is used for testing to ensure clean state between test runs.
    """
    from praga_core.page_cache.schema import Base, clear_table_registry

    clear_table_registry()
    Base.metadata.clear()


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear the global registry before and after each test."""
    clear_global_registry()
    yield
    clear_global_registry()


# Test page classes
class UserPage(Page):
    """Test user page."""

    name: str
    email: str
    age: Optional[int] = None

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.name) + len(self.email)) // 4


class PostPage(Page):
    """Test post page."""

    title: str
    content: str
    author_email: str

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


class EventPage(Page):
    """Test event page with datetime fields."""

    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = len(self.title) // 4


# Test fixtures
@pytest.fixture
def temp_db_url() -> str:
    """Provide a temporary database URL for testing."""
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    return f"sqlite:///{temp_file.name}"


@pytest.fixture
def page_cache(temp_db_url: str) -> PageCache:
    """Provide a fresh PageCache instance for each test."""
    return PageCache(temp_db_url, drop_previous=True)


@pytest.fixture
def sample_user() -> UserPage:
    """Provide a sample user page."""
    return UserPage(
        uri=PageURI(root="test", type="user", id="user1", version=1),
        name="Test User",
        email="test@example.com",
        age=30,
    )


@pytest.fixture
def sample_post() -> PostPage:
    """Provide a sample post page."""
    return PostPage(
        uri=PageURI(root="test", type="post", id="post1", version=1),
        title="Test Post",
        content="Test content for the post",
        author_email="test@example.com",
    )


@pytest.fixture
def sample_event() -> EventPage:
    """Provide a sample event page."""
    return EventPage(
        uri=PageURI(root="test", type="event", id="event1", version=1),
        title="Test Event",
        start_time=datetime(2024, 1, 1, 10, 0),
        end_time=datetime(2024, 1, 1, 11, 0),
        location="Test Location",
    )


class TestPageCacheInitialization:
    """Test basic PageCache initialization."""

    def test_initialization(self, temp_db_url: str) -> None:
        """Test basic PageCache initialization."""
        cache = PageCache(temp_db_url)
        assert cache.engine is not None

    def test_initialization_with_drop_previous(self, temp_db_url: str) -> None:
        """Test PageCache initialization with drop_previous=True."""
        cache = PageCache(temp_db_url, drop_previous=True)
        assert cache.engine is not None


class TestPageStorage:
    """Test page storage functionality."""

    def test_store_new_page(self, page_cache: PageCache, sample_user: UserPage) -> None:
        """Test storing a new page."""
        result = page_cache.store(sample_user)
        assert result is True  # Returns True for new pages

        # Verify page was stored
        stored_page = page_cache.get(UserPage, sample_user.uri)
        assert stored_page is not None
        assert stored_page.name == sample_user.name
        assert stored_page.email == sample_user.email
        assert stored_page.age == sample_user.age

    def test_store_duplicate_page(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test storing the same page twice (should fail)."""

        # Store first time
        result1 = page_cache.store(sample_user)
        assert result1 is True

        # Store second time (should raise error)
        with pytest.raises(
            PageCacheError, match="already exists and cannot be updated"
        ):
            page_cache.store(sample_user)

    def test_update_existing_page(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test updating an existing page (should fail)."""

        # Store initial page
        page_cache.store(sample_user)

        # Create updated version
        updated_user = UserPage(
            uri=sample_user.uri, name="Updated User", email=sample_user.email, age=31
        )

        # Try to store update (should fail)
        with pytest.raises(
            PageCacheError, match="already exists and cannot be updated"
        ):
            page_cache.store(updated_user)

        # Verify original page is unchanged
        stored_page = page_cache.get(UserPage, sample_user.uri)
        assert stored_page is not None
        assert stored_page.name == sample_user.name  # Original name
        assert stored_page.age == sample_user.age  # Original age

    def test_store_pages_different_types(
        self, page_cache: PageCache, sample_user: UserPage, sample_post: PostPage
    ) -> None:
        """Test storing pages of different types."""
        result1 = page_cache.store(sample_user)
        result2 = page_cache.store(sample_post)

        assert result1 is True
        assert result2 is True

        # Verify both pages were stored
        stored_user = page_cache.get(UserPage, sample_user.uri)
        stored_post = page_cache.get(PostPage, sample_post.uri)

        assert stored_user is not None
        assert stored_post is not None
        assert stored_user.name == sample_user.name
        assert stored_post.title == sample_post.title


class TestPageRetrieval:
    """Test page retrieval functionality."""

    def test_get_existing_page(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test retrieving an existing page."""
        page_cache.store(sample_user)

        retrieved_page = page_cache.get(UserPage, sample_user.uri)
        assert retrieved_page is not None
        assert retrieved_page.uri == sample_user.uri
        assert retrieved_page.name == sample_user.name
        assert retrieved_page.email == sample_user.email
        assert retrieved_page.age == sample_user.age

    def test_get_nonexistent_page(self, page_cache: PageCache) -> None:
        """Test retrieving a non-existent page."""
        nonexistent_uri = PageURI(root="test", type="user", id="nonexistent")
        result = page_cache.get(UserPage, nonexistent_uri)
        assert result is None

    def test_get_page_unregistered_type(self, page_cache: PageCache) -> None:
        """Test retrieving a page of unregistered type."""
        uri = PageURI(root="test", type="user", id="user1")
        result = page_cache.get(UserPage, uri)
        assert result is None


class TestSqlAlchemyQueries:
    """Test SqlAlchemy-style query functionality."""

    def test_find_by_exact_match(self, page_cache: PageCache) -> None:
        """Test finding pages by exact attribute match."""
        # Create and store multiple users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1", version=1),
                name="John Doe",
                email="john@example.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2", version=1),
                name="Jane Doe",
                email="jane@example.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3", version=1),
                name="Bob Smith",
                email="bob@example.com",
                age=25,
            ),
        ]

        for user in users:
            page_cache.store(user)

        # Test exact name match
        results = page_cache.find(UserPage).where(lambda t: t.name == "John Doe").all()
        assert len(results) == 1
        assert results[0].name == "John Doe"

        # Test exact age match
        results = page_cache.find(UserPage).where(lambda t: t.age == 30).all()
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"John Doe", "Jane Doe"}

    def test_find_by_like_pattern(self, page_cache: PageCache) -> None:
        """Test finding pages using LIKE patterns."""
        # Create and store multiple users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1", version=1),
                name="John Doe",
                email="john@example.com",
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2", version=1),
                name="Jane Doe",
                email="jane@example.com",
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3", version=1),
                name="Bob Smith",
                email="bob@example.com",
            ),
        ]

        for user in users:
            page_cache.store(user)

        # Test LIKE pattern for names
        results = page_cache.find(UserPage).where(lambda t: t.name.like("%Doe%")).all()
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"John Doe", "Jane Doe"}

        # Test case-insensitive LIKE (ilike)
        results = (
            page_cache.find(UserPage).where(lambda t: t.email.ilike("%EXAMPLE%")).all()
        )
        assert len(results) == 3

    def test_find_by_complex_query(self, page_cache: PageCache) -> None:
        """Test finding pages using complex query expressions."""
        # Create and store multiple users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1", version=1),
                name="John Doe",
                email="john@company.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2", version=1),
                name="Jane Smith",
                email="jane@company.com",
                age=25,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3", version=1),
                name="Bob Johnson",
                email="bob@personal.org",
                age=35,
            ),
        ]

        for user in users:
            page_cache.store(user)

        # Test complex AND query
        results = (
            page_cache.find(UserPage)
            .where(lambda t: (t.age > 25) & (t.email.like("%@company.com")))
            .all()
        )
        assert len(results) == 1
        assert results[0].name == "John Doe"

        # Test OR query
        results = (
            page_cache.find(UserPage)
            .where(lambda t: (t.name.like("%Doe")) | (t.age == 35))
            .all()
        )
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"John Doe", "Bob Johnson"}

    def test_find_with_lambda_expression(self, page_cache: PageCache) -> None:
        """Test finding pages using lambda expressions (the recommended approach)."""
        # Store a user
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="Test User",
            email="test@example.com",
        )
        page_cache.store(user)

        # Use lambda expression for queries
        results = (
            page_cache.find(UserPage)
            .where(lambda t: t.email == "test@example.com")
            .all()
        )

        assert len(results) == 1
        assert results[0].name == "Test User"

    def test_find_no_results(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test finding pages with no matching results."""
        page_cache.store(sample_user)

        results = (
            page_cache.find(UserPage).where(lambda t: t.name == "Nonexistent").all()
        )
        assert len(results) == 0

    def test_find_unregistered_type(self, page_cache: PageCache) -> None:
        """Test finding pages of unregistered type."""
        results = page_cache.find(UserPage).where(lambda t: t.name == "Test").all()
        assert len(results) == 0


class TestDateTimeHandling:
    """Test datetime field handling."""

    def test_store_and_retrieve_datetime(
        self, page_cache: PageCache, sample_event: EventPage
    ) -> None:
        """Test storing and retrieving pages with datetime fields."""
        page_cache.store(sample_event)

        retrieved_event = page_cache.get(EventPage, sample_event.uri)
        assert retrieved_event is not None
        assert retrieved_event.start_time == sample_event.start_time
        assert retrieved_event.end_time == sample_event.end_time
        assert retrieved_event.location == sample_event.location

    def test_find_by_datetime(self, page_cache: PageCache) -> None:
        """Test finding pages by datetime values."""
        # Create events with different times
        events = [
            EventPage(
                uri=PageURI(root="test", type="event", id="event1", version=1),
                title="Morning Event",
                start_time=datetime(2024, 1, 1, 10, 0),
                end_time=datetime(2024, 1, 1, 11, 0),
            ),
            EventPage(
                uri=PageURI(root="test", type="event", id="event2", version=1),
                title="Afternoon Event",
                start_time=datetime(2024, 1, 1, 14, 0),
                end_time=datetime(2024, 1, 1, 15, 0),
            ),
        ]

        for event in events:
            page_cache.store(event)

        # Test exact datetime match
        results = (
            page_cache.find(EventPage)
            .where(lambda t: t.start_time == datetime(2024, 1, 1, 10, 0))
            .all()
        )
        assert len(results) == 1
        assert results[0].title == "Morning Event"

    def test_datetime_with_microseconds(self, page_cache: PageCache) -> None:
        """Test datetime fields with microseconds."""
        event = EventPage(
            uri=PageURI(root="test", type="event", id="event_micro", version=1),
            title="Event with Microseconds",
            start_time=datetime(2024, 1, 1, 10, 0, 0, 123456),
            end_time=datetime(2024, 1, 1, 11, 0, 0, 789012),
        )

        page_cache.store(event)
        retrieved_event = page_cache.get(EventPage, event.uri)

        # Verify microseconds are preserved
        assert retrieved_event is not None
        assert retrieved_event.start_time == datetime(2024, 1, 1, 10, 0, 0, 123456)
        assert retrieved_event.end_time == datetime(2024, 1, 1, 11, 0, 0, 789012)


class TestOptionalFields:
    """Test handling of optional fields."""

    def test_store_page_with_none_values(self, page_cache: PageCache) -> None:
        """Test storing pages with None values in optional fields."""
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user_no_age", version=1),
            name="User Without Age",
            email="noage@example.com",
            age=None,
        )

        page_cache.store(user)
        retrieved_user = page_cache.get(UserPage, user.uri)

        assert retrieved_user is not None
        assert retrieved_user.name == "User Without Age"
        assert retrieved_user.email == "noage@example.com"
        assert retrieved_user.age is None


class TestAdvancedQueries:
    """Test advanced query functionality."""

    def test_complex_query_with_lambda_expressions(self, page_cache: PageCache) -> None:
        """Test complex queries using lambda expressions."""
        # Store some users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1", version=1),
                name="Alice",
                email="alice@example.com",
                age=25,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2", version=1),
                name="Bob",
                email="bob@example.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3", version=1),
                name="Charlie",
                email="charlie@example.com",
                age=35,
            ),
        ]

        for user in users:
            page_cache.store(user)

        # Find users with age between 25 and 30 using lambda
        results = (
            page_cache.find(UserPage)
            .where(lambda t: (t.age >= 25) & (t.age <= 30))
            .all()
        )

        assert len(results) == 2
        names = {user.name for user in results}
        assert names == {"Alice", "Bob"}


class TestCacheInstancesShareData:
    """Test that multiple PageCache instances can share data."""

    def test_multiple_cache_instances_share_data(self, temp_db_url: str) -> None:
        """Test that multiple PageCache instances using the same DB can share data."""
        # Create first cache instance and store a page
        cache1 = PageCache(temp_db_url, drop_previous=True)
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="Test User",
            email="test@example.com",
        )
        cache1.store(user)

        # Create second cache instance with same URL
        cache2 = PageCache(temp_db_url)

        # Should be able to retrieve the page from second instance
        retrieved_user = cache2.get(UserPage, user.uri)
        assert retrieved_user is not None
        assert retrieved_user.name == "Test User"


class TestURIHandling:
    """Test URI handling as primary key."""

    def test_uri_as_primary_key(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test that URI is used as primary key."""
        page_cache.store(sample_user)

        # Try to store another page with same URI (should fail)
        duplicate_user = UserPage(
            uri=sample_user.uri,  # Same URI
            name="Different Name",
            email="different@example.com",
        )
        with pytest.raises(
            PageCacheError, match="already exists and cannot be updated"
        ):
            page_cache.store(duplicate_user)

    def test_different_uris_different_records(self, page_cache: PageCache) -> None:
        """Test that different URIs create different records."""
        user1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User 1",
            email="user1@example.com",
        )
        user2 = UserPage(
            uri=PageURI(root="test", type="user", id="user2", version=1),
            name="User 2",
            email="user2@example.com",
        )

        result1 = page_cache.store(user1)
        result2 = page_cache.store(user2)

        assert result1 is True  # New insert
        assert result2 is True  # New insert

        # Both should be retrievable
        retrieved_user1 = page_cache.get(UserPage, user1.uri)
        retrieved_user2 = page_cache.get(UserPage, user2.uri)

        assert retrieved_user1 is not None
        assert retrieved_user2 is not None
        assert retrieved_user1.name == "User 1"
        assert retrieved_user2.name == "User 2"


class TestPageURISerialization:
    """Test PageURI serialization and deserialization in page_cache."""

    def test_convert_page_uris_for_storage_single_uri(self) -> None:
        """Test converting a single PageURI to string for storage."""

        uri = PageURI(root="test", type="doc", id="123", version=1)
        result = serialize_for_storage(uri)
        assert result == str(uri)
        assert isinstance(result, str)

    def test_convert_page_uris_for_storage_list_of_uris(self) -> None:
        """Test converting a list of PageURIs to strings for storage."""

        uris = [
            PageURI(root="test", type="doc", id="123", version=1),
            PageURI(root="test", type="doc", id="456", version=1),
        ]
        result = serialize_for_storage(uris)
        expected = [str(uri) for uri in uris]
        assert result == expected
        assert all(isinstance(item, str) for item in result)

    def test_convert_page_uris_for_storage_nested_structure(self) -> None:
        """Test converting nested structures containing PageURIs."""

        uri1 = PageURI(root="test", type="doc", id="123")
        uri2 = PageURI(root="test", type="doc", id="456")

        nested_data = {
            "single_uri": uri1,
            "uri_list": [uri1, uri2],
            "regular_data": "some string",
            "number": 42,
        }

        result = serialize_for_storage(nested_data)

        assert result["single_uri"] == str(uri1)
        assert result["uri_list"] == [str(uri1), str(uri2)]
        assert result["regular_data"] == "some string"
        assert result["number"] == 42

    def test_convert_page_uris_for_storage_non_uri_values(self) -> None:
        """Test that non-PageURI values are returned unchanged."""

        test_values = [
            "string",
            42,
            3.14,
            True,
            None,
            ["list", "of", "strings"],
            {"dict": "value"},
        ]

        for value in test_values:
            result = serialize_for_storage(value)
            assert result == value

    def test_convert_page_uris_from_storage_single_uri(
        self, page_cache: PageCache
    ) -> None:
        """Test converting a string back to PageURI from storage."""
        uri_string = "test/doc:123@1"
        result = deserialize_from_storage(uri_string, PageURI)

        assert isinstance(result, PageURI)
        assert result.root == "test"
        assert result.type == "doc"
        assert result.id == "123"

    def test_convert_page_uris_from_storage_optional_uri(self) -> None:
        """Test converting Optional[PageURI] from storage."""
        # Test with actual URI string
        uri_string = "test/doc:123@1"
        result = deserialize_from_storage(uri_string, Optional[PageURI])
        assert isinstance(result, PageURI)

        # Test with None
        result_none = deserialize_from_storage(None, Optional[PageURI])
        assert result_none is None

    def test_convert_page_uris_from_storage_list_of_uris(self) -> None:
        """Test converting List[PageURI] from storage."""
        uri_strings = ["test/doc:123@1", "test/doc:456@1"]
        result = deserialize_from_storage(uri_strings, List[PageURI])

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(uri, PageURI) for uri in result)
        assert result[0].id == "123"
        assert result[1].id == "456"

    def test_convert_page_uris_from_storage_non_uri_types(self) -> None:
        """Test that non-PageURI types are returned unchanged."""
        test_cases = [
            ("string", str),
            (42, int),
            (3.14, float),
            (True, bool),
            (["list"], list),
            ({"dict": "value"}, dict),
        ]

        for value, field_type in test_cases:
            result = deserialize_from_storage(value, field_type)
            assert result == value


class TestPageWithPageURIFields:
    """Test pages that contain PageURI fields."""

    class DocumentPage(Page):
        """Test document page with PageURI fields."""

        title: str
        content: str
        author_uri: Optional[PageURI] = None
        related_docs: list[PageURI] = []
        parent_doc: Optional[PageURI] = None

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    @pytest.fixture
    def sample_document_with_uris(self) -> "TestPageWithPageURIFields.DocumentPage":
        """Provide a sample document with PageURI fields."""
        return self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc1", version=1),
            title="Test Document",
            content="This is test content for the document",
            author_uri=PageURI(root="test", type="user", id="author1", version=1),
            related_docs=[
                PageURI(root="test", type="document", id="related1", version=1),
                PageURI(root="test", type="document", id="related2", version=1),
            ],
            parent_doc=PageURI(root="test", type="document", id="parent1", version=1),
        )

    def test_store_and_retrieve_page_with_page_uris(
        self,
        page_cache: PageCache,
        sample_document_with_uris: "TestPageWithPageURIFields.DocumentPage",
    ) -> None:
        """Test storing and retrieving a page with PageURI fields."""
        # Store the document
        result = page_cache.store(sample_document_with_uris)
        assert result is True

        # Retrieve the document
        retrieved_doc = page_cache.get(self.DocumentPage, sample_document_with_uris.uri)

        assert retrieved_doc is not None
        assert retrieved_doc.title == "Test Document"
        assert retrieved_doc.content == "This is test content for the document"

        # Verify PageURI fields are correctly deserialized
        assert isinstance(retrieved_doc.author_uri, PageURI)
        assert retrieved_doc.author_uri.type == "user"
        assert retrieved_doc.author_uri.id == "author1"

        assert isinstance(retrieved_doc.related_docs, list)
        assert len(retrieved_doc.related_docs) == 2
        assert all(isinstance(uri, PageURI) for uri in retrieved_doc.related_docs)
        assert retrieved_doc.related_docs[0].id == "related1"
        assert retrieved_doc.related_docs[1].id == "related2"

        assert isinstance(retrieved_doc.parent_doc, PageURI)
        assert retrieved_doc.parent_doc.id == "parent1"

    def test_store_and_retrieve_page_with_none_page_uris(
        self, page_cache: PageCache
    ) -> None:
        """Test storing and retrieving a page with None PageURI fields."""
        doc = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc2", version=1),
            title="Document Without URIs",
            content="Content without related URIs",
            author_uri=None,
            related_docs=[],
            parent_doc=None,
        )

        # Store the document
        result = page_cache.store(doc)
        assert result is True

        # Retrieve the document
        retrieved_doc = page_cache.get(self.DocumentPage, doc.uri)

        assert retrieved_doc is not None
        assert retrieved_doc.title == "Document Without URIs"
        assert retrieved_doc.author_uri is None
        assert retrieved_doc.related_docs == []
        assert retrieved_doc.parent_doc is None

    def test_find_pages_by_page_uri_fields(self, page_cache: PageCache) -> None:
        """Test finding pages by PageURI field values."""
        # Create documents with specific author
        author_uri = PageURI(root="test", type="user", id="author123", version=1)

        doc1 = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc1", version=1),
            title="Document 1",
            content="Content 1",
            author_uri=author_uri,
        )

        doc2 = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc2", version=1),
            title="Document 2",
            content="Content 2",
            author_uri=author_uri,
        )

        doc3 = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc3", version=1),
            title="Document 3",
            content="Content 3",
            author_uri=PageURI(
                root="test", type="user", id="different_author", version=1
            ),
        )

        # Store all documents
        page_cache.store(doc1)
        page_cache.store(doc2)
        page_cache.store(doc3)

        # Find documents by author_uri (note: stored as string in DB)
        results = (
            page_cache.find(self.DocumentPage)
            .where(lambda t: t.author_uri == str(author_uri))
            .all()
        )

        assert len(results) == 2
        titles = {doc.title for doc in results}
        assert titles == {"Document 1", "Document 2"}


class TestGoogleDocsPageURIs:
    """Test Google Docs specific PageURI handling (simulating real usage)."""

    class GDocHeader(Page):
        """Simulated Google Docs header page with PageURI fields."""

        document_id: str
        title: str
        chunk_count: int
        chunk_uris: list[PageURI] = []

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.title) // 4

    class GDocChunk(Page):
        """Simulated Google Docs chunk page with PageURI fields."""

        document_id: str
        chunk_index: int
        content: str
        prev_chunk_uri: Optional[PageURI] = None
        next_chunk_uri: Optional[PageURI] = None
        header_uri: PageURI

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    def test_google_docs_end_to_end_scenario(self, page_cache: PageCache) -> None:
        """Test a realistic Google Docs scenario with headers and chunks."""
        document_id = "1234567890"

        # Create chunk URIs
        chunk_uris = [
            PageURI(
                root="google", type="gdoc_chunk", id=f"{document_id}(0)", version=1
            ),
            PageURI(
                root="google", type="gdoc_chunk", id=f"{document_id}(1)", version=1
            ),
            PageURI(
                root="google", type="gdoc_chunk", id=f"{document_id}(2)", version=1
            ),
        ]

        # Create header with chunk URIs
        header = self.GDocHeader(
            uri=PageURI(root="google", type="gdoc_header", id=document_id, version=1),
            document_id=document_id,
            title="Test Google Doc",
            chunk_count=3,
            chunk_uris=chunk_uris,
        )

        # Create chunks with prev/next links
        chunks = []
        for i in range(3):
            chunk = self.GDocChunk(
                uri=chunk_uris[i],
                document_id=document_id,
                chunk_index=i,
                content=f"Content of chunk {i}",
                prev_chunk_uri=chunk_uris[i - 1] if i > 0 else None,
                next_chunk_uri=chunk_uris[i + 1] if i < 2 else None,
                header_uri=header.uri,
            )
            chunks.append(chunk)

        # Store header and chunks
        page_cache.store(header)
        for chunk in chunks:
            page_cache.store(chunk)

        # Retrieve and verify header
        retrieved_header = page_cache.get(self.GDocHeader, header.uri)
        assert retrieved_header is not None
        assert retrieved_header.title == "Test Google Doc"
        assert len(retrieved_header.chunk_uris) == 3
        assert all(isinstance(uri, PageURI) for uri in retrieved_header.chunk_uris)

        # Retrieve and verify chunks
        for i, chunk_uri in enumerate(chunk_uris):
            retrieved_chunk = page_cache.get(self.GDocChunk, chunk_uri)
            assert retrieved_chunk is not None
            assert retrieved_chunk.chunk_index == i
            assert retrieved_chunk.content == f"Content of chunk {i}"

            # Verify navigation links
            if i > 0:
                assert isinstance(retrieved_chunk.prev_chunk_uri, PageURI)
                assert retrieved_chunk.prev_chunk_uri.id == f"{document_id}({i-1})"
            else:
                assert retrieved_chunk.prev_chunk_uri is None

            if i < 2:
                assert isinstance(retrieved_chunk.next_chunk_uri, PageURI)
                assert retrieved_chunk.next_chunk_uri.id == f"{document_id}({i+1})"
            else:
                assert retrieved_chunk.next_chunk_uri is None

            # Verify header link
            assert isinstance(retrieved_chunk.header_uri, PageURI)
            assert retrieved_chunk.header_uri.id == document_id

    def test_find_chunks_by_document_id(self, page_cache: PageCache) -> None:
        """Test finding all chunks for a specific document."""
        document_id = "test_document_456"

        # Create and store multiple chunks for the document
        chunks = []
        for i in range(3):
            chunk = self.GDocChunk(
                uri=PageURI(
                    root="google",
                    type="gdoc_chunk",
                    id=f"{document_id}({i})",
                    version=1,
                ),
                document_id=document_id,
                chunk_index=i,
                content=f"Chunk {i} content",
                header_uri=PageURI(
                    root="google", type="gdoc_header", id=document_id, version=1
                ),
            )
            chunks.append(chunk)
            page_cache.store(chunk)

        # Find all chunks for this document
        results = (
            page_cache.find(self.GDocChunk)
            .where(lambda t: t.document_id == document_id)
            .all()
        )

        assert len(results) == 3
        chunk_indices = {chunk.chunk_index for chunk in results}
        assert chunk_indices == {0, 1, 2}


class TestProvenanceTracking:
    """Test provenance tracking functionality."""

    class EmailPage(Page):
        """Test email page."""

        subject: str
        content: str
        sender: str

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = (len(self.subject) + len(self.content)) // 4

    class ThreadPage(Page):
        """Test email thread page."""

        title: str
        message_count: int

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.title) // 4

    class GoogleDocPage(Page):
        """Test Google Docs page."""

        title: str
        content: str

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = (len(self.title) + len(self.content)) // 4

    class ChunkPage(Page):
        """Test chunk page derived from Google Doc."""

        chunk_index: int
        content: str

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    def test_store_page_with_parent_uri_parameter(self, page_cache: PageCache) -> None:
        """Test storing a page with parent_uri specified as parameter."""
        # Store parent first
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Test Document",
            content="This is a test document",
        )
        page_cache.store(parent_doc)

        # Store child with parent_uri parameter
        chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=0,
            content="This is a test",
        )

        result = page_cache.store(chunk, parent_uri=parent_doc.uri)
        assert result is True

        # Verify parent_uri was set
        stored_chunk = page_cache.get(self.ChunkPage, chunk.uri)
        assert stored_chunk is not None
        assert stored_chunk.parent_uri == parent_doc.uri

    def test_store_page_with_parent_uri_on_page(self, page_cache: PageCache) -> None:
        """Test storing a page with parent_uri set on the page instance."""
        # Store parent first
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Test Document",
            content="This is a test document",
        )
        page_cache.store(parent_doc)

        # Store child with parent_uri on page
        chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=0,
            content="This is a test",
            parent_uri=parent_doc.uri,
        )

        result = page_cache.store(chunk)
        assert result is True

        # Verify parent_uri was preserved
        stored_chunk = page_cache.get(self.ChunkPage, chunk.uri)
        assert stored_chunk is not None
        assert stored_chunk.parent_uri == parent_doc.uri

    def test_parent_uri_parameter_overrides_page_parent_uri(
        self, page_cache: PageCache
    ) -> None:
        """Test that parent_uri parameter overrides page's parent_uri."""

        # Store two potential parents
        parent1 = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Document 1",
            content="Content 1",
        )
        parent2 = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc2", version=1),
            title="Document 2",
            content="Content 2",
        )
        page_cache.store(parent1)
        page_cache.store(parent2)

        # Create child with parent_uri set to parent1
        chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=0,
            content="Test chunk",
            parent_uri=parent1.uri,
        )

        # Store with parent_uri parameter set to parent2 (should override)
        result = page_cache.store(chunk, parent_uri=parent2.uri)
        assert result is True

        # Verify parent_uri was overridden
        stored_chunk = page_cache.get(self.ChunkPage, chunk.uri)
        assert stored_chunk is not None
        assert stored_chunk.parent_uri == parent2.uri

    def test_store_page_no_parent_tracking(self, page_cache: PageCache) -> None:
        """Test storing a page without any parent tracking (should work as before)."""
        # Create email and thread without parent-child relationship
        email = self.EmailPage(
            uri=PageURI(root="test", type="email", id="email1", version=1),
            subject="Test Email",
            content="Test content",
            sender="test@example.com",
        )

        thread = self.ThreadPage(
            uri=PageURI(root="test", type="thread", id="thread1", version=1),
            title="Test Thread",
            message_count=5,
        )

        result1 = page_cache.store(email)
        result2 = page_cache.store(thread)

        assert result1 is True
        assert result2 is True

    def test_provenance_precheck_parent_not_exist(self, page_cache: PageCache) -> None:
        """Test that storing fails when parent doesn't exist."""
        from praga_core.page_cache import ProvenanceError

        nonexistent_parent = PageURI(
            root="test", type="gdoc", id="nonexistent", version=1
        )

        chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=0,
            content="Test chunk",
        )

        with pytest.raises(
            ProvenanceError, match="Parent page .* does not exist in cache"
        ):
            page_cache.store(chunk, parent_uri=nonexistent_parent)

    def test_provenance_precheck_child_already_exists(
        self, page_cache: PageCache
    ) -> None:
        """Test that storing fails when child already exists."""
        from praga_core.page_cache import PageCacheError

        # Store parent
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Test Document",
            content="This is a test document",
        )
        page_cache.store(parent_doc)

        # Store child first time
        chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=0,
            content="Test chunk",
        )
        page_cache.store(chunk)

        # Try to store with parent relationship (should fail because child exists)
        with pytest.raises(
            PageCacheError, match="already exists and cannot be updated"
        ):
            page_cache.store(chunk, parent_uri=parent_doc.uri)

    def test_provenance_precheck_same_page_type(self, page_cache: PageCache) -> None:
        """Test that storing fails when parent and child are same page type."""

        # Store parent doc
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Parent Document",
            content="Parent content",
        )
        page_cache.store(parent_doc)

        # Try to store another doc as child (same type - should fail)
        child_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc2", version=1),
            title="Child Document",
            content="Child content",
        )

        with pytest.raises(
            ProvenanceError, match="Parent and child cannot be the same page type"
        ):
            page_cache.store(child_doc, parent_uri=parent_doc.uri)

    def test_provenance_precheck_parent_version_number(
        self, page_cache: PageCache
    ) -> None:
        """Test that storing fails when parent has invalid version number."""

        # Store parent with version 0 (should still be stored)
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=0),
            title="Test Document",
            content="This is a test document",
        )
        page_cache.store(parent_doc)

        # Try to use it as parent (should fail due to version 0)
        chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=0,
            content="Test chunk",
        )

        with pytest.raises(
            ProvenanceError, match="Parent URI must have a fixed version number"
        ):
            page_cache.store(chunk, parent_uri=parent_doc.uri)

    def test_get_children(self, page_cache: PageCache) -> None:
        """Test getting children of a parent page."""
        # Store parent doc
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Parent Document",
            content="Parent content",
        )
        page_cache.store(parent_doc)

        # Store multiple chunks as children
        chunks = []
        for i in range(3):
            chunk = self.ChunkPage(
                uri=PageURI(root="test", type="chunk", id=f"chunk{i}", version=1),
                chunk_index=i,
                content=f"Chunk {i} content",
                parent_uri=parent_doc.uri,
            )
            page_cache.store(chunk)
            chunks.append(chunk)

        # Get children
        children = page_cache.get_children(parent_doc.uri)

        assert len(children) == 3
        child_uris = {child.uri for child in children}
        expected_uris = {chunk.uri for chunk in chunks}
        assert child_uris == expected_uris

    def test_get_children_no_children(self, page_cache: PageCache) -> None:
        """Test getting children when page has no children."""
        # Store page without children
        page = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Document",
            content="Content",
        )
        page_cache.store(page)

        children = page_cache.get_children(page.uri)
        assert len(children) == 0

    def test_get_provenance_chain(self, page_cache: PageCache) -> None:
        """Test getting the full provenance chain."""
        # Store grandparent document
        grandparent = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="grandparent", version=1),
            title="Grandparent Document",
            content="Grandparent content",
        )
        page_cache.store(grandparent)

        # Store parent chunk with grandparent as parent
        parent = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="parent", version=1),
            chunk_index=0,
            content="Parent chunk",
            parent_uri=grandparent.uri,
        )
        page_cache.store(parent)

        # Store child document with parent chunk as parent (different types, so allowed)
        child = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="child", version=1),
            title="Child Document",
            content="Child content",
        )
        page_cache.store(child, parent_uri=parent.uri)

        # Get provenance chain for child
        chain = page_cache.get_lineage(child.uri)

        assert len(chain) == 3
        assert chain[0].uri == grandparent.uri
        assert chain[1].uri == parent.uri
        assert chain[2].uri == child.uri

    def test_get_provenance_chain_no_parent(self, page_cache: PageCache) -> None:
        """Test getting provenance chain for page with no parent."""
        # Store page without parent
        page = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="doc1", version=1),
            title="Document",
            content="Content",
        )
        page_cache.store(page)

        chain = page_cache.get_lineage(page.uri)

        assert len(chain) == 1
        assert chain[0].uri == page.uri

    def test_get_provenance_chain_nonexistent_page(self, page_cache: PageCache) -> None:
        """Test getting provenance chain for non-existent page."""
        nonexistent_uri = PageURI(
            root="test", type="chunk", id="nonexistent", version=1
        )

        chain = page_cache.get_lineage(nonexistent_uri)
        assert len(chain) == 0

    def test_example_google_docs_scenario(self, page_cache: PageCache) -> None:
        """Test the Google Docs example scenario from the requirements."""
        # Store the Google Doc
        gdoc = self.GoogleDocPage(
            uri=PageURI(root="test", type="gdoc", id="my_doc", version=1),
            title="My Google Document",
            content="This is a long document that will be chunked.",
        )
        page_cache.store(gdoc)

        # Store chunks derived from the Google Doc
        chunks = []
        for i in range(3):
            chunk = self.ChunkPage(
                uri=PageURI(
                    root="test", type="chunk", id=f"my_doc_chunk_{i}", version=1
                ),
                chunk_index=i,
                content=f"Chunk {i} of the document",
                parent_uri=gdoc.uri,
            )
            page_cache.store(chunk)
            chunks.append(chunk)

        # Verify relationships
        children = page_cache.get_children(gdoc.uri)
        assert len(children) == 3

        # Verify each chunk has the correct parent
        for i, chunk in enumerate(chunks):
            stored_chunk = page_cache.get(self.ChunkPage, chunk.uri)
            assert stored_chunk is not None
            assert stored_chunk.parent_uri == gdoc.uri
            assert stored_chunk.chunk_index == i

    def test_example_email_thread_scenario(self, page_cache: PageCache) -> None:
        """Test the email thread example scenario from the requirements."""
        # Store emails and threads separately (no parent-child relationship)
        emails = []
        for i in range(3):
            email = self.EmailPage(
                uri=PageURI(root="test", type="email", id=f"email_{i}", version=1),
                subject=f"Email Subject {i}",
                content=f"Email content {i}",
                sender=f"user{i}@example.com",
            )
            page_cache.store(email)
            emails.append(email)

        thread = self.ThreadPage(
            uri=PageURI(root="test", type="thread", id="thread_1", version=1),
            title="Email Thread",
            message_count=len(emails),
        )
        page_cache.store(thread)

        # Verify no parent-child relationships exist
        for email in emails:
            stored_email = page_cache.get(self.EmailPage, email.uri)
            assert stored_email is not None
            assert stored_email.parent_uri is None

        stored_thread = page_cache.get(self.ThreadPage, thread.uri)
        assert stored_thread is not None
        assert stored_thread.parent_uri is None

        # Verify no children relationships
        assert len(page_cache.get_children(thread.uri)) == 0
        for email in emails:
            assert len(page_cache.get_children(email.uri)) == 0


class TestPageRelationshipsTable:
    """Test the PageRelationships table functionality and optimization."""

    class DocPage(Page):
        """Test document page."""

        title: str
        content: str

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    class SectionPage(Page):
        """Test section page."""

        title: str
        section_content: str

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.section_content) // 4

    def test_relationships_table_created(self, page_cache: PageCache) -> None:
        """Test that the PageRelationships table is created automatically."""

        # Check that the table exists in the database
        with page_cache.get_session() as session:
            # This should not raise an error if table exists
            result = session.query(PageRelationships).count()
            assert result == 0  # Should be empty initially

    def test_relationship_stored_when_page_has_parent(
        self, page_cache: PageCache
    ) -> None:
        """Test that relationships are stored in the PageRelationships table."""

        # Store parent page
        parent = self.DocPage(
            uri=PageURI(root="test", type="doc", id="parent", version=1),
            title="Parent Document",
            content="Parent content",
        )
        page_cache.store(parent)

        # Store child page with parent relationship
        child = self.SectionPage(
            uri=PageURI(root="test", type="section", id="child", version=1),
            title="Child Section",
            section_content="Child content",
        )
        page_cache.store(child, parent_uri=parent.uri)

        # Verify relationship was stored in the relationships table
        with page_cache.get_session() as session:
            relationships = session.query(PageRelationships).all()
            assert len(relationships) == 1

            rel = relationships[0]
            assert rel.source_uri == str(child.uri)
            assert rel.target_uri == str(parent.uri)
            assert rel.relationship_type == "parent"
            assert rel.created_at is not None

    def test_relationship_immutable_with_different_versions(
        self, page_cache: PageCache
    ) -> None:
        """Test that relationships work with different page versions."""

        # Store two parent pages
        parent1 = self.DocPage(
            uri=PageURI(root="test", type="doc", id="parent1", version=1),
            title="Parent 1",
            content="Parent 1 content",
        )
        parent2 = self.DocPage(
            uri=PageURI(root="test", type="doc", id="parent2", version=1),
            title="Parent 2",
            content="Parent 2 content",
        )
        page_cache.store(parent1)
        page_cache.store(parent2)

        # Store child with first parent
        child1 = self.SectionPage(
            uri=PageURI(root="test", type="section", id="child", version=1),
            title="Child Section",
            section_content="Child content",
        )
        page_cache.store(child1, parent_uri=parent1.uri)

        # Store different version of child with second parent (different URI due to version)
        child2 = self.SectionPage(
            uri=PageURI(root="test", type="section", id="child", version=2),
            title="Child Section v2",
            section_content="Updated content",
        )
        page_cache.store(child2, parent_uri=parent2.uri)

        # Verify both relationships exist independently
        with page_cache.get_session() as session:
            relationships = session.query(PageRelationships).all()
            assert len(relationships) == 2

            # Find relationships by source
            child1_rel = next(
                r for r in relationships if r.source_uri == str(child1.uri)
            )
            child2_rel = next(
                r for r in relationships if r.source_uri == str(child2.uri)
            )

            assert child1_rel.target_uri == str(parent1.uri)
            assert child2_rel.target_uri == str(parent2.uri)

    def test_pages_without_parent_have_no_relationships(
        self, page_cache: PageCache
    ) -> None:
        """Test that pages stored without a parent have no relationships."""

        # Store a page without parent
        page_without_parent = self.DocPage(
            uri=PageURI(root="test", type="doc", id="orphan", version=1),
            title="Orphan Page",
            content="Content without parent",
        )
        page_cache.store(page_without_parent)

        # Store another page with a parent
        parent = self.SectionPage(
            uri=PageURI(root="test", type="section", id="parent", version=1),
            title="Parent",
            section_content="Parent content",
        )
        child = self.DocPage(
            uri=PageURI(root="test", type="doc", id="child", version=1),
            title="Child",
            content="Child content",
        )
        page_cache.store(parent)
        page_cache.store(child, parent_uri=parent.uri)

        # Verify only one relationship exists (for the child with parent)
        with page_cache.get_session() as session:
            relationships = session.query(PageRelationships).all()
            assert len(relationships) == 1
            assert relationships[0].source_uri == str(child.uri)
            assert relationships[0].target_uri == str(parent.uri)

            # Verify orphan page has no relationships
            orphan_relationships = (
                session.query(PageRelationships)
                .filter_by(source_uri=str(page_without_parent.uri))
                .count()
            )
            assert orphan_relationships == 0

    def test_get_children_uses_relationships_table(self, page_cache: PageCache) -> None:
        """Test that get_children uses the relationships table efficiently."""
        # Store parent
        parent = self.DocPage(
            uri=PageURI(root="test", type="doc", id="parent", version=1),
            title="Parent Document",
            content="Parent content",
        )
        page_cache.store(parent)

        # Store multiple children
        children = []
        for i in range(3):
            child = self.SectionPage(
                uri=PageURI(root="test", type="section", id=f"child{i}", version=1),
                title=f"Child {i}",
                section_content=f"Child {i} content",
            )
            page_cache.store(child, parent_uri=parent.uri)
            children.append(child)

        # Get children using the optimized method
        retrieved_children = page_cache.get_children(parent.uri)

        # Verify all children are returned
        assert len(retrieved_children) == 3
        child_titles = {child.title for child in retrieved_children}
        expected_titles = {"Child 0", "Child 1", "Child 2"}
        assert child_titles == expected_titles

    def test_get_provenance_chain_uses_relationships_table(
        self, page_cache: PageCache
    ) -> None:
        """Test that get_provenance_chain uses the relationships table efficiently."""
        # Create a chain: grandparent -> parent -> child
        grandparent = self.DocPage(
            uri=PageURI(root="test", type="doc", id="grandparent", version=1),
            title="Grandparent",
            content="Grandparent content",
        )
        parent = self.SectionPage(
            uri=PageURI(root="test", type="section", id="parent", version=1),
            title="Parent",
            section_content="Parent content",
        )
        child = self.DocPage(
            uri=PageURI(root="test", type="doc", id="child", version=1),
            title="Child",
            content="Child content",
        )

        page_cache.store(grandparent)
        page_cache.store(parent, parent_uri=grandparent.uri)
        page_cache.store(child, parent_uri=parent.uri)

        # Get provenance chain
        chain = page_cache.get_lineage(child.uri)

        # Verify chain is correct
        assert len(chain) == 3
        assert chain[0].title == "Grandparent"
        assert chain[1].title == "Parent"
        assert chain[2].title == "Child"

    def test_relationships_table_indexes_exist(self, page_cache: PageCache) -> None:
        """Test that the relationships table has proper indexes for performance."""

        # Get the table object
        table = PageRelationships.__table__

        # Check that indexes exist
        index_names = {idx.name for idx in table.indexes}
        assert "idx_relationships_target" in index_names
        assert "idx_relationships_source" in index_names

    def test_multiple_relationship_types_supported(self, page_cache: PageCache) -> None:
        """Test that the relationships table can support different relationship types."""

        # Store parent and child
        parent = self.DocPage(
            uri=PageURI(root="test", type="doc", id="parent", version=1),
            title="Parent",
            content="Parent content",
        )
        child = self.SectionPage(
            uri=PageURI(root="test", type="section", id="child", version=1),
            title="Child",
            section_content="Child content",
        )

        page_cache.store(parent)
        page_cache.store(child, parent_uri=parent.uri)

        # Manually add a different relationship type for future extensibility
        with page_cache.get_session() as session:
            custom_rel = PageRelationships(
                source_uri=str(child.uri),
                relationship_type="references",
                target_uri=str(parent.uri),
            )
            session.add(custom_rel)
            session.commit()

            # Verify both relationships exist
            relationships = (
                session.query(PageRelationships)
                .filter_by(source_uri=str(child.uri))
                .all()
            )
            assert len(relationships) == 2
            rel_types = {rel.relationship_type for rel in relationships}
            assert rel_types == {"parent", "references"}


class TestComprehensiveSerialization:
    """Test comprehensive serialization of complex Pydantic models."""

    class NestedModel(BaseModel):
        """A nested Pydantic model for testing serialization."""

        name: str
        value: int
        uri: Optional[PageURI] = None

    class ComplexPage(Page):
        """A complex page with nested Pydantic models for testing."""

        title: str
        nested_model: "TestComprehensiveSerialization.NestedModel"
        model_list: List["TestComprehensiveSerialization.NestedModel"]
        optional_model: Optional["TestComprehensiveSerialization.NestedModel"] = None

    def test_store_and_retrieve_complex_page_with_pydantic_models(
        self, page_cache: PageCache
    ) -> None:
        """Test storing and retrieving pages with nested Pydantic models."""
        nested_model = self.NestedModel(
            name="Test Nested",
            value=42,
            uri=PageURI(root="test", type="nested", id="nested1", version=1),
        )

        model_list = [
            self.NestedModel(name="Item 1", value=10),
            self.NestedModel(
                name="Item 2",
                value=20,
                uri=PageURI(root="test", type="item", id="item2", version=1),
            ),
        ]

        complex_page = self.ComplexPage(
            uri=PageURI(root="test", type="complex", id="complex1", version=1),
            title="Complex Page Test",
            nested_model=nested_model,
            model_list=model_list,
            optional_model=None,
        )

        # Store the complex page
        result = page_cache.store(complex_page)
        assert result is True

        # Retrieve the complex page
        retrieved_page = page_cache.get(self.ComplexPage, complex_page.uri)

        assert retrieved_page is not None
        assert retrieved_page.title == "Complex Page Test"

        # Verify nested model serialization/deserialization
        assert isinstance(retrieved_page.nested_model, self.NestedModel)
        assert retrieved_page.nested_model.name == "Test Nested"
        assert retrieved_page.nested_model.value == 42
        assert isinstance(retrieved_page.nested_model.uri, PageURI)
        assert retrieved_page.nested_model.uri.id == "nested1"

        # Verify list of models serialization/deserialization
        assert isinstance(retrieved_page.model_list, list)
        assert len(retrieved_page.model_list) == 2

        assert all(
            isinstance(model, self.NestedModel) for model in retrieved_page.model_list
        )
        assert retrieved_page.model_list[0].name == "Item 1"
        assert retrieved_page.model_list[0].value == 10
        assert retrieved_page.model_list[0].uri is None

        assert retrieved_page.model_list[1].name == "Item 2"
        assert retrieved_page.model_list[1].value == 20
        assert isinstance(retrieved_page.model_list[1].uri, PageURI)
        assert retrieved_page.model_list[1].uri.id == "item2"

        # Verify optional model is None
        assert retrieved_page.optional_model is None

    def test_store_and_retrieve_complex_page_with_optional_model(
        self, page_cache: PageCache
    ) -> None:
        """Test storing and retrieving pages with optional Pydantic models."""
        optional_model = self.NestedModel(
            name="Optional Model",
            value=99,
            uri=PageURI(root="test", type="optional", id="opt1", version=1),
        )

        complex_page = self.ComplexPage(
            uri=PageURI(root="test", type="complex", id="complex2", version=1),
            title="Complex Page with Optional",
            nested_model=self.NestedModel(name="Required", value=1),
            model_list=[],
            optional_model=optional_model,
        )

        # Store the complex page
        result = page_cache.store(complex_page)
        assert result is True

        # Retrieve the complex page
        retrieved_page = page_cache.get(self.ComplexPage, complex_page.uri)

        assert retrieved_page is not None
        assert retrieved_page.title == "Complex Page with Optional"

        # Verify optional model serialization/deserialization
        assert isinstance(retrieved_page.optional_model, self.NestedModel)
        assert retrieved_page.optional_model.name == "Optional Model"
        assert retrieved_page.optional_model.value == 99
        assert isinstance(retrieved_page.optional_model.uri, PageURI)
        assert retrieved_page.optional_model.uri.id == "opt1"

    def test_find_pages_with_complex_models(self, page_cache: PageCache) -> None:
        """Test querying pages that contain complex Pydantic models."""
        # Create pages with different nested model names
        page1 = self.ComplexPage(
            uri=PageURI(root="test", type="complex", id="find1", version=1),
            title="Find Test 1",
            nested_model=self.NestedModel(name="Search Target", value=100),
            model_list=[],
        )

        page2 = self.ComplexPage(
            uri=PageURI(root="test", type="complex", id="find2", version=1),
            title="Find Test 2",
            nested_model=self.NestedModel(name="Different Name", value=200),
            model_list=[],
        )

        page_cache.store(page1)
        page_cache.store(page2)

        # Find pages by title (which should work normally)
        results = (
            page_cache.find(self.ComplexPage)
            .where(lambda t: t.title.like("Find Test%"))
            .all()
        )

        assert len(results) == 2
        titles = {page.title for page in results}
        assert titles == {"Find Test 1", "Find Test 2"}

        # Verify the complex models are properly deserialized
        for page in results:
            assert isinstance(page.nested_model, self.NestedModel)
            assert page.nested_model.value in [100, 200]


class TestVersioning:
    """Test URI prefix and version handling with composite primary keys."""

    def test_store_and_retrieve_multiple_versions(self, page_cache: PageCache) -> None:
        """Test storing and retrieving multiple versions of the same page."""
        # Create multiple versions of the same page
        user_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User Version 1",
            email="user@example.com",
            age=25,
        )

        user_v2 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=2),
            name="User Version 2",
            email="user@example.com",
            age=26,
        )

        user_v3 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=3),
            name="User Version 3",
            email="user@example.com",
            age=27,
        )

        # Store all versions
        result1 = page_cache.store(user_v1)
        result2 = page_cache.store(user_v2)
        result3 = page_cache.store(user_v3)

        assert result1 is True
        assert result2 is True
        assert result3 is True

        # Retrieve each version
        retrieved_v1 = page_cache.get(UserPage, user_v1.uri)
        retrieved_v2 = page_cache.get(UserPage, user_v2.uri)
        retrieved_v3 = page_cache.get(UserPage, user_v3.uri)

        assert retrieved_v1 is not None
        assert retrieved_v2 is not None
        assert retrieved_v3 is not None

        assert retrieved_v1.name == "User Version 1"
        assert retrieved_v1.age == 25
        assert retrieved_v2.name == "User Version 2"
        assert retrieved_v2.age == 26
        assert retrieved_v3.name == "User Version 3"
        assert retrieved_v3.age == 27

    def test_get_latest_version(self, page_cache: PageCache) -> None:
        """Test getting the latest version number for a URI prefix."""
        prefix = "test/user:user1"

        # Should return None when no versions exist
        latest = page_cache.get_latest_version(UserPage, prefix)
        assert latest is None

        # Store multiple versions
        user_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User Version 1",
            email="user@example.com",
        )
        user_v3 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=3),
            name="User Version 3",
            email="user@example.com",
        )
        user_v2 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=2),
            name="User Version 2",
            email="user@example.com",
        )

        page_cache.store(user_v1)
        page_cache.store(user_v3)  # Store v3 before v2 to test ordering
        page_cache.store(user_v2)

        # Should return the highest version number
        latest = page_cache.get_latest_version(UserPage, prefix)
        assert latest == 3

    def test_get_latest_functionality(self, page_cache: PageCache) -> None:
        """Test getting the latest version through get_latest method."""
        prefix = "test/user:user1"

        # Should return None when no versions exist
        latest_page = page_cache.get_latest(UserPage, prefix)
        assert latest_page is None

        # Store multiple versions
        user_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User Version 1",
            email="user@example.com",
            age=25,
        )
        user_v2 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=2),
            name="User Version 2",
            email="user@example.com",
            age=26,
        )

        page_cache.store(user_v1)
        page_cache.store(user_v2)

        # Should return the latest version page
        latest_page = page_cache.get_latest(UserPage, prefix)
        assert latest_page is not None
        assert latest_page.name == "User Version 2"
        assert latest_page.age == 26
        assert latest_page.uri.version == 2

    def test_prefix_property_usage(self, page_cache: PageCache) -> None:
        """Test that the PageURI prefix property works correctly in practice."""
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user123", version=5),
            name="Test User",
            email="test@example.com",
        )

        # Test the prefix property
        assert user.uri.prefix == "test/user:user123"

        page_cache.store(user)

        # Use the prefix to get the latest version
        latest_version = page_cache.get_latest_version(UserPage, user.uri.prefix)
        assert latest_version == 5

        latest_page = page_cache.get_latest(UserPage, user.uri.prefix)
        assert latest_page is not None
        assert latest_page.name == "Test User"

    def test_different_prefixes_independent(self, page_cache: PageCache) -> None:
        """Test that different URI prefixes are handled independently."""
        # Create pages with different prefixes
        user1_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User 1 Version 1",
            email="user1@example.com",
        )
        user1_v2 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=2),
            name="User 1 Version 2",
            email="user1@example.com",
        )

        user2_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user2", version=1),
            name="User 2 Version 1",
            email="user2@example.com",
        )

        page_cache.store(user1_v1)
        page_cache.store(user1_v2)
        page_cache.store(user2_v1)

        # Check that each prefix has its own version history
        user1_latest = page_cache.get_latest_version(UserPage, "test/user:user1")
        user2_latest = page_cache.get_latest_version(UserPage, "test/user:user2")

        assert user1_latest == 2
        assert user2_latest == 1

        # Check that latest pages are correct
        user1_latest_page = page_cache.get_latest(UserPage, "test/user:user1")
        user2_latest_page = page_cache.get_latest(UserPage, "test/user:user2")

        assert user1_latest_page is not None
        assert user2_latest_page is not None
        assert user1_latest_page.name == "User 1 Version 2"
        assert user2_latest_page.name == "User 2 Version 1"


class TestPageCacheDefaultVersionFunctionality:
    """Test default version functionality in PageCache."""

    def test_store_page_with_default_version_raises_error(
        self, page_cache: PageCache
    ) -> None:
        """Test that storing a page with default version raises an error."""
        import pytest

        # Create page with default version URI
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=None),
            name="Test User",
            email="test@example.com",
            age=30,
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="Cannot store page with None version"):
            page_cache.store(user)

    def test_retrieve_default_version_gets_highest_version(
        self, page_cache: PageCache
    ) -> None:
        """Test that requesting default version returns the highest actual version."""
        # Store multiple versions
        user_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User v1",
            email="test@example.com",
        )
        user_v3 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=3),
            name="User v3",
            email="test@example.com",
        )

        page_cache.store(user_v1)
        page_cache.store(user_v3)

        # Request default version should return v3 (highest)
        default_uri = PageURI(root="test", type="user", id="user1", version=None)
        retrieved = page_cache.get(UserPage, default_uri)

        assert retrieved is not None
        assert retrieved.name == "User v3"  # Should get version 3
        assert retrieved.uri.version == 3  # Page should have actual version

    def test_retrieve_default_version_for_nonexistent_page(
        self, page_cache: PageCache
    ) -> None:
        """Test getting default version for a page that doesn't exist."""
        uri = PageURI(root="test", type="user", id="nonexistent", version=None)
        result = page_cache.get(UserPage, uri)
        assert result is None


class TestCacheInvalidation:
    """Test cache invalidation functionality."""

    class GoogleDocPage(Page):
        """Test Google Docs page with revision tracking."""

        title: str
        content: str
        revision: str = Field(exclude=True)  # Excluded field for validation

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    class ChunkPage(Page):
        """Test chunk page derived from Google Doc."""

        chunk_index: int
        content: str
        doc_revision: str = Field(exclude=True)  # For validation

        def __init__(self, **data: Any) -> None:
            super().__init__(**data)
            self._metadata.token_count = len(self.content) // 4

    def test_register_invalidator(self, page_cache: PageCache) -> None:
        """Test registering an invalidator function."""

        def validate_doc(page: "TestCacheInvalidation.GoogleDocPage") -> bool:
            # Mock validation - check if revision is "current"
            return page.revision == "current"

        page_cache.register_validator(self.GoogleDocPage, validate_doc)

        # Note: We don't test internal storage details, just that validation works

    def test_invalidate_page_by_uri(self, page_cache: PageCache) -> None:
        """Test invalidating a specific page by URI."""
        # Store a page
        doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="doc", id="doc1", version=1),
            title="Test Doc",
            content="Test content",
            revision="current",
        )
        page_cache.store(doc)

        # Verify page exists and is valid
        retrieved = page_cache.get(self.GoogleDocPage, doc.uri)
        assert retrieved is not None

        # Invalidate the page
        result = page_cache.invalidate(doc.uri)
        assert result is True

        # Verify page is now invalid
        retrieved = page_cache.get(self.GoogleDocPage, doc.uri)
        assert retrieved is None

    def test_page_validation_with_invalidator(self, page_cache: PageCache) -> None:
        """Test that pages are validated using registered invalidators."""

        def validate_doc(page: "TestCacheInvalidation.GoogleDocPage") -> bool:
            # Mock validation - only "current" revision is valid
            return page.revision == "current"

        page_cache.register_validator(self.GoogleDocPage, validate_doc)

        # Store a page with "current" revision
        doc_current = self.GoogleDocPage(
            uri=PageURI(root="test", type="doc", id="doc1", version=1),
            title="Current Doc",
            content="Current content",
            revision="current",
        )
        page_cache.store(doc_current)

        # Store a page with "old" revision
        doc_old = self.GoogleDocPage(
            uri=PageURI(root="test", type="doc", id="doc2", version=1),
            title="Old Doc",
            content="Old content",
            revision="old",
        )
        page_cache.store(doc_old)

        # Current revision should be retrievable
        retrieved_current = page_cache.get(self.GoogleDocPage, doc_current.uri)
        assert retrieved_current is not None
        assert retrieved_current.title == "Current Doc"

        # Old revision should be invalidated and not retrievable
        retrieved_old = page_cache.get(self.GoogleDocPage, doc_old.uri)
        assert retrieved_old is None

    def test_ancestor_validation(self, page_cache: PageCache) -> None:
        """Test that ancestor pages are validated when retrieving child pages."""

        def validate_doc(page: "TestCacheInvalidation.GoogleDocPage") -> bool:
            return page.revision == "current"

        def validate_chunk(page: "TestCacheInvalidation.ChunkPage") -> bool:
            return page.doc_revision == "current"

        page_cache.register_validator(self.GoogleDocPage, validate_doc)
        page_cache.register_validator(self.ChunkPage, validate_chunk)

        # Store parent document with "current" revision
        parent_doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="doc", id="doc1", version=1),
            title="Parent Doc",
            content="Parent content",
            revision="current",
        )
        page_cache.store(parent_doc)

        # Store child chunk with "current" revision
        child_chunk = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=1),
            chunk_index=1,
            content="Chunk content",
            doc_revision="current",
            parent_uri=parent_doc.uri,
        )
        page_cache.store(child_chunk, parent_uri=parent_doc.uri)

        # Both should be retrievable initially
        retrieved_parent = page_cache.get(self.GoogleDocPage, parent_doc.uri)
        retrieved_child = page_cache.get(self.ChunkPage, child_chunk.uri)
        assert retrieved_parent is not None
        assert retrieved_child is not None

        # Now simulate parent document becoming invalid (revision changed)
        # We'll manually update the parent's revision to make it invalid
        updated_parent = self.GoogleDocPage(
            uri=PageURI(root="test", type="doc", id="doc1", version=2),
            title="Parent Doc Updated",
            content="Updated parent content",
            revision="old",  # This will make it invalid
        )
        page_cache.store(updated_parent)

        # Update the child to point to the new parent version
        updated_child = self.ChunkPage(
            uri=PageURI(root="test", type="chunk", id="chunk1", version=2),
            chunk_index=1,
            content="Chunk content",
            doc_revision="current",  # Child is still current
            parent_uri=updated_parent.uri,
        )
        page_cache.store(updated_child, parent_uri=updated_parent.uri)

        # The updated parent should be invalid
        retrieved_updated_parent = page_cache.get(
            self.GoogleDocPage, updated_parent.uri
        )
        assert retrieved_updated_parent is None

        # The child should also be invalid because its parent is invalid
        retrieved_updated_child = page_cache.get(self.ChunkPage, updated_child.uri)
        assert retrieved_updated_child is None

    def test_find_pages_respects_validity(self, page_cache: PageCache) -> None:
        """Test that find_pages_by_attribute only returns valid pages."""

        def validate_doc(page: "TestCacheInvalidation.GoogleDocPage") -> bool:
            return page.revision == "current"

        page_cache.register_validator(self.GoogleDocPage, validate_doc)

        # Store multiple documents with different revisions
        docs = [
            self.GoogleDocPage(
                uri=PageURI(root="test", type="doc", id="doc1", version=1),
                title="Current Doc 1",
                content="Content 1",
                revision="current",
            ),
            self.GoogleDocPage(
                uri=PageURI(root="test", type="doc", id="doc2", version=1),
                title="Current Doc 2",
                content="Content 2",
                revision="current",
            ),
            self.GoogleDocPage(
                uri=PageURI(root="test", type="doc", id="doc3", version=1),
                title="Old Doc 3",
                content="Content 3",
                revision="old",
            ),
        ]

        for doc in docs:
            page_cache.store(doc)

        # Find all documents with "Doc" in title
        results = (
            page_cache.find(self.GoogleDocPage)
            .where(lambda t: t.title.like("%Doc%"))
            .all()
        )

        # Should only return the 2 current documents, not the old one
        assert len(results) == 2
        titles = {r.title for r in results}
        assert titles == {"Current Doc 1", "Current Doc 2"}

    def test_no_invalidator_allows_all_pages(self, page_cache: PageCache) -> None:
        """Test that pages without invalidators are always considered valid."""
        # Store a page without registering an invalidator
        doc = self.GoogleDocPage(
            uri=PageURI(root="test", type="doc", id="doc1", version=1),
            title="Test Doc",
            content="Test content",
            revision="old",  # Would be invalid if invalidator was registered
        )
        page_cache.store(doc)

        # Should be retrievable since no invalidator is registered
        retrieved = page_cache.get(self.GoogleDocPage, doc.uri)
        assert retrieved is not None
        assert retrieved.title == "Test Doc"
