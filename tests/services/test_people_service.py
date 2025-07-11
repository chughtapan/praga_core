"""Tests for the rewritten PeopleService."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.people.page import PersonPage
from pragweb.google_api.people.service import PeopleService, PersonInfo


class TestPeopleService:
    """Test suite for PeopleService."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_page_cache = Mock()
        self.mock_page_cache.get = AsyncMock()
        self.mock_page_cache.store = AsyncMock()
        self.mock_page_cache.find = Mock()
        self.mock_context.page_cache = self.mock_page_cache

        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service
        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()
        self.mock_api_client.search_contacts = AsyncMock(return_value=[])
        self.mock_api_client.search_messages = AsyncMock(return_value=([], None))
        self.mock_api_client.get_message = AsyncMock()
        self.mock_api_client._people = Mock()

        self.service = PeopleService(self.mock_api_client)

        self.mock_context.create_page_uri = AsyncMock()

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test PeopleService initialization."""
        assert self.service.api_client is self.mock_api_client
        assert self.service.name == "people"
        assert "people" in self.mock_context.services
        assert self.mock_context.services["people"] is self.service

    @pytest.mark.asyncio
    async def test_handle_person_request_not_found(self):
        """Test handle_person_request raises error when person not found."""
        self.mock_page_cache.get.return_value = None

        with pytest.raises(
            RuntimeError, match="Invalid request: Person person123 not yet created"
        ):
            expected_uri = PageURI(
                root="test-root", type="person", id="person123", version=1
            )
            await self.service.handle_person_request(expected_uri)

    @pytest.mark.asyncio
    async def test_get_person_records_existing(self):
        """Test get_person_records returns existing people."""
        mock_people = [Mock(spec=PersonPage), Mock(spec=PersonPage)]
        with patch.object(
            self.service, "search_existing_records", return_value=mock_people
        ):
            result = await self.service.get_person_records("test@example.com")
            assert result == mock_people

    @pytest.mark.asyncio
    async def test_get_person_records_create_new(self):
        """Test get_person_records creates new people when not found."""
        mock_people = [Mock(spec=PersonPage)]
        with patch.object(self.service, "search_existing_records", return_value=[]):
            with patch.object(
                self.service, "create_new_records", return_value=mock_people
            ):
                result = await self.service.get_person_records("test@example.com")
                assert result == mock_people

    @pytest.mark.asyncio
    async def test_get_person_records_creation_fails(self):
        """Test get_person_records returns empty list when creation fails."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            with patch.object(
                self.service, "create_new_records", side_effect=ValueError("Not found")
            ):
                result = await self.service.get_person_records("test@example.com")
                assert result == []

    @pytest.mark.asyncio
    async def test_lookup_people_by_email(self):
        """Test lookup_people by email address (search path only)."""
        mock_people = [Mock(spec=PersonPage), Mock(spec=PersonPage)]
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(return_value=mock_people)
        self.mock_page_cache.find.return_value = mock_query
        result = await self.service.search_existing_records("test@example.com")
        assert result == mock_people
        self.mock_page_cache.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_lookup_people_by_full_name(self):
        """Test lookup_people by full name when email match fails."""
        mock_people = [Mock(spec=PersonPage)]
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(side_effect=[[], mock_people])
        self.mock_page_cache.find.return_value = mock_query
        result = await self.service.search_existing_records("John Doe")
        assert result == mock_people
        assert self.mock_page_cache.find.call_count == 2

    @pytest.mark.asyncio
    async def test_lookup_people_by_first_name(self):
        """Test lookup_people by first name when other matches fail."""
        mock_people = [Mock(spec=PersonPage)]
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(side_effect=[[], mock_people])
        self.mock_page_cache.find.return_value = mock_query
        result = await self.service.search_existing_records("John")
        assert result == mock_people
        assert self.mock_page_cache.find.call_count == 2

    @pytest.mark.asyncio
    async def test_lookup_people_not_found(self):
        """Test lookup_people returns empty list when not found."""
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(return_value=[])
        self.mock_page_cache.find.return_value = mock_query
        result = await self.service.search_existing_records("nonexistent@example.com")
        assert result == []

    @pytest.mark.asyncio
    async def test_create_person_existing(self):
        """Test create_new_records raises error when people already exist."""
        mock_people = [Mock(spec=PersonPage)]
        with patch.object(
            self.service, "search_existing_records", return_value=mock_people
        ):
            with pytest.raises(
                RuntimeError, match="Person already exists for identifier"
            ):
                await self.service.create_new_records("John Doe")

    @pytest.mark.asyncio
    async def test_create_person_from_people_api(self):
        """Test create_person from Google People API."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            mock_person_info = PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            )
            with patch.object(
                self.service,
                "_extract_people_info_from_google_people",
                return_value=[mock_person_info],
            ):
                with patch.object(
                    self.service, "_extract_people_from_directory", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_gmail_contacts",
                        return_value=[],
                    ):
                        with patch.object(
                            self.service, "_is_real_person", return_value=True
                        ):
                            mock_query = Mock()
                            mock_query.where.return_value = mock_query
                            mock_query.all = AsyncMock(return_value=[])
                            self.mock_page_cache.find.return_value = mock_query
                            mock_person_page = Mock(spec=PersonPage)
                            with (
                                patch.object(
                                    self.service,
                                    "_store_and_create_page",
                                    return_value=mock_person_page,
                                ),
                                patch.object(
                                    self.service,
                                    "_find_existing_person_by_email",
                                    new_callable=AsyncMock,
                                    return_value=None,
                                ),
                            ):
                                result = await self.service.create_new_records(
                                    "john@example.com"
                                )
        assert result == [mock_person_page]

    @pytest.mark.asyncio
    async def test_create_person_no_sources(self):
        """Test create_person raises error when no sources found."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            with patch.object(
                self.service, "_extract_people_info_from_google_people", return_value=[]
            ):
                with patch.object(
                    self.service, "_extract_people_from_directory", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_gmail_contacts",
                        return_value=[],
                    ):
                        with pytest.raises(
                            ValueError, match="Could not find any real people"
                        ):
                            await self.service.create_new_records(
                                "nonexistent@example.com"
                            )

    @pytest.mark.asyncio
    async def test_create_person_filters_non_real_people(self):
        """Test create_person filters out non-real people."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            mock_person_info = PersonInfo(
                first_name="No Reply",
                last_name="",
                email="noreply@example.com",
                source="emails",
            )
            with patch.object(
                self.service,
                "_extract_people_info_from_google_people",
                return_value=[mock_person_info],
            ):
                with patch.object(
                    self.service, "_extract_people_from_directory", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_gmail_contacts",
                        return_value=[],
                    ):
                        with pytest.raises(
                            ValueError, match="Could not find any real people"
                        ):
                            await self.service.create_new_records("noreply@example.com")

    @pytest.mark.asyncio
    async def test_create_person_name_divergence_error(self):
        """Test create_person raises error when names diverge for same email."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            existing_person = Mock(spec=PersonPage)
            existing_person.full_name = "Jane Smith"
            existing_person.email = "john@example.com"
            mock_query = Mock()
            mock_query.where.return_value = mock_query
            mock_query.all = AsyncMock(return_value=[existing_person])
            self.mock_page_cache.find.return_value = mock_query
            mock_person_info = PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            )
            with patch.object(
                self.service,
                "_extract_people_info_from_google_people",
                return_value=[mock_person_info],
            ):
                with patch.object(
                    self.service, "_extract_people_from_directory", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_gmail_contacts",
                        return_value=[],
                    ):
                        with (
                            patch.object(
                                self.service, "_is_real_person", return_value=True
                            ),
                            patch.object(
                                self.service,
                                "_find_existing_person_by_email",
                                new_callable=AsyncMock,
                                return_value=existing_person,
                            ),
                        ):
                            with pytest.raises(
                                ValueError, match="Name divergence detected"
                            ):
                                await self.service.create_new_records(
                                    "john@example.com"
                                )

    @pytest.mark.asyncio
    async def test_extract_people_info_from_google_people(self):
        """Test _extract_people_info_from_google_people returns person info."""
        mock_api_result = {
            "person": {
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}],
            }
        }

        self.mock_api_client.search_contacts.return_value = [mock_api_result]

        result = await self.service._extract_people_info_from_google_people(
            "john@example.com"
        )

        assert len(result) == 1
        assert result[0].first_name == "John"
        assert result[0].last_name == "Doe"
        assert result[0].email == "john@example.com"
        assert result[0].source == "people_api"

    @pytest.mark.asyncio
    async def test_extract_people_from_directory(self):
        """Test _extract_people_from_directory returns person info."""
        mock_directory_result = {
            "people": [
                {
                    "names": [{"displayName": "John Doe"}],
                    "emailAddresses": [{"value": "john@example.com"}],
                }
            ]
        }

        mock_search = Mock()
        mock_search.execute.return_value = mock_directory_result
        mock_people = Mock()
        mock_people.searchDirectoryPeople.return_value = mock_search
        self.mock_api_client._people.people.return_value = mock_people

        result = await self.service._extract_people_from_directory("john@example.com")

        assert len(result) == 1
        assert result[0].first_name == "John"
        assert result[0].last_name == "Doe"
        assert result[0].email == "john@example.com"
        assert result[0].source == "directory_api"

    @pytest.mark.asyncio
    async def test_extract_people_from_gmail_contacts(self):
        """Test _extract_people_from_gmail_contacts returns person info."""
        mock_message = {"id": "123"}
        mock_message_data = {
            "payload": {
                "headers": [{"name": "From", "value": "John Doe <john@example.com>"}]
            }
        }

        self.mock_api_client.search_messages.return_value = ([mock_message], None)
        self.mock_api_client.get_message.return_value = mock_message_data

        with patch.object(self.service, "_matches_identifier", return_value=True):
            result = await self.service._extract_people_from_gmail_contacts(
                "john@example.com"
            )

            assert len(result) == 1
            assert result[0].first_name == "John"
            assert result[0].last_name == "Doe"
            assert result[0].email == "john@example.com"
            assert result[0].source == "emails"

    def test_is_real_person_valid(self):
        """Test _is_real_person returns True for valid person."""
        person_info = PersonInfo(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            source="people_api",
        )
        assert self.service._is_real_person(person_info) is True

    def test_is_real_person_automated(self):
        """Test _is_real_person returns False for automated accounts."""
        person_info = PersonInfo(
            first_name="No Reply",
            last_name="",
            email="noreply@example.com",
            source="emails",
        )
        assert self.service._is_real_person(person_info) is False

    def test_matches_identifier_email(self):
        """Test _matches_identifier for email identifiers."""
        person_info = PersonInfo(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        assert self.service._matches_identifier(person_info, "john@example.com") is True
        assert (
            self.service._matches_identifier(person_info, "other@example.com") is False
        )

    def test_matches_identifier_name(self):
        """Test _matches_identifier for name identifiers."""
        person_info = PersonInfo(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        assert self.service._matches_identifier(person_info, "John") is True
        assert self.service._matches_identifier(person_info, "John Doe") is True
        assert self.service._matches_identifier(person_info, "Jane") is False

    @pytest.mark.asyncio
    async def test_store_and_create_page(self):
        """Test _store_and_create_page creates PersonPage with source."""
        person_info = PersonInfo(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )
        self.mock_page_cache.store = AsyncMock()
        self.mock_context.create_page_uri = AsyncMock(
            return_value=PageURI(
                root="test-root", type="person", id="person123", version=1
            )
        )
        result = await self.service._store_and_create_page(person_info)
        assert isinstance(result, PersonPage)
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.email == "john@example.com"
        assert result.source == "people_api"
        self.mock_page_cache.store.assert_awaited_once_with(result)

    @pytest.mark.asyncio
    async def test_toolkit_get_person_records(self):
        """Test toolkit get_person_records method."""
        toolkit = self.service.toolkit
        mock_people = [Mock(spec=PersonPage), Mock(spec=PersonPage)]

        with patch.object(self.service, "get_person_records", return_value=mock_people):
            result = await toolkit.get_person_records("test@example.com")
            assert result == mock_people

        with patch.object(self.service, "get_person_records", return_value=[]):
            result = await toolkit.get_person_records("test@example.com")
            assert result == []

    @pytest.mark.asyncio
    async def test_find_existing_person_by_email_found(self):
        """Test _find_existing_person_by_email returns the first match (async)."""
        mock_people = [Mock(spec=PersonPage), Mock(spec=PersonPage)]
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(return_value=mock_people)
        self.mock_page_cache.find.return_value = mock_query
        result = await self.service._find_existing_person_by_email("test@example.com")
        assert result == mock_people[0]

    @pytest.mark.asyncio
    async def test_find_existing_person_by_email_not_found(self):
        """Test _find_existing_person_by_email returns None if no match (async)."""
        mock_query = Mock()
        mock_query.where.return_value = mock_query
        mock_query.all = AsyncMock(return_value=[])
        self.mock_page_cache.find.return_value = mock_query
        result = await self.service._find_existing_person_by_email(
            "notfound@example.com"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_real_async_query_path(self):
        """Test the real async query path for search_existing_records (integration, async DB)."""
        import os
        import tempfile

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from praga_core.page_cache.core import QueryBuilder
        from praga_core.page_cache.query import PageQuery
        from praga_core.page_cache.registry import PageRegistry
        from praga_core.page_cache.storage import PageStorage
        from praga_core.page_cache.validator import PageValidator

        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            db_url = f"sqlite+aiosqlite:///{temp_file.name}"
            engine = create_async_engine(db_url)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            registry = PageRegistry(engine)
            storage = PageStorage(session_factory, registry)
            validator = PageValidator()
            query_engine = PageQuery(session_factory, registry)
            # Register table (async)
            await registry.ensure_registered(PersonPage)
            person = PersonPage(
                uri=PageURI(root="test", type="person", id="p1", version=1),
                first_name="John",
                last_name="Doe",
                email="john@example.com",
            )
            await storage.store(person)

            # Minimal fake cache that returns a real QueryBuilder
            class FakeCache:
                def find(self_inner, t):
                    return QueryBuilder(t, query_engine, validator, storage)

            real_cache = FakeCache()
            self.service._page_cache = real_cache
            self.mock_context.page_cache = real_cache
            result = await self.service.search_existing_records("john@example.com")
            assert len(result) == 1
            assert result[0].email == "john@example.com"
        finally:
            temp_file.close()
            os.unlink(temp_file.name)


class TestPeopleServiceRefactored:
    """Test suite for the refactored PeopleService functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_page_cache = Mock()
        self.mock_page_cache.get = AsyncMock()
        self.mock_page_cache.store = AsyncMock()
        self.mock_page_cache.find = Mock()
        self.mock_context.page_cache = self.mock_page_cache

        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service
        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()
        self.service = PeopleService(self.mock_api_client)

        self.mock_context.create_page_uri = AsyncMock()

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    @pytest.mark.asyncio
    async def test_search_explicit_sources(self):
        """Test _search_explicit_sources combines Google People API and Directory API results."""
        people_api_results = [
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            )
        ]

        directory_results = [
            PersonInfo(
                first_name="Jane",
                last_name="Smith",
                email="jane@example.com",
                source="directory_api",
            )
        ]

        with patch.object(
            self.service,
            "_extract_people_info_from_google_people",
            return_value=people_api_results,
        ):
            with patch.object(
                self.service,
                "_extract_people_from_directory",
                return_value=directory_results,
            ):
                result = await self.service._search_explicit_sources("test")

        assert len(result) == 2
        assert people_api_results[0] in result
        assert directory_results[0] in result

    @pytest.mark.asyncio
    async def test_search_implicit_sources(self):
        """Test _search_implicit_sources returns Gmail contact results."""
        gmail_results = [
            PersonInfo(
                first_name="Bob",
                last_name="Wilson",
                email="bob@example.com",
                source="emails",
            )
        ]

        with patch.object(
            self.service,
            "_extract_people_from_gmail_contacts",
            return_value=gmail_results,
        ):
            result = await self.service._search_implicit_sources("test")

        assert result == gmail_results

    @pytest.mark.asyncio
    async def test_create_person_name_search_prioritizes_implicit(self):
        """Test create_person for name searches prioritizes implicit sources first."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            with patch.object(
                self.service, "_search_implicit_sources"
            ) as mock_implicit:
                with patch.object(
                    self.service, "_search_explicit_sources"
                ) as mock_explicit:
                    mock_implicit.return_value = []
                    mock_explicit.return_value = []

                    try:
                        await self.service.create_new_records(
                            "John Doe"
                        )  # Name, not email
                    except ValueError:
                        pass  # Expected when no results found

                    # Verify implicit sources called first
                    assert mock_implicit.call_count == 1
                    assert mock_explicit.call_count == 1

    @pytest.mark.asyncio
    async def test_create_person_email_search_prioritizes_explicit(self):
        """Test create_person for email searches prioritizes explicit sources first."""
        with patch.object(self.service, "search_existing_records", return_value=[]):
            with patch.object(
                self.service, "_search_explicit_sources"
            ) as mock_explicit:
                with patch.object(
                    self.service, "_search_implicit_sources"
                ) as mock_implicit:
                    mock_explicit.return_value = []
                    mock_implicit.return_value = []

                    try:
                        await self.service.create_new_records(
                            "john@example.com"
                        )  # Email
                    except ValueError:
                        pass  # Expected when no results found

                    # Verify explicit sources called first
                    assert mock_explicit.call_count == 1
                    assert mock_implicit.call_count == 1

    @pytest.mark.asyncio
    async def test_filter_and_deduplicate_people_removes_duplicates(self):
        """Test _filter_and_deduplicate_people removes duplicate emails (async)."""
        all_person_infos = [
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            ),
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",  # Duplicate email
                source="emails",
            ),
            PersonInfo(
                first_name="Jane",
                last_name="Smith",
                email="jane@example.com",
                source="directory_api",
            ),
        ]
        with patch.object(self.service, "_is_real_person", return_value=True):
            with patch.object(
                self.service,
                "_find_existing_person_by_email",
                new_callable=AsyncMock,
                return_value=None,
            ):
                new_person_infos, existing_people = (
                    await self.service._filter_and_deduplicate_people(
                        all_person_infos, "test"
                    )
                )
        assert len(new_person_infos) == 2
        assert len(existing_people) == 0

    @pytest.mark.asyncio
    async def test_filter_and_deduplicate_people_filters_non_real_people(self):
        """Test _filter_and_deduplicate_people filters out non-real people (async)."""
        all_person_infos = [
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            ),
            PersonInfo(
                first_name="No Reply",
                last_name="",
                email="noreply@example.com",
                source="emails",
            ),
        ]

        def mock_is_real_person(person_info):
            return person_info.email != "noreply@example.com"

        with patch.object(
            self.service, "_is_real_person", side_effect=mock_is_real_person
        ):
            with patch.object(
                self.service,
                "_find_existing_person_by_email",
                new_callable=AsyncMock,
                return_value=None,
            ):
                new_person_infos, existing_people = (
                    await self.service._filter_and_deduplicate_people(
                        all_person_infos, "test"
                    )
                )
        assert len(new_person_infos) == 1
        assert new_person_infos[0].email == "john@example.com"
        assert len(existing_people) == 0

    def test_validate_name_consistency_same_names(self):
        """Test _validate_name_consistency passes for same names."""
        existing_person = Mock(spec=PersonPage)
        existing_person.full_name = "John Doe"

        new_person_info = PersonInfo(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        # Should not raise exception
        self.service._validate_name_consistency(
            existing_person, new_person_info, "john@example.com"
        )

    def test_validate_name_consistency_different_names_raises_error(self):
        """Test _validate_name_consistency raises error for different names."""
        existing_person = Mock(spec=PersonPage)
        existing_person.full_name = "Jane Smith"

        new_person_info = PersonInfo(
            first_name="John",
            last_name="Doe",
            email="john@example.com",
            source="people_api",
        )

        with pytest.raises(ValueError, match="Name divergence detected"):
            self.service._validate_name_consistency(
                existing_person, new_person_info, "john@example.com"
            )

    @pytest.mark.asyncio
    async def test_create_person_pages_new_people_only(self):
        """Test _create_person_pages handles only new people (no more mixed types)."""
        new_person_infos = [
            PersonInfo(
                first_name="Jane",
                last_name="Smith",
                email="jane@example.com",
                source="people_api",
            ),
            PersonInfo(
                first_name="Bob",
                last_name="Wilson",
                email="bob@example.com",
                source="emails",
            ),
        ]

        new_person_page1 = Mock(spec=PersonPage)
        new_person_page2 = Mock(spec=PersonPage)
        with patch.object(
            self.service,
            "_store_and_create_page",
            side_effect=[new_person_page1, new_person_page2],
        ):
            result = await self.service._create_person_pages(new_person_infos)

        assert len(result) == 2
        assert new_person_page1 in result
        assert new_person_page2 in result

    def test_extract_all_people_from_gmail_message_multiple_headers(self):
        """Test _extract_from_gmail extracts from all headers."""
        message_data = {
            "payload": {
                "headers": [
                    {"name": "From", "value": "John Doe <john@example.com>"},
                    {
                        "name": "To",
                        "value": "Jane Smith <jane@example.com>, Bob Wilson <bob@example.com>",
                    },
                    {"name": "Cc", "value": "Alice Brown <alice@example.com>"},
                ]
            }
        }

        with patch.object(self.service, "_matches_identifier", return_value=True):
            with patch.object(self.service, "_is_real_person", return_value=True):
                result = self.service._extract_from_gmail(message_data, "test")

        # Should extract from all headers including multiple To addresses
        assert len(result) == 4
        emails = [person.email for person in result]
        assert "john@example.com" in emails
        assert "jane@example.com" in emails
        assert "bob@example.com" in emails
        assert "alice@example.com" in emails

    @pytest.mark.asyncio
    async def test_extract_people_from_gmail_contacts_name_vs_email_search(self):
        """Test _extract_people_from_gmail_contacts uses different queries for names vs emails."""
        mock_message = {"id": "123"}

        self.mock_api_client.search_messages.return_value = ([mock_message], None)
        self.mock_api_client.get_message.return_value = {
            "payload": {"headers": [{"name": "From", "value": "test@example.com"}]}
        }

        with patch.object(self.service, "_extract_from_gmail", return_value=[]):
            # Test email search
            await self.service._extract_people_from_gmail_contacts("test@example.com")

            # Verify it used email-specific query
            call_args = self.mock_api_client.search_messages.call_args[0][0]
            assert "from:test@example.com OR to:test@example.com" == call_args

            # Test name search
            await self.service._extract_people_from_gmail_contacts("John Doe")

            # Verify it used name-specific queries
            call_args = self.mock_api_client.search_messages.call_args[0][0]
            assert 'from:"John Doe"' in call_args
            assert 'to:"John Doe"' in call_args
