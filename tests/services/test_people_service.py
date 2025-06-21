"""Tests for existing PeopleService before refactoring."""

from unittest.mock import Mock, patch

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.pages.person import PersonPage
from pragweb.google_api.services.people_service import PeopleService


class TestPeopleService:
    """Test suite for PeopleService."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_page_cache = Mock()
        self.mock_context.page_cache = self.mock_page_cache
        set_global_context(self.mock_context)

        # Create mock services
        self.mock_people_service = Mock()
        self.mock_gmail_service = Mock()
        self.mock_calendar_service = Mock()
        self.mock_auth_manager = Mock()
        self.mock_auth_manager.get_people_service.return_value = (
            self.mock_people_service
        )
        self.mock_auth_manager.get_gmail_service.return_value = self.mock_gmail_service
        self.mock_auth_manager.get_calendar_service.return_value = (
            self.mock_calendar_service
        )

        with patch(
            "pragweb.google_api.services.people_service.GoogleAuthManager"
        ) as mock_auth_class:
            mock_auth_class.return_value = self.mock_auth_manager
            self.service = PeopleService()

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test PeopleService initialization."""
        assert self.service.auth_manager is self.mock_auth_manager
        assert self.service.people_service is self.mock_people_service
        assert self.service.gmail_service is self.mock_gmail_service
        assert self.service.calendar_service is self.mock_calendar_service
        assert self.service.name == "person"

        # Verify handler registration
        self.mock_context.register_handler.assert_called_once_with(
            "person", self.service.handle_person_request
        )

    def test_root_property(self):
        """Test root property returns context root."""
        assert self.service.root == "test-root"

    def test_handle_person_request_cached(self):
        """Test handle_person_request returns cached person."""
        mock_person = Mock(spec=PersonPage)
        self.mock_page_cache.get_page.return_value = mock_person

        result = self.service.handle_person_request("person123")

        # Verify cache lookup
        expected_uri = PageURI(root="test-root", type="person", id="person123")
        self.mock_page_cache.get_page.assert_called_once_with(PersonPage, expected_uri)
        assert result is mock_person

    def test_handle_person_request_not_found(self):
        """Test handle_person_request raises error when person not found."""
        self.mock_page_cache.get_page.return_value = None

        with pytest.raises(
            RuntimeError, match="Invalid request: Person person123 not found"
        ):
            self.service.handle_person_request("person123")

    def test_lookup_people_by_email(self):
        """Test lookup_people by email address."""
        mock_people = [Mock(spec=PersonPage), Mock(spec=PersonPage)]
        self.mock_page_cache.find_pages_by_attribute.return_value = mock_people

        result = self.service.lookup_people("test@example.com")

        # Should match by email first (most specific)
        self.mock_page_cache.find_pages_by_attribute.assert_called_once()
        call_args = self.mock_page_cache.find_pages_by_attribute.call_args
        assert call_args[0][0] == PersonPage
        # Test the lambda function matches email
        lambda_func = call_args[0][1]
        mock_person_attrs = Mock()
        mock_person_attrs.email = "test@example.com"
        assert lambda_func(mock_person_attrs) is True

        assert result == mock_people

    def test_lookup_people_by_full_name(self):
        """Test lookup_people by full name when email match fails."""
        # First call (email) returns empty, second call (full name) returns results
        self.mock_page_cache.find_pages_by_attribute.side_effect = [
            [],
            [Mock(spec=PersonPage)],
        ]

        result = self.service.lookup_people("John Doe")

        # Should try email first, then full name
        assert self.mock_page_cache.find_pages_by_attribute.call_count == 2
        assert len(result) == 1

    def test_lookup_people_by_first_name(self):
        """Test lookup_people by first name when other matches fail."""
        # Email and full name return empty, first name returns results
        mock_people = [Mock(spec=PersonPage)]
        self.mock_page_cache.find_pages_by_attribute.side_effect = [[], [], mock_people]

        result = self.service.lookup_people("John")

        # Should try email, full name, then first name
        assert self.mock_page_cache.find_pages_by_attribute.call_count == 3
        assert result == mock_people

    def test_create_person_existing(self):
        """Test create_person returns existing people if found."""
        mock_people = [Mock(spec=PersonPage)]
        with patch.object(self.service, "lookup_people", return_value=mock_people):
            result = self.service.create_person("John Doe")

        assert result == mock_people

    def test_create_person_new_from_google_people(self):
        """Test create_person from Google People API."""
        # No existing people
        with patch.object(self.service, "lookup_people", return_value=[]):
            # Mock Google People API response
            with patch.object(
                self.service, "_extract_people_info_from_google_people"
            ) as mock_google_people:
                with patch.object(
                    self.service, "_extract_people_from_gmail_contacts", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_calendar_contacts",
                        return_value=[],
                    ):
                        mock_person_info = {
                            "first_name": "John",
                            "last_name": "Doe",
                            "email": "john@example.com",
                            "source": "google_people",
                        }
                        mock_google_people.return_value = [mock_person_info]

                        # Mock _is_real_person and _store_and_create_page
                        with patch.object(
                            self.service, "_is_real_person", return_value=True
                        ):
                            with patch.object(
                                self.service,
                                "_get_existing_person_by_email",
                                return_value=None,
                            ):
                                mock_person_page = Mock(spec=PersonPage)
                                with patch.object(
                                    self.service,
                                    "_store_and_create_page",
                                    return_value=mock_person_page,
                                ):
                                    result = self.service.create_person(
                                        "john@example.com"
                                    )

        assert result == [mock_person_page]

    def test_create_person_no_sources(self):
        """Test create_person raises error when no sources found."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            with patch.object(
                self.service, "_extract_people_info_from_google_people", return_value=[]
            ):
                with patch.object(
                    self.service, "_extract_people_from_gmail_contacts", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_calendar_contacts",
                        return_value=[],
                    ):
                        with pytest.raises(
                            ValueError, match="Could not find any real people"
                        ):
                            self.service.create_person("nonexistent@example.com")

    def test_create_person_filters_non_real_people(self):
        """Test create_person filters out non-real people."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            mock_person_info = {
                "first_name": "No Reply",
                "last_name": "",
                "email": "noreply@example.com",
                "source": "gmail",
            }
            with patch.object(
                self.service,
                "_extract_people_info_from_google_people",
                return_value=[mock_person_info],
            ):
                with patch.object(
                    self.service, "_extract_people_from_gmail_contacts", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_calendar_contacts",
                        return_value=[],
                    ):
                        with patch.object(
                            self.service, "_is_real_person", return_value=False
                        ):
                            with pytest.raises(
                                ValueError, match="Could not find any real people"
                            ):
                                self.service.create_person("noreply@example.com")

    def test_create_person_name_divergence_error(self):
        """Test create_person raises error on name divergence."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            mock_person_info = {
                "first_name": "John",
                "last_name": "Smith",
                "email": "john@example.com",
                "source": "gmail",
            }
            # Mock existing person with different name
            mock_existing_person = Mock(spec=PersonPage)
            mock_existing_person.full_name = "John Doe"

            with patch.object(
                self.service,
                "_extract_people_info_from_google_people",
                return_value=[mock_person_info],
            ):
                with patch.object(
                    self.service, "_extract_people_from_gmail_contacts", return_value=[]
                ):
                    with patch.object(
                        self.service,
                        "_extract_people_from_calendar_contacts",
                        return_value=[],
                    ):
                        with patch.object(
                            self.service, "_is_real_person", return_value=True
                        ):
                            with patch.object(
                                self.service,
                                "_get_existing_person_by_email",
                                return_value=mock_existing_person,
                            ):
                                with pytest.raises(
                                    ValueError, match="Name divergence detected"
                                ):
                                    self.service.create_person("john@example.com")

    def test_is_real_person_valid(self):
        """Test _is_real_person identifies valid people."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "source": "gmail",
        }

        result = self.service._is_real_person(person_info)
        assert result is True

    def test_is_real_person_automated_email(self):
        """Test _is_real_person filters automated emails."""
        automated_cases = [
            {"first_name": "No Reply", "last_name": "", "email": "noreply@example.com"},
            {"first_name": "", "last_name": "", "email": "donotreply@example.com"},
            {"first_name": "Support", "last_name": "", "email": "support@example.com"},
            {"first_name": "Admin", "last_name": "", "email": "admin@example.com"},
        ]

        for case in automated_cases:
            case["source"] = "test"
            result = self.service._is_real_person(case)
            assert result is False, f"Should filter out {case['email']}"

    def test_get_existing_person_by_email(self):
        """Test _get_existing_person_by_email."""
        mock_people = [Mock(spec=PersonPage)]
        self.mock_page_cache.find_pages_by_attribute.return_value = mock_people

        result = self.service._get_existing_person_by_email("test@example.com")

        assert result == mock_people[0]

    def test_get_existing_person_by_email_not_found(self):
        """Test _get_existing_person_by_email returns None when not found."""
        self.mock_page_cache.find_pages_by_attribute.return_value = []

        result = self.service._get_existing_person_by_email("test@example.com")

        assert result is None

    def test_parse_name_and_email_full_format(self):
        """Test _parse_name_and_email with full display name format."""
        result = self.service._parse_name_and_email(
            "John Doe <john@example.com>", "john@example.com", "test"
        )

        expected = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": "test",
        }
        assert result == expected

    def test_parse_name_and_email_simple_format(self):
        """Test _parse_name_and_email with simple display name."""
        result = self.service._parse_name_and_email(
            "John Doe", "john@example.com", "test"
        )

        expected = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": "test",
        }
        assert result == expected

    def test_parse_name_and_email_single_name(self):
        """Test _parse_name_and_email with single name."""
        result = self.service._parse_name_and_email("John", "john@example.com", "test")

        expected = {
            "first_name": "John",
            "last_name": "",
            "email": "john@example.com",
            "source": "test",
        }
        assert result == expected

    def test_generate_person_id(self):
        """Test _generate_person_id creates consistent hash."""
        result1 = self.service._generate_person_id("test@example.com")
        result2 = self.service._generate_person_id("test@example.com")
        result3 = self.service._generate_person_id("different@example.com")

        # Same email should produce same ID
        assert result1 == result2
        # Different email should produce different ID
        assert result1 != result3
        # Should be reasonable length hash
        assert len(result1) > 10

    def test_store_and_create_page(self):
        """Test _store_and_create_page creates and stores PersonPage."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": "test",
        }

        with patch.object(
            self.service, "_generate_person_id", return_value="person123"
        ):
            result = self.service._store_and_create_page(person_info)

        # Verify PersonPage creation
        assert isinstance(result, PersonPage)
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.email == "john@example.com"
        assert result.full_name == "John Doe"

        # Verify page storage
        self.mock_page_cache.store_page.assert_called_once_with(result)

    def test_name_property(self):
        """Test name property returns correct value."""
        assert self.service.name == "person"
