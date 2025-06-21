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
