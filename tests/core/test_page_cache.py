"""Tests for the PageCache class.

This module contains comprehensive tests for the PageCache functionality,
including page storage, retrieval, SqlAlchemy queries, and error handling.
"""

import tempfile
from datetime import datetime
from typing import Any, Optional

import pytest

from praga_core.page_cache import PageCache
from praga_core.types import Page, PageURI


def clear_global_registry() -> None:
    """Clear the global table registry and reset SQLAlchemy metadata.

    This function is used for testing to ensure clean state between test runs.
    """
    from praga_core.page_cache import _TABLE_REGISTRY, Base

    _TABLE_REGISTRY.clear()
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
        uri=PageURI(root="test", type="user", id="user1"),
        name="Test User",
        email="test@example.com",
        age=30,
    )


@pytest.fixture
def sample_post() -> PostPage:
    """Provide a sample post page."""
    return PostPage(
        uri=PageURI(root="test", type="post", id="post1"),
        title="Test Post",
        content="Test content for the post",
        author_email="test@example.com",
    )


@pytest.fixture
def sample_event() -> EventPage:
    """Provide a sample event page."""
    return EventPage(
        uri=PageURI(root="test", type="event", id="event1"),
        title="Test Event",
        start_time=datetime(2024, 1, 1, 10, 0),
        end_time=datetime(2024, 1, 1, 11, 0),
        location="Test Location",
    )


class TestPageCacheInitialization:
    """Test PageCache initialization."""

    def test_initialization(self, temp_db_url: str) -> None:
        """Test basic PageCache initialization."""
        cache = PageCache(temp_db_url)
        assert cache.engine is not None
        assert len(cache.registered_page_types) == 0

    def test_initialization_with_drop_previous(self, temp_db_url: str) -> None:
        """Test PageCache initialization with drop_previous=True."""
        cache = PageCache(temp_db_url, drop_previous=True)
        assert cache.engine is not None
        assert len(cache.registered_page_types) == 0


class TestPageTypeRegistration:
    """Test page type registration."""

    def test_register_single_page_type(self, page_cache: PageCache) -> None:
        """Test registering a single page type."""
        page_cache.register_page_type(UserPage)
        assert "UserPage" in page_cache.registered_page_types
        assert len(page_cache.registered_page_types) == 1

    def test_register_multiple_page_types(self, page_cache: PageCache) -> None:
        """Test registering multiple page types."""
        page_cache.register_page_type(UserPage)
        page_cache.register_page_type(PostPage)
        page_cache.register_page_type(EventPage)

        assert "UserPage" in page_cache.registered_page_types
        assert "PostPage" in page_cache.registered_page_types
        assert "EventPage" in page_cache.registered_page_types
        assert len(page_cache.registered_page_types) == 3

    def test_register_same_type_twice(self, page_cache: PageCache) -> None:
        """Test registering the same page type twice (should be idempotent)."""
        page_cache.register_page_type(UserPage)
        page_cache.register_page_type(UserPage)  # Register again

        assert "UserPage" in page_cache.registered_page_types
        assert len(page_cache.registered_page_types) == 1


