"""Tests for the rewritten PeopleService."""

from unittest.mock import Mock, patch

import pytest

from praga_core import clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.google_api.people.page import PersonPage, SourceType
from pragweb.google_api.people.service import PeopleService


class TestPeopleService:
    """Test suite for PeopleService."""

    def setup_method(self):
        """Set up test environment."""
        self.mock_context = Mock()
        self.mock_context.root = "test-root"
        self.mock_context.services = {}
        self.mock_page_cache = Mock()
        self.mock_context.page_cache = self.mock_page_cache

        def mock_register_service(name, service):
            self.mock_context.services[name] = service

        self.mock_context.register_service = mock_register_service
        set_global_context(self.mock_context)

        # Create mock GoogleAPIClient
        self.mock_api_client = Mock()
        self.mock_api_client.search_contacts = Mock()
        self.mock_api_client.search_messages = Mock()
        self.mock_api_client.get_message = Mock()
        self.mock_api_client._people = Mock()

        self.service = PeopleService(self.mock_api_client)

    def teardown_method(self):
        """Clean up test environment."""
        clear_global_context()

    def test_init(self):
        """Test PeopleService initialization."""
        assert self.service.api_client is self.mock_api_client
        assert self.service.name == "people"
        assert "people" in self.mock_context.services
        assert self.mock_context.services["people"] is self.service

    def test_handle_person_request_cached(self):
        """Test handle_person_request returns cached person."""
        mock_person = Mock(spec=PersonPage)
        self.mock_page_cache.get_page.return_value = mock_person

        result = self.service.handle_person_request("person123")

        expected_uri = PageURI(root="test-root", type="person", id="person123")
        self.mock_page_cache.get_page.assert_called_once_with(PersonPage, expected_uri)
        assert result is mock_person

    def test_handle_person_request_not_found(self):
        """Test handle_person_request raises error when person not found."""
        self.mock_page_cache.get_page.return_value = None

        with pytest.raises(RuntimeError, match="Invalid request: Person person123 not found"):
            self.service.handle_person_request("person123")

    def test_get_person_record_existing(self):
        """Test get_person_record returns existing person."""
        mock_person = Mock(spec=PersonPage)
        with patch.object(self.service, "lookup_people", return_value=[mock_person]):
            result = self.service.get_person_record("test@example.com")
            assert result is mock_person

    def test_get_person_record_create_new(self):
        """Test get_person_record creates new person when not found."""
        mock_person = Mock(spec=PersonPage)
        with patch.object(self.service, "lookup_people", return_value=[]):
            with patch.object(self.service, "create_person", return_value=[mock_person]):
                result = self.service.get_person_record("test@example.com")
                assert result is mock_person

    def test_get_person_record_creation_fails(self):
        """Test get_person_record returns None when creation fails."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            with patch.object(self.service, "create_person", side_effect=ValueError("Not found")):
                result = self.service.get_person_record("test@example.com")
                assert result is None

    def test_lookup_people_by_email(self):
        """Test lookup_people by email address (search path only)."""
        mock_people = [Mock(spec=PersonPage), Mock(spec=PersonPage)]
        self.mock_page_cache.find_pages_by_attribute.return_value = mock_people

        result = self.service.lookup_people("test@example.com")

        assert result == mock_people
        self.mock_page_cache.find_pages_by_attribute.assert_called_once()

    def test_lookup_people_by_full_name(self):
        """Test lookup_people by full name when email match fails."""
        mock_people = [Mock(spec=PersonPage)]
        # First call (email) returns empty, second call (full name) returns results
        self.mock_page_cache.find_pages_by_attribute.side_effect = [[], mock_people]

        result = self.service.lookup_people("John Doe")

        assert result == mock_people
        assert self.mock_page_cache.find_pages_by_attribute.call_count == 2

    def test_lookup_people_by_first_name(self):
        """Test lookup_people by first name when other matches fail."""
        mock_people = [Mock(spec=PersonPage)]
        # Full name and first name calls
        self.mock_page_cache.find_pages_by_attribute.side_effect = [[], mock_people]

        result = self.service.lookup_people("John")

        assert result == mock_people
        assert self.mock_page_cache.find_pages_by_attribute.call_count == 2

    def test_lookup_people_not_found(self):
        """Test lookup_people returns empty list when not found."""
        self.mock_page_cache.find_pages_by_attribute.return_value = []

        result = self.service.lookup_people("nonexistent@example.com")

        assert result == []

    def test_create_person_existing(self):
        """Test create_person returns existing people if found."""
        mock_people = [Mock(spec=PersonPage)]
        with patch.object(self.service, "lookup_people", return_value=mock_people):
            result = self.service.create_person("John Doe")

        assert result == mock_people

    def test_create_person_from_people_api(self):
        """Test create_person from Google People API."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            mock_person_info = {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "source": SourceType.PEOPLE_API
            }
            
            with patch.object(self.service, "_extract_people_info_from_google_people", return_value=[mock_person_info]):
                with patch.object(self.service, "_extract_people_from_directory", return_value=[]):
                    with patch.object(self.service, "_extract_people_from_gmail_contacts", return_value=[]):
                        with patch.object(self.service, "_is_real_person", return_value=True):
                            # Mock page cache to return no existing person
                            self.mock_page_cache.find_pages_by_attribute.return_value = []
                            mock_person_page = Mock(spec=PersonPage)
                            with patch.object(self.service, "_store_and_create_page", return_value=mock_person_page):
                                result = self.service.create_person("john@example.com")

        assert result == [mock_person_page]

    def test_create_person_no_sources(self):
        """Test create_person raises error when no sources found."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            with patch.object(self.service, "_extract_people_info_from_google_people", return_value=[]):
                with patch.object(self.service, "_extract_people_from_directory", return_value=[]):
                    with patch.object(self.service, "_extract_people_from_gmail_contacts", return_value=[]):
                        with pytest.raises(ValueError, match="Could not find any real people"):
                            self.service.create_person("nonexistent@example.com")

    def test_create_person_filters_non_real_people(self):
        """Test create_person filters out non-real people."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            mock_person_info = {
                "first_name": "No Reply",
                "last_name": "",
                "email": "noreply@example.com",
                "source": SourceType.EMAILS
            }
            with patch.object(self.service, "_extract_people_info_from_google_people", return_value=[mock_person_info]):
                with patch.object(self.service, "_extract_people_from_directory", return_value=[]):
                    with patch.object(self.service, "_extract_people_from_gmail_contacts", return_value=[]):
                        with pytest.raises(ValueError, match="Could not find any real people"):
                            self.service.create_person("noreply@example.com")

    def test_create_person_name_divergence_error(self):
        """Test create_person raises error when names diverge for same email."""
        with patch.object(self.service, "lookup_people", return_value=[]):
            # Mock existing person with different name
            existing_person = Mock(spec=PersonPage)
            existing_person.full_name = "Jane Smith"
            existing_person.email = "john@example.com"

            # Mock page cache to return existing person
            self.mock_page_cache.find_pages_by_attribute.return_value = [existing_person]
            
            mock_person_info = {
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "source": SourceType.PEOPLE_API
            }
            with patch.object(self.service, "_extract_people_info_from_google_people", return_value=[mock_person_info]):
                with patch.object(self.service, "_extract_people_from_directory", return_value=[]):
                    with patch.object(self.service, "_extract_people_from_gmail_contacts", return_value=[]):
                        with patch.object(self.service, "_is_real_person", return_value=True):
                            with pytest.raises(ValueError, match="Name divergence detected"):
                                self.service.create_person("john@example.com")

    def test_extract_people_info_from_google_people(self):
        """Test _extract_people_info_from_google_people returns person info."""
        mock_api_result = {
            "person": {
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}]
            }
        }
        
        self.mock_api_client.search_contacts.return_value = [mock_api_result]
        
        result = self.service._extract_people_info_from_google_people("john@example.com")
        
        assert len(result) == 1
        assert result[0]["first_name"] == "John"
        assert result[0]["last_name"] == "Doe" 
        assert result[0]["email"] == "john@example.com"
        assert result[0]["source"] == SourceType.PEOPLE_API

    def test_extract_people_from_directory(self):
        """Test _extract_people_from_directory returns person info."""
        mock_directory_result = {
            "people": [{
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}]
            }]
        }
        
        mock_search = Mock()
        mock_search.execute.return_value = mock_directory_result
        mock_people = Mock()
        mock_people.searchDirectoryPeople.return_value = mock_search
        self.mock_api_client._people.people.return_value = mock_people
        
        result = self.service._extract_people_from_directory("john@example.com")
        
        assert len(result) == 1
        assert result[0]["first_name"] == "John"
        assert result[0]["last_name"] == "Doe"
        assert result[0]["email"] == "john@example.com"
        assert result[0]["source"] == SourceType.DIRECTORY_API

    def test_extract_people_from_gmail_contacts(self):
        """Test _extract_people_from_gmail_contacts returns person info."""
        mock_message = {"id": "123"}
        mock_message_data = {
            "payload": {
                "headers": [
                    {"name": "From", "value": "John Doe <john@example.com>"}
                ]
            }
        }
        
        self.mock_api_client.search_messages.return_value = ([mock_message], None)
        self.mock_api_client.get_message.return_value = mock_message_data
        
        with patch.object(self.service, "_matches_identifier", return_value=True):
            result = self.service._extract_people_from_gmail_contacts("john@example.com")
            
            assert len(result) == 1
            assert result[0]["first_name"] == "John"
            assert result[0]["last_name"] == "Doe"
            assert result[0]["email"] == "john@example.com"
            assert result[0]["source"] == SourceType.EMAILS

    def test_is_real_person_valid(self):
        """Test _is_real_person returns True for valid person."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
            "source": SourceType.PEOPLE_API
        }
        assert self.service._is_real_person(person_info) is True

    def test_is_real_person_automated(self):
        """Test _is_real_person returns False for automated accounts."""
        person_info = {
            "first_name": "No Reply",
            "last_name": "",
            "email": "noreply@example.com",
            "source": SourceType.EMAILS
        }
        assert self.service._is_real_person(person_info) is False

    def test_matches_identifier_email(self):
        """Test _matches_identifier for email identifiers."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }
        
        assert self.service._matches_identifier(person_info, "john@example.com") is True
        assert self.service._matches_identifier(person_info, "other@example.com") is False

    def test_matches_identifier_name(self):
        """Test _matches_identifier for name identifiers."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe", 
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }
        
        assert self.service._matches_identifier(person_info, "John") is True
        assert self.service._matches_identifier(person_info, "John Doe") is True
        assert self.service._matches_identifier(person_info, "Jane") is False

    def test_store_and_create_page(self):
        """Test _store_and_create_page creates PersonPage with source_enum."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }

        self.mock_page_cache.store_page = Mock()

        result = self.service._store_and_create_page(person_info)

        assert isinstance(result, PersonPage)
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.email == "john@example.com"
        assert result.source_enum == SourceType.PEOPLE_API
        self.mock_page_cache.store_page.assert_called_once_with(result)

    def test_toolkit_get_or_create_person(self):
        """Test toolkit get_or_create_person method."""
        toolkit = self.service.toolkit
        mock_person = Mock(spec=PersonPage)
        
        with patch.object(self.service, "get_person_record", return_value=mock_person):
            result = toolkit.get_or_create_person("test@example.com")
            assert result == [mock_person]

        with patch.object(self.service, "get_person_record", return_value=None):
            result = toolkit.get_or_create_person("test@example.com")
            assert result == []
