"""Tests for People service with new architecture."""

from unittest.mock import AsyncMock, Mock

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import PersonPage
from pragweb.services import PeopleService


class MockPeopleClient:
    """Mock People client for testing."""

    def __init__(self):
        self.contacts = {}
        self.groups = {}

    async def get_contact(self, contact_id: str):
        """Get contact by ID."""
        return self.contacts.get(contact_id, {})

    async def search_contacts(self, **kwargs):
        """Search contacts."""
        return {"results": [], "nextPageToken": None}

    async def list_contacts(self, **kwargs):
        """List contacts."""
        return {"connections": [], "nextPageToken": None}

    async def create_contact(self, **kwargs):
        """Create a new contact."""
        return {"resourceName": "people/new_contact_123"}

    async def update_contact(self, **kwargs):
        """Update a contact."""
        return {"resourceName": f"people/{kwargs.get('contact_id', 'test')}"}

    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact."""
        return True

    def parse_contact_to_person_page(
        self, contact_data, page_uri: PageURI
    ) -> PersonPage:
        """Parse contact data to PersonPage."""
        return PersonPage(
            uri=page_uri,
            provider_person_id=contact_data.get("resourceName", "test_person").replace(
                "people/", ""
            ),
            first_name=contact_data.get("first_name", "Test"),
            last_name=contact_data.get("last_name", "Person"),
            email=contact_data.get("email", "test@example.com"),
            phone_numbers=contact_data.get("phone_numbers", []),
            job_title=contact_data.get("job_title"),
            company=contact_data.get("company"),
        )


class MockGoogleProviderClient(BaseProviderClient):
    """Mock Google provider client."""

    def __init__(self):
        super().__init__(Mock())
        self._people_client = MockPeopleClient()

    @property
    def people_client(self):
        return self._people_client

    @property
    def email_client(self):
        return Mock()

    @property
    def calendar_client(self):
        return Mock()

    @property
    def documents_client(self):
        return Mock()

    async def test_connection(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "google"


class TestPeopleService:
    """Test suite for PeopleService with new architecture."""

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
        service = PeopleService(providers)

        yield service

        clear_global_context()

    @pytest.mark.asyncio
    async def test_service_initialization(self, service):
        """Test that service initializes correctly."""
        assert service.name == "people"
        assert len(service.providers) == 1
        assert "google" in service.providers

    @pytest.mark.asyncio
    async def test_service_registration(self, service):
        """Test that service registers with context."""
        context = service.context
        registered_service = context.get_service("people")
        assert registered_service is service

    @pytest.mark.asyncio
    async def test_create_person_page(self, service):
        """Test creating a person page from URI."""
        # Set up mock contact data
        contact_data = {
            "resourceName": "people/test_person",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john@example.com",
            "phone_numbers": ["+1234567890"],
            "job_title": "Software Engineer",
            "company": "Test Corp",
        }

        service.providers["google"].people_client.get_contact = AsyncMock(
            return_value=contact_data
        )

        # Create page URI
        page_uri = PageURI(root="test://example", type="person", id="test_person")

        # Test page creation
        person_page = await service.create_person_page(page_uri)

        assert isinstance(person_page, PersonPage)
        assert person_page.uri == page_uri
        assert person_page.first_name == "John"
        assert person_page.last_name == "Doe"
        assert person_page.email == "john@example.com"
        assert person_page.full_name == "John Doe"

        # Verify API was called
        service.providers["google"].people_client.get_contact.assert_called_once_with(
            "test_person"
        )

    @pytest.mark.asyncio
    async def test_parse_person_uri(self, service):
        """Test parsing person URI."""
        page_uri = PageURI(root="test://example", type="person", id="person123")

        provider_name, person_id = service._parse_person_uri(page_uri)

        assert provider_name == "google"
        assert person_id == "person123"

    @pytest.mark.asyncio
    async def test_parse_person_uri_invalid_format(self, service):
        """Test parsing person URI with invalid format."""
        page_uri = PageURI(root="test://example", type="person", id="invalid_format")

        # This test is no longer relevant since we don't parse provider from URI
        # Just test that it returns the provider and ID correctly
        provider_name, person_id = service._parse_person_uri(page_uri)
        assert provider_name == "google"
        assert person_id == "invalid_format"

    @pytest.mark.asyncio
    async def test_empty_providers(self, service):
        """Test handling of service with no providers."""
        # Clear providers to simulate error
        service.providers = {}

        page_uri = PageURI(root="test://example", type="person", id="person123")

        with pytest.raises(ValueError, match="No provider available for service"):
            await service.create_person_page(page_uri)

    @pytest.mark.asyncio
    async def test_update_contact_action(self, service):
        """Test update_contact action."""
        # Create person page
        person_uri = PageURI(root="test://example", type="person", id="person123")

        # Mock update_contact to succeed
        service.providers["google"].people_client.update_contact = AsyncMock(
            return_value={"resourceName": "people/person123"}
        )

        # Test the action through context
        context = service.context
        result = await context.invoke_action(
            "update_contact",
            {
                "person": person_uri,
                "first_name": "Updated",
                "last_name": "Name",
                "email": "updated@example.com",
            },
        )

        # Verify the result
        assert result == {"success": True}

        # Verify update_contact was called
        service.providers["google"].people_client.update_contact.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_contact_action(self, service):
        """Test delete_contact action."""
        # Create person page
        person_uri = PageURI(root="test://example", type="person", id="person123")

        # Mock delete_contact to succeed
        service.providers["google"].people_client.delete_contact = AsyncMock(
            return_value=True
        )

        # Test the action through context
        context = service.context
        result = await context.invoke_action(
            "delete_contact",
            {"person": person_uri},
        )

        # Verify the result
        assert result == {"success": True}

        # Verify delete_contact was called
        service.providers["google"].people_client.delete_contact.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_registration(self, service):
        """Test that actions are properly registered with the context."""
        context = service.context

        # Verify actions are registered (create_contact is now a tool, not an action)
        assert "update_contact" in context._actions
        assert "delete_contact" in context._actions
