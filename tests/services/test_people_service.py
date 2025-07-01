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
        with patch.object(self.service, "lookup_existing_record", return_value=mock_person):
            result = self.service.get_person_record("test@example.com")
            assert result is mock_person

    def test_get_person_record_create_new(self):
        """Test get_person_record creates new person when not found."""
        mock_person = Mock(spec=PersonPage)
        with patch.object(self.service, "lookup_existing_record", return_value=None):
            with patch.object(self.service, "create_new_record", return_value=mock_person):
                result = self.service.get_person_record("test@example.com")
                assert result is mock_person

    def test_get_person_record_creation_fails(self):
        """Test get_person_record returns None when creation fails."""
        with patch.object(self.service, "lookup_existing_record", return_value=None):
            with patch.object(self.service, "create_new_record", side_effect=ValueError("Not found")):
                result = self.service.get_person_record("test@example.com")
                assert result is None

    def test_lookup_existing_record_by_email(self):
        """Test lookup_existing_record finds person by email."""
        mock_person = Mock(spec=PersonPage)
        self.mock_page_cache.find_pages_by_attribute.return_value = [mock_person]

        result = self.service.lookup_existing_record("test@example.com")

        assert result is mock_person
        self.mock_page_cache.find_pages_by_attribute.assert_called_once()

    def test_lookup_existing_record_by_full_name(self):
        """Test lookup_existing_record finds person by full name."""
        mock_person = Mock(spec=PersonPage)
        # First call (email) returns empty, second call (full name) returns results
        self.mock_page_cache.find_pages_by_attribute.side_effect = [[], [mock_person]]

        result = self.service.lookup_existing_record("John Doe")

        assert result is mock_person
        assert self.mock_page_cache.find_pages_by_attribute.call_count == 2

    def test_lookup_existing_record_by_first_name(self):
        """Test lookup_existing_record finds person by first name."""
        mock_person = Mock(spec=PersonPage)
        # Full name and first name calls
        self.mock_page_cache.find_pages_by_attribute.side_effect = [[], [mock_person]]

        result = self.service.lookup_existing_record("John")

        assert result is mock_person
        assert self.mock_page_cache.find_pages_by_attribute.call_count == 2

    def test_lookup_existing_record_not_found(self):
        """Test lookup_existing_record returns None when not found."""
        self.mock_page_cache.find_pages_by_attribute.return_value = []

        result = self.service.lookup_existing_record("nonexistent@example.com")

        assert result is None

    def test_create_new_record_from_people_api(self):
        """Test create_new_record from People API (explicit source)."""
        mock_person_info = {
            "first_name": "John",
            "last_name": "Doe", 
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }
        
        with patch.object(self.service, "_search_explicit_sources", return_value=mock_person_info):
            with patch.object(self.service, "_is_real_person", return_value=True):
                with patch.object(self.service, "_get_existing_person_by_email", return_value=None):
                    mock_person_page = Mock(spec=PersonPage)
                    with patch.object(self.service, "_create_and_store_person", return_value=mock_person_page):
                        result = self.service.create_new_record("john@example.com")
                        assert result is mock_person_page

    def test_create_new_record_from_emails(self):
        """Test create_new_record from emails (implicit source)."""
        mock_person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com", 
            "source": SourceType.EMAILS
        }
        
        with patch.object(self.service, "_search_explicit_sources", return_value=None):
            with patch.object(self.service, "_search_implicit_sources", return_value=mock_person_info):
                with patch.object(self.service, "_is_real_person", return_value=True):
                    with patch.object(self.service, "_get_existing_person_by_email", return_value=None):
                        mock_person_page = Mock(spec=PersonPage)
                        with patch.object(self.service, "_create_and_store_person", return_value=mock_person_page):
                            result = self.service.create_new_record("john@example.com")
                            assert result is mock_person_page

    def test_create_new_record_no_sources(self):
        """Test create_new_record raises error when no sources found."""
        with patch.object(self.service, "_search_explicit_sources", return_value=None):
            with patch.object(self.service, "_search_implicit_sources", return_value=None):
                with pytest.raises(ValueError, match="Could not find person data"):
                    self.service.create_new_record("nonexistent@example.com")

    def test_create_new_record_not_real_person(self):
        """Test create_new_record raises error for automated accounts."""
        mock_person_info = {
            "first_name": "No Reply",
            "last_name": "",
            "email": "noreply@example.com",
            "source": SourceType.EMAILS
        }
        
        with patch.object(self.service, "_search_explicit_sources", return_value=mock_person_info):
            with patch.object(self.service, "_is_real_person", return_value=False):
                with pytest.raises(ValueError, match="appears to be automated"):
                    self.service.create_new_record("noreply@example.com")

    def test_create_new_record_existing_person_same_email(self):
        """Test create_new_record returns existing person with same email and name."""
        mock_person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }
        
        existing_person = Mock(spec=PersonPage)
        existing_person.full_name = "John Doe"
        
        with patch.object(self.service, "_search_explicit_sources", return_value=mock_person_info):
            with patch.object(self.service, "_is_real_person", return_value=True):
                with patch.object(self.service, "_get_existing_person_by_email", return_value=existing_person):
                    with patch.object(self.service, "_validate_name_consistency"):
                        result = self.service.create_new_record("john@example.com")
                        assert result is existing_person

    def test_search_people_api(self):
        """Test _search_people_api returns person info."""
        mock_api_result = {
            "person": {
                "names": [{"displayName": "John Doe"}],
                "emailAddresses": [{"value": "john@example.com"}]
            }
        }
        
        self.mock_api_client.search_contacts.return_value = [mock_api_result]
        
        with patch.object(self.service, "_matches_identifier", return_value=True):
            result = self.service._search_people_api("john@example.com")
            
            assert result is not None
            assert result["first_name"] == "John"
            assert result["last_name"] == "Doe" 
            assert result["email"] == "john@example.com"
            assert result["source"] == SourceType.PEOPLE_API

    def test_search_directory_api(self):
        """Test _search_directory_api returns person info."""
        mock_user = {
            "primaryEmail": "john@example.com",
            "name": {
                "fullName": "John Doe",
                "givenName": "John",
                "familyName": "Doe"
            }
        }
        
        mock_admin_service = Mock()
        mock_admin_service.users().get().execute.return_value = mock_user
        self.mock_api_client.auth_manager.get_admin_service.return_value = mock_admin_service
        
        result = self.service._search_directory_api("john@example.com")
        
        assert result is not None
        assert result["first_name"] == "John"
        assert result["last_name"] == "Doe"
        assert result["email"] == "john@example.com"
        assert result["source"] == SourceType.DIRECTORY_API

    def test_search_emails(self):
        """Test _search_emails returns person info."""
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
            result = self.service._search_emails("john@example.com")
            
            assert result is not None
            assert result["first_name"] == "John"
            assert result["last_name"] == "Doe"
            assert result["email"] == "john@example.com"
            assert result["source"] == SourceType.EMAILS

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

    def test_validate_name_consistency_same_names(self):
        """Test _validate_name_consistency passes for same names."""
        existing_person = Mock(spec=PersonPage)
        existing_person.full_name = "John Doe"
        
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }
        
        # Should not raise exception
        self.service._validate_name_consistency(existing_person, person_info)

    def test_validate_name_consistency_different_names(self):
        """Test _validate_name_consistency raises error for different names."""
        existing_person = Mock(spec=PersonPage)
        existing_person.full_name = "Jane Smith"
        
        person_info = {
            "first_name": "John", 
            "last_name": "Doe",
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }
        
        with pytest.raises(ValueError, match="Name divergence detected"):
            self.service._validate_name_consistency(existing_person, person_info)

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

    def test_create_and_store_person(self):
        """Test _create_and_store_person creates PersonPage with source_enum."""
        person_info = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "source": SourceType.PEOPLE_API
        }

        self.mock_page_cache.store_page = Mock()

        result = self.service._create_and_store_person(person_info)

        assert isinstance(result, PersonPage)
        assert result.first_name == "John"
        assert result.last_name == "Doe"
        assert result.email == "john@example.com"
        assert result.source_enum == SourceType.PEOPLE_API
        self.mock_page_cache.store_page.assert_called_once_with(result)

    def test_toolkit_get_person_record(self):
        """Test toolkit get_person_record method."""
        toolkit = self.service.toolkit
        mock_person = Mock(spec=PersonPage)
        
        with patch.object(self.service, "get_person_record", return_value=mock_person):
            result = toolkit.get_person_record("test@example.com")
            assert result is mock_person

    def test_toolkit_get_person_by_email(self):
        """Test toolkit get_person_by_email method."""
        toolkit = self.service.toolkit
        mock_person = Mock(spec=PersonPage)
        
        with patch.object(self.service, "_get_existing_person_by_email", return_value=mock_person):
            result = toolkit.get_person_by_email("test@example.com")
            assert result is mock_person