class TestPageStorage:
    """Test page storage functionality."""

    def test_store_new_page(self, page_cache: PageCache, sample_user: UserPage) -> None:
        """Test storing a new page."""
        result = page_cache.store_page(sample_user)
        assert result is True  # Returns True for new pages

        # Verify page was stored
        stored_page = page_cache.get_page(UserPage, sample_user.uri)
        assert stored_page is not None
        assert stored_page.name == sample_user.name
        assert stored_page.email == sample_user.email
        assert stored_page.age == sample_user.age

    def test_store_duplicate_page(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test storing the same page twice."""
        # Store first time
        result1 = page_cache.store_page(sample_user)
        assert result1 is True

        # Store second time (should update)
        result2 = page_cache.store_page(sample_user)
        assert result2 is False  # Returns False for updates

    def test_update_existing_page(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test updating an existing page."""
        # Store initial page
        page_cache.store_page(sample_user)

        # Create updated version
        updated_user = UserPage(
            uri=sample_user.uri, name="Updated User", email=sample_user.email, age=31
        )

        # Store update
        result = page_cache.store_page(updated_user)
        assert result is False  # Returns False for updates

        # Verify update
        stored_page = page_cache.get_page(UserPage, sample_user.uri)
        assert stored_page is not None
        assert stored_page.name == "Updated User"
        assert stored_page.age == 31

    def test_store_pages_different_types(
        self, page_cache: PageCache, sample_user: UserPage, sample_post: PostPage
    ) -> None:
        """Test storing pages of different types."""
        result1 = page_cache.store_page(sample_user)
        result2 = page_cache.store_page(sample_post)

        assert result1 is True
        assert result2 is True

        # Verify both pages were stored
        stored_user = page_cache.get_page(UserPage, sample_user.uri)
        stored_post = page_cache.get_page(PostPage, sample_post.uri)

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
        page_cache.store_page(sample_user)

        retrieved_page = page_cache.get_page(UserPage, sample_user.uri)
        assert retrieved_page is not None
        assert retrieved_page.uri == sample_user.uri
        assert retrieved_page.name == sample_user.name
        assert retrieved_page.email == sample_user.email
        assert retrieved_page.age == sample_user.age

    def test_get_nonexistent_page(self, page_cache: PageCache) -> None:
        """Test retrieving a non-existent page."""
        nonexistent_uri = PageURI(root="test", type="user", id="nonexistent")
        result = page_cache.get_page(UserPage, nonexistent_uri)
        assert result is None

    def test_get_page_unregistered_type(self, page_cache: PageCache) -> None:
        """Test retrieving a page of unregistered type."""
        uri = PageURI(root="test", type="user", id="user1")
        result = page_cache.get_page(UserPage, uri)
        assert result is None


class TestSqlAlchemyQueries:
    """Test SqlAlchemy-style query functionality."""

    def test_find_by_exact_match(self, page_cache: PageCache) -> None:
        """Test finding pages by exact attribute match."""
        # Create and store multiple users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1"),
                name="John Doe",
                email="john@example.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2"),
                name="Jane Doe",
                email="jane@example.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3"),
                name="Bob Smith",
                email="bob@example.com",
                age=25,
            ),
        ]

        for user in users:
            page_cache.store_page(user)

        # Test exact name match
        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: t.name == "John Doe"
        )
        assert len(results) == 1
        assert results[0].name == "John Doe"

        # Test exact age match
        results = page_cache.find_pages_by_attribute(UserPage, lambda t: t.age == 30)
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"John Doe", "Jane Doe"}

    def test_find_by_like_pattern(self, page_cache: PageCache) -> None:
        """Test finding pages using LIKE patterns."""
        # Create and store multiple users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1"),
                name="John Doe",
                email="john@example.com",
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2"),
                name="Jane Doe",
                email="jane@example.com",
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3"),
                name="Bob Smith",
                email="bob@example.com",
            ),
        ]

        for user in users:
            page_cache.store_page(user)

        # Test LIKE pattern for names
        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: t.name.like("%Doe%")
        )
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"John Doe", "Jane Doe"}

        # Test case-insensitive LIKE (ilike)
        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: t.email.ilike("%EXAMPLE%")
        )
        assert len(results) == 3

    def test_find_by_complex_query(self, page_cache: PageCache) -> None:
        """Test finding pages using complex query expressions."""
        # Create and store multiple users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1"),
                name="John Doe",
                email="john@company.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2"),
                name="Jane Smith",
                email="jane@company.com",
                age=25,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3"),
                name="Bob Johnson",
                email="bob@personal.org",
                age=35,
            ),
        ]

        for user in users:
            page_cache.store_page(user)

        # Test complex AND query
        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: (t.age > 25) & (t.email.like("%@company.com"))
        )
        assert len(results) == 1
        assert results[0].name == "John Doe"

        # Test OR query
        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: (t.name.like("%Doe")) | (t.age == 35)
        )
        assert len(results) == 2
        names = {r.name for r in results}
        assert names == {"John Doe", "Bob Johnson"}

    def test_find_with_direct_table_reference(self, page_cache: PageCache) -> None:
        """Test finding pages using direct table reference."""
        # Store a user
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user1"),
            name="Test User",
            email="test@example.com",
        )
        page_cache.store_page(user)

        # Get table class and use direct reference
        table = page_cache._get_table_class(UserPage)
        results = page_cache.find_pages_by_attribute(
            UserPage, table.email == "test@example.com"
        )

        assert len(results) == 1
        assert results[0].name == "Test User"

    def test_find_no_results(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test finding pages with no matching results."""
        page_cache.store_page(sample_user)

        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: t.name == "Nonexistent"
        )
        assert len(results) == 0

    def test_find_unregistered_type(self, page_cache: PageCache) -> None:
        """Test finding pages of unregistered type."""
        results = page_cache.find_pages_by_attribute(
            UserPage, lambda t: t.name == "Test"
        )
        assert len(results) == 0


class TestDateTimeHandling:
    """Test datetime field handling."""

    def test_store_and_retrieve_datetime(
        self, page_cache: PageCache, sample_event: EventPage
    ) -> None:
        """Test storing and retrieving pages with datetime fields."""
        page_cache.store_page(sample_event)

        retrieved_event = page_cache.get_page(EventPage, sample_event.uri)
        assert retrieved_event is not None
        assert retrieved_event.start_time == sample_event.start_time
        assert retrieved_event.end_time == sample_event.end_time
        assert retrieved_event.location == sample_event.location

    def test_update_datetime_fields(
        self, page_cache: PageCache, sample_event: EventPage
    ) -> None:
        """Test updating datetime fields."""
        page_cache.store_page(sample_event)

        # Create updated event
        updated_event = EventPage(
            uri=sample_event.uri,
            title="Updated Event",
            start_time=datetime(2024, 1, 2, 14, 0),
            end_time=datetime(2024, 1, 2, 15, 0),
            location="New Location",
        )

        page_cache.store_page(updated_event)

        # Verify update
        retrieved_event = page_cache.get_page(EventPage, sample_event.uri)
        assert retrieved_event is not None
        assert retrieved_event.title == "Updated Event"
        assert retrieved_event.start_time == datetime(2024, 1, 2, 14, 0)
        assert retrieved_event.end_time == datetime(2024, 1, 2, 15, 0)
        assert retrieved_event.location == "New Location"

    def test_find_by_datetime(self, page_cache: PageCache) -> None:
        """Test finding pages by datetime values."""
        # Create events with different times
        events = [
            EventPage(
                uri=PageURI(root="test", type="event", id="event1"),
                title="Morning Event",
                start_time=datetime(2024, 1, 1, 10, 0),
                end_time=datetime(2024, 1, 1, 11, 0),
            ),
            EventPage(
                uri=PageURI(root="test", type="event", id="event2"),
                title="Afternoon Event",
                start_time=datetime(2024, 1, 1, 14, 0),
                end_time=datetime(2024, 1, 1, 15, 0),
            ),
        ]

        for event in events:
            page_cache.store_page(event)

        # Test exact datetime match
        results = page_cache.find_pages_by_attribute(
            EventPage, lambda t: t.start_time == datetime(2024, 1, 1, 10, 0)
        )
        assert len(results) == 1
        assert results[0].title == "Morning Event"

    def test_datetime_with_microseconds(self, page_cache: PageCache) -> None:
        """Test datetime fields with microseconds."""
        event = EventPage(
            uri=PageURI(root="test", type="event", id="event_micro"),
            title="Event with Microseconds",
            start_time=datetime(2024, 1, 1, 10, 0, 0, 123456),
            end_time=datetime(2024, 1, 1, 11, 0, 0, 789012),
        )

        page_cache.store_page(event)
        retrieved_event = page_cache.get_page(EventPage, event.uri)

        # Verify microseconds are preserved
        assert retrieved_event is not None
        assert retrieved_event.start_time == datetime(2024, 1, 1, 10, 0, 0, 123456)
        assert retrieved_event.end_time == datetime(2024, 1, 1, 11, 0, 0, 789012)


class TestOptionalFields:
    """Test handling of optional fields."""

    def test_store_page_with_none_values(self, page_cache: PageCache) -> None:
        """Test storing pages with None values in optional fields."""
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user_no_age"),
            name="User Without Age",
            email="noage@example.com",
            age=None,
        )

        page_cache.store_page(user)
        retrieved_user = page_cache.get_page(UserPage, user.uri)

        assert retrieved_user is not None
        assert retrieved_user.name == "User Without Age"
        assert retrieved_user.email == "noage@example.com"
        assert retrieved_user.age is None

    def test_update_optional_field_to_none(self, page_cache: PageCache) -> None:
        """Test updating an optional field to None."""
        # Store user with age
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user_age_change"),
            name="User",
            email="user@example.com",
            age=30,
        )
        page_cache.store_page(user)

        # Update age to None
        updated_user = UserPage(
            uri=user.uri, name="User", email="user@example.com", age=None
        )
        page_cache.store_page(updated_user)

        # Verify update
        retrieved_user = page_cache.get_page(UserPage, user.uri)
        assert retrieved_user is not None
        assert retrieved_user.age is None


class TestAdvancedQueries:
    """Test advanced query functionality."""

    def test_complex_query_with_direct_table_access(
        self, page_cache: PageCache
    ) -> None:
        """Test complex queries using direct table access."""
        # Store some users
        users = [
            UserPage(
                uri=PageURI(root="test", type="user", id="user1"),
                name="Alice",
                email="alice@example.com",
                age=25,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user2"),
                name="Bob",
                email="bob@example.com",
                age=30,
            ),
            UserPage(
                uri=PageURI(root="test", type="user", id="user3"),
                name="Charlie",
                email="charlie@example.com",
                age=35,
            ),
        ]

        for user in users:
            page_cache.store_page(user)

        # Use direct table access for complex queries
        table = page_cache._get_table_class(UserPage)

        # Find users with age between 25 and 30
        results = page_cache.find_pages_by_attribute(
            UserPage, (table.age >= 25) & (table.age <= 30)
        )

        assert len(results) == 2
        names = {user.name for user in results}
        assert names == {"Alice", "Bob"}

    def test_get_table_class_unregistered_type(self, page_cache: PageCache) -> None:
        """Test getting table class for unregistered page type."""
        with pytest.raises(ValueError, match="Page type UserPage not registered"):
            page_cache._get_table_class(UserPage)


class TestTableReuse:
    """Test table reuse across PageCache instances."""

    def test_multiple_cache_instances_reuse_tables(self, temp_db_url: str) -> None:
        """Test that multiple PageCache instances reuse the same table classes."""
        # Create first cache instance and register a type
        cache1 = PageCache(temp_db_url, drop_previous=True)
        cache1.register_page_type(UserPage)

        # Store a page
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user1"),
            name="Test User",
            email="test@example.com",
        )
        cache1.store_page(user)

        # Create second cache instance with same URL
        cache2 = PageCache(temp_db_url)
        cache2.register_page_type(UserPage)

        # Should be able to retrieve the page from second instance
        retrieved_user = cache2.get_page(UserPage, user.uri)
        assert retrieved_user is not None
        assert retrieved_user.name == "Test User"


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_get_table_class_unregistered_type(self, page_cache: PageCache) -> None:
        """Test getting table class for unregistered type."""
        with pytest.raises(ValueError, match="Page type UserPage not registered"):
            page_cache._get_table_class(UserPage)

    def test_get_table_class_registered_type(self, page_cache: PageCache) -> None:
        """Test getting table class for registered type."""
        page_cache.register_page_type(UserPage)
        table_class = page_cache._get_table_class(UserPage)
        assert table_class is not None
        assert hasattr(table_class, "uri")
        assert hasattr(table_class, "name")
        assert hasattr(table_class, "email")


class TestURIHandling:
    """Test URI handling as primary key."""

    def test_uri_as_primary_key(
        self, page_cache: PageCache, sample_user: UserPage
    ) -> None:
        """Test that URI is used as primary key."""
        page_cache.store_page(sample_user)

        # Try to store another page with same URI (should update)
        duplicate_user = UserPage(
            uri=sample_user.uri,  # Same URI
            name="Different Name",
            email="different@example.com",
        )

        result = page_cache.store_page(duplicate_user)
        assert result is False  # Should be update, not insert

        # Verify the page was updated
        retrieved_user = page_cache.get_page(UserPage, sample_user.uri)
        assert retrieved_user is not None
        assert retrieved_user.name == "Different Name"
        assert retrieved_user.email == "different@example.com"

    def test_different_uris_different_records(self, page_cache: PageCache) -> None:
        """Test that different URIs create different records."""
        user1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1"),
            name="User 1",
            email="user1@example.com",
        )
        user2 = UserPage(
            uri=PageURI(root="test", type="user", id="user2"),
            name="User 2",
            email="user2@example.com",
        )

        result1 = page_cache.store_page(user1)
        result2 = page_cache.store_page(user2)

        assert result1 is True  # New insert
        assert result2 is True  # New insert

        # Both should be retrievable
        retrieved_user1 = page_cache.get_page(UserPage, user1.uri)
        retrieved_user2 = page_cache.get_page(UserPage, user2.uri)

        assert retrieved_user1 is not None
        assert retrieved_user2 is not None
        assert retrieved_user1.name == "User 1"
        assert retrieved_user2.name == "User 2"


class TestPageURISerialization:
    """Test PageURI serialization and deserialization in page_cache."""

    def test_convert_page_uris_for_storage_single_uri(
        self, page_cache: PageCache
    ) -> None:
        """Test converting a single PageURI to string for storage."""
        uri = PageURI(root="test", type="doc", id="123")
        result = page_cache._convert_page_uris_for_storage(uri)
        assert result == str(uri)
        assert isinstance(result, str)

    def test_convert_page_uris_for_storage_list_of_uris(
        self, page_cache: PageCache
    ) -> None:
        """Test converting a list of PageURIs to strings for storage."""
        uris = [
            PageURI(root="test", type="doc", id="123"),
            PageURI(root="test", type="doc", id="456"),
        ]
        result = page_cache._convert_page_uris_for_storage(uris)
        expected = [str(uri) for uri in uris]
        assert result == expected
        assert all(isinstance(item, str) for item in result)

    def test_convert_page_uris_for_storage_nested_structure(
        self, page_cache: PageCache
    ) -> None:
        """Test converting nested structures containing PageURIs."""
        uri1 = PageURI(root="test", type="doc", id="123")
        uri2 = PageURI(root="test", type="doc", id="456")

        nested_data = {
            "single_uri": uri1,
            "uri_list": [uri1, uri2],
            "regular_data": "some string",
            "number": 42,
        }

        result = page_cache._convert_page_uris_for_storage(nested_data)

        assert result["single_uri"] == str(uri1)
        assert result["uri_list"] == [str(uri1), str(uri2)]
        assert result["regular_data"] == "some string"
        assert result["number"] == 42

    def test_convert_page_uris_for_storage_non_uri_values(
        self, page_cache: PageCache
    ) -> None:
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
            result = page_cache._convert_page_uris_for_storage(value)
            assert result == value

    def test_convert_page_uris_from_storage_single_uri(
        self, page_cache: PageCache
    ) -> None:
        """Test converting a string back to PageURI from storage."""
        from praga_core.types import PageURI

        uri_string = "test/doc:123@1"
        result = page_cache._convert_page_uris_from_storage(uri_string, PageURI)

        assert isinstance(result, PageURI)
        assert result.root == "test"
        assert result.type == "doc"
        assert result.id == "123"

    def test_convert_page_uris_from_storage_optional_uri(
        self, page_cache: PageCache
    ) -> None:
        """Test converting Optional[PageURI] from storage."""
        from typing import Optional

        from praga_core.types import PageURI

        # Test with actual URI string
        uri_string = "test/doc:123@1"
        result = page_cache._convert_page_uris_from_storage(
            uri_string, Optional[PageURI]
        )
        assert isinstance(result, PageURI)

        # Test with None
        result_none = page_cache._convert_page_uris_from_storage(
            None, Optional[PageURI]
        )
        assert result_none is None

    def test_convert_page_uris_from_storage_list_of_uris(
        self, page_cache: PageCache
    ) -> None:
        """Test converting List[PageURI] from storage."""
        from typing import List

        from praga_core.types import PageURI

        uri_strings = ["test/doc:123@1", "test/doc:456@1"]
        result = page_cache._convert_page_uris_from_storage(uri_strings, List[PageURI])

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(isinstance(uri, PageURI) for uri in result)
        assert result[0].id == "123"
        assert result[1].id == "456"

    def test_convert_page_uris_from_storage_non_uri_types(
        self, page_cache: PageCache
    ) -> None:
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
            result = page_cache._convert_page_uris_from_storage(value, field_type)
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
            uri=PageURI(root="test", type="document", id="doc1"),
            title="Test Document",
            content="This is test content for the document",
            author_uri=PageURI(root="test", type="user", id="author1"),
            related_docs=[
                PageURI(root="test", type="document", id="related1"),
                PageURI(root="test", type="document", id="related2"),
            ],
            parent_doc=PageURI(root="test", type="document", id="parent1"),
        )

    def test_store_and_retrieve_page_with_page_uris(
        self,
        page_cache: PageCache,
        sample_document_with_uris: "TestPageWithPageURIFields.DocumentPage",
    ) -> None:
        """Test storing and retrieving a page with PageURI fields."""
        # Store the document
        result = page_cache.store_page(sample_document_with_uris)
        assert result is True

        # Retrieve the document
        retrieved_doc = page_cache.get_page(
            self.DocumentPage, sample_document_with_uris.uri
        )

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
            uri=PageURI(root="test", type="document", id="doc2"),
            title="Document Without URIs",
            content="Content without related URIs",
            author_uri=None,
            related_docs=[],
            parent_doc=None,
        )

        # Store the document
        result = page_cache.store_page(doc)
        assert result is True

        # Retrieve the document
        retrieved_doc = page_cache.get_page(self.DocumentPage, doc.uri)

        assert retrieved_doc is not None
        assert retrieved_doc.title == "Document Without URIs"
        assert retrieved_doc.author_uri is None
        assert retrieved_doc.related_docs == []
        assert retrieved_doc.parent_doc is None

    def test_update_page_with_page_uris(
        self,
        page_cache: PageCache,
        sample_document_with_uris: "TestPageWithPageURIFields.DocumentPage",
    ) -> None:
        """Test updating a page with PageURI fields."""
        # Store initial document
        page_cache.store_page(sample_document_with_uris)

        # Create updated version
        updated_doc = self.DocumentPage(
            uri=sample_document_with_uris.uri,  # Same URI
            title="Updated Document",
            content="Updated content",
            author_uri=PageURI(root="test", type="user", id="new_author"),
            related_docs=[
                PageURI(root="test", type="document", id="new_related1"),
            ],
            parent_doc=None,  # Changed to None
        )

        # Update the document
        result = page_cache.store_page(updated_doc)
        assert result is False  # Should be update, not insert

        # Retrieve and verify
        retrieved_doc = page_cache.get_page(self.DocumentPage, updated_doc.uri)

        assert retrieved_doc is not None
        assert retrieved_doc.title == "Updated Document"
        assert retrieved_doc.author_uri.id == "new_author"
        assert len(retrieved_doc.related_docs) == 1
        assert retrieved_doc.related_docs[0].id == "new_related1"
        assert retrieved_doc.parent_doc is None

    def test_find_pages_by_page_uri_fields(self, page_cache: PageCache) -> None:
        """Test finding pages by PageURI field values."""
        # Create documents with specific author
        author_uri = PageURI(root="test", type="user", id="author123")

        doc1 = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc1"),
            title="Document 1",
            content="Content 1",
            author_uri=author_uri,
        )

        doc2 = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc2"),
            title="Document 2",
            content="Content 2",
            author_uri=author_uri,
        )

        doc3 = self.DocumentPage(
            uri=PageURI(root="test", type="document", id="doc3"),
            title="Document 3",
            content="Content 3",
            author_uri=PageURI(root="test", type="user", id="different_author"),
        )

        # Store all documents
        page_cache.store_page(doc1)
        page_cache.store_page(doc2)
        page_cache.store_page(doc3)

        # Find documents by author_uri (note: stored as string in DB)
        results = page_cache.find_pages_by_attribute(
            self.DocumentPage, lambda t: t.author_uri == str(author_uri)
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
            PageURI(root="google", type="gdoc_chunk", id=f"{document_id}(0)"),
            PageURI(root="google", type="gdoc_chunk", id=f"{document_id}(1)"),
            PageURI(root="google", type="gdoc_chunk", id=f"{document_id}(2)"),
        ]

        # Create header with chunk URIs
        header = self.GDocHeader(
            uri=PageURI(root="google", type="gdoc_header", id=document_id),
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
        page_cache.store_page(header)
        for chunk in chunks:
            page_cache.store_page(chunk)

        # Retrieve and verify header
        retrieved_header = page_cache.get_page(self.GDocHeader, header.uri)
        assert retrieved_header is not None
        assert retrieved_header.title == "Test Google Doc"
        assert len(retrieved_header.chunk_uris) == 3
        assert all(isinstance(uri, PageURI) for uri in retrieved_header.chunk_uris)

        # Retrieve and verify chunks
        for i, chunk_uri in enumerate(chunk_uris):
            retrieved_chunk = page_cache.get_page(self.GDocChunk, chunk_uri)
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
                uri=PageURI(root="google", type="gdoc_chunk", id=f"{document_id}({i})"),
                document_id=document_id,
                chunk_index=i,
                content=f"Chunk {i} content",
                header_uri=PageURI(root="google", type="gdoc_header", id=document_id),
            )
            chunks.append(chunk)
            page_cache.store_page(chunk)

        # Find all chunks for this document
        results = page_cache.find_pages_by_attribute(
            self.GDocChunk, lambda t: t.document_id == document_id
        )

        assert len(results) == 3
        chunk_indices = {chunk.chunk_index for chunk in results}
        assert chunk_indices == {0, 1, 2}


class TestPageCacheLatestVersionFunctionality:
    """Test latest version functionality in PageCache."""

    def test_store_page_with_latest_version_uri(self, page_cache: PageCache) -> None:
        """Test storing a page with latest version URI and retrieving it."""
        # Create page with latest version URI
        user = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=-1),
            name="Test User",
            email="test@example.com",
            age=30,
        )
        
        page_cache.store_page(user)

        # Should be able to retrieve by same URI
        retrieved = page_cache.get_page(UserPage, user.uri)
        assert retrieved is not None
        assert retrieved.name == "Test User"

    def test_store_page_with_specific_version_updates_latest_tracking(self, page_cache: PageCache) -> None:
        """Test that storing pages with specific versions updates latest version tracking."""
        from praga_core.types import LATEST_VERSION
        
        # Store page with version 1
        user_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User v1",
            email="test@example.com",
        )
        page_cache.store_page(user_v1)

        # Check latest version
        latest_version = page_cache.get_latest_version(user_v1.uri)
        assert latest_version == 1

        # Store page with version 3 (skipping 2)
        user_v3 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=3),
            name="User v3",
            email="test@example.com",
        )
        page_cache.store_page(user_v3)

        # Latest version should now be 3
        latest_version = page_cache.get_latest_version(user_v3.uri)
        assert latest_version == 3

        # Request latest version should return v3
        latest_uri = PageURI(root="test", type="user", id="user1", version=LATEST_VERSION)
        retrieved = page_cache.get_page(UserPage, latest_uri)
        assert retrieved is not None
        assert retrieved.name == "User v3"

    def test_get_latest_version_for_nonexistent_page(self, page_cache: PageCache) -> None:
        """Test getting latest version for a page that doesn't exist."""
        uri = PageURI(root="test", type="user", id="nonexistent")
        latest_version = page_cache.get_latest_version(uri)
        assert latest_version is None

    def test_retrieve_latest_version_with_explicit_latest_uri(self, page_cache: PageCache) -> None:
        """Test retrieving latest version using explicit latest version URI."""
        from praga_core.types import LATEST_VERSION
        
        # Store multiple versions
        user_v1 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=1),
            name="User v1",
            email="test@example.com",
        )
        user_v2 = UserPage(
            uri=PageURI(root="test", type="user", id="user1", version=2),
            name="User v2",
            email="test@example.com",
        )
        
        page_cache.store_page(user_v1)
        page_cache.store_page(user_v2)

        # Request latest version explicitly
        latest_uri = PageURI(root="test", type="user", id="user1", version=LATEST_VERSION)
        retrieved = page_cache.get_page(UserPage, latest_uri)
        
        assert retrieved is not None
        assert retrieved.name == "User v2"  # Should get version 2
