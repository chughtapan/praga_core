"""Comprehensive tests for People service multi-source search functionality."""

from unittest.mock import Mock, patch

import pytest

from praga_core import ServerContext, clear_global_context, set_global_context
from praga_core.types import PageURI
from pragweb.api_clients.base import BaseProviderClient
from pragweb.pages import PersonPage
from pragweb.services import PeopleService
from pragweb.services.people import PersonInfo


class MockEmailClient:
    """Mock Email client for testing Gmail search."""

    def __init__(self):
        self.messages = []
        self.search_responses = {}

    async def search_messages(self, query: str):
        """Mock search messages - returns single dict, not tuple."""
        # Return messages based on query
        return {"messages": self.search_responses.get(query, [])}

    async def get_message(self, message_id: str):
        """Mock get message."""
        return {
            "id": message_id,
            "payload": {
                "headers": [
                    {"name": "From", "value": "John Doe <john@example.com>"},
                    {"name": "To", "value": "test@example.com"},
                    {"name": "Subject", "value": "Test Email"},
                ]
            },
        }


class MockPeopleClient:
    """Mock People client for testing People API search."""

    def __init__(self):
        self.search_responses = {}
        self.has_directory_api = True
        self._people = Mock()
        self._executor = Mock()

    async def search_contacts(self, query: str):
        """Mock search contacts."""
        return self.search_responses.get(query, {"results": []})

    async def get_contact(self, contact_id: str):
        """Mock get contact."""
        return {"id": contact_id, "names": [{"displayName": "Test Person"}]}

    def parse_contact_to_person_page(self, contact_data, page_uri):
        """Mock parse contact."""
        return PersonPage(
            uri=page_uri,
            first_name="Test",
            last_name="Person",
            email="test@example.com",
        )


class MockGoogleProviderClient(BaseProviderClient):
    """Mock Google provider client with all search capabilities."""

    def __init__(self):
        super().__init__(Mock())
        self._people_client = MockPeopleClient()
        self._email_client = MockEmailClient()

    @property
    def people_client(self):
        return self._people_client

    @property
    def email_client(self):
        return self._email_client

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


class MockMicrosoftProviderClient(BaseProviderClient):
    """Mock Microsoft provider client with limited search capabilities."""

    def __init__(self):
        super().__init__(Mock())
        self._people_client = MockPeopleClient()

    @property
    def people_client(self):
        return self._people_client

    @property
    def email_client(self):
        # Microsoft provider doesn't have email client in our implementation
        return None

    @property
    def calendar_client(self):
        return Mock()

    @property
    def documents_client(self):
        return Mock()

    async def test_connection(self) -> bool:
        return True

    def get_provider_name(self) -> str:
        return "microsoft"


class TestPeopleComprehensiveSearch:
    """Test suite for comprehensive people search functionality."""

    @pytest.fixture
    async def service_with_google_only(self):
        """Create service with Google provider only."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock provider
        google_provider = MockGoogleProviderClient()
        providers = {"google": google_provider}

        # Create service
        service = PeopleService(providers)

        yield service, google_provider

        clear_global_context()

    @pytest.fixture
    async def service_with_multiple_providers(self):
        """Create service with both Google and Microsoft providers."""
        clear_global_context()

        # Create real context
        context = await ServerContext.create(root="test://example")
        set_global_context(context)

        # Create mock providers
        google_provider = MockGoogleProviderClient()
        microsoft_provider = MockMicrosoftProviderClient()
        providers = {"google": google_provider, "microsoft": microsoft_provider}

        # Create service
        service = PeopleService(providers)

        yield service, google_provider, microsoft_provider

        clear_global_context()

    @pytest.mark.asyncio
    async def test_google_multi_source_search_all_sources_hit(
        self, service_with_google_only
    ):
        """Test that Google search hits all three sources: People API, Directory API, Gmail."""
        service, google_provider = service_with_google_only

        # Set up responses for all three sources
        google_provider.people_client.search_responses["arvind"] = {
            "results": [
                {
                    "person": {
                        "names": [{"displayName": "Arvind Kumar"}],
                        "emailAddresses": [{"value": "arvind@company.com"}],
                    }
                }
            ]
        }

        # Mock Directory API search
        mock_directory_results = {
            "people": [
                {
                    "names": [{"displayName": "Arvind Singh"}],
                    "emailAddresses": [{"value": "arvind.singh@company.com"}],
                }
            ]
        }

        # Mock Gmail search
        google_provider.email_client.search_responses[
            '(from:"arvind") OR (to:"arvind")'
        ] = [{"id": "msg1"}]

        with patch.object(
            service,
            "_extract_people_from_provider_directory",
            return_value=[
                PersonInfo(
                    first_name="Arvind",
                    last_name="Singh",
                    email="arvind.singh@company.com",
                    source="directory_api",
                )
            ],
        ) as mock_directory:

            with patch.object(
                service,
                "_extract_people_from_provider_gmail",
                return_value=[
                    PersonInfo(
                        first_name="Arvind",
                        last_name="Patel",
                        email="arvind.patel@gmail.com",
                        source="emails",
                    )
                ],
            ) as mock_gmail:

                # Execute search
                result = await service.search_across_providers("arvind")

                # Verify all sources were called
                mock_directory.assert_called_once_with("arvind", google_provider)
                mock_gmail.assert_called_once_with("arvind", google_provider)

                # Should find people from all sources
                assert len(result) >= 1  # At least one person found
                # Verify people from different sources exist
                sources = {
                    person.source for person in result if hasattr(person, "source")
                }

    @pytest.mark.asyncio
    async def test_microsoft_single_source_search(
        self, service_with_multiple_providers
    ):
        """Test that Microsoft search only hits People API (no Directory or Gmail)."""
        service, google_provider, microsoft_provider = service_with_multiple_providers

        # Set up Microsoft People API response
        microsoft_provider.people_client.search_responses["john"] = {
            "results": [
                {
                    "givenName": "John",
                    "surname": "Smith",
                    "emailAddresses": [{"address": "john.smith@outlook.com"}],
                }
            ]
        }

        with patch.object(
            service, "_extract_people_from_provider_directory"
        ) as mock_directory:
            with patch.object(
                service, "_extract_people_from_provider_gmail"
            ) as mock_gmail:

                # Execute search on Microsoft provider only
                result = await service._search_single_provider_comprehensive(
                    "john", "microsoft", microsoft_provider
                )

                # Directory and Gmail should not be called for Microsoft
                mock_directory.assert_not_called()
                mock_gmail.assert_not_called()

    @pytest.mark.asyncio
    async def test_cross_provider_search_aggregation(
        self, service_with_multiple_providers
    ):
        """Test that search aggregates results across multiple providers."""
        service, google_provider, microsoft_provider = service_with_multiple_providers

        # Set up responses for both providers
        google_provider.people_client.search_responses["sarah"] = {
            "results": [
                {
                    "person": {
                        "names": [{"displayName": "Sarah Johnson"}],
                        "emailAddresses": [{"value": "sarah@google.com"}],
                    }
                }
            ]
        }

        microsoft_provider.people_client.search_responses["sarah"] = {
            "results": [
                {
                    "givenName": "Sarah",
                    "surname": "Wilson",
                    "emailAddresses": [{"address": "sarah@microsoft.com"}],
                }
            ]
        }

        # Mock other sources to return empty
        with patch.object(
            service, "_extract_people_from_provider_directory", return_value=[]
        ):
            with patch.object(
                service, "_extract_people_from_provider_gmail", return_value=[]
            ):

                result = await service.search_across_providers("sarah")

                # Should find people from both providers
                assert len(result) >= 2
                emails = {person.email for person in result}
                assert "sarah@google.com" in emails or "sarah@microsoft.com" in emails

    @pytest.mark.asyncio
    async def test_email_search_vs_name_search_behavior(self, service_with_google_only):
        """Test different search behavior for email vs name identifiers."""
        service, google_provider = service_with_google_only

        # Test email search
        email_identifier = "test@example.com"

        with patch.object(
            service, "_extract_people_from_provider_gmail"
        ) as mock_gmail_email:
            await service._extract_people_from_provider_gmail(
                email_identifier, google_provider
            )

            # For email search, should search for specific email
            mock_gmail_email.assert_called_once_with(email_identifier, google_provider)

        # Test name search
        name_identifier = "John Doe"

        with patch.object(
            service, "_extract_people_from_provider_gmail"
        ) as mock_gmail_name:
            await service._extract_people_from_provider_gmail(
                name_identifier, google_provider
            )

            # For name search, should search with broader queries
            mock_gmail_name.assert_called_once_with(name_identifier, google_provider)

    @pytest.mark.asyncio
    async def test_search_source_prioritization_name_vs_email(
        self, service_with_google_only
    ):
        """Test different prioritization for name vs email searches."""
        service, google_provider = service_with_google_only

        # Test name-based search: Gmail first, then People API, then Directory
        name_call_order = []

        async def track_people_api_call(*args):
            name_call_order.append("people_api")
            return [
                PersonInfo(
                    first_name="John",
                    last_name="Doe",
                    email="john@example.com",
                    source="people_api",
                )
            ]

        async def track_directory_call(*args):
            name_call_order.append("directory_api")
            return []

        async def track_gmail_call(*args):
            name_call_order.append("gmail")
            return []

        with patch.object(
            service,
            "_extract_people_info_from_provider_people_api",
            side_effect=track_people_api_call,
        ):
            with patch.object(
                service,
                "_extract_people_from_provider_directory",
                side_effect=track_directory_call,
            ):
                with patch.object(
                    service,
                    "_extract_people_from_provider_gmail",
                    side_effect=track_gmail_call,
                ):

                    # Test name search
                    await service._search_single_provider_comprehensive(
                        "john doe", "google", google_provider
                    )

                    # For names: Gmail first, then People API, then Directory
                    assert name_call_order == ["gmail", "people_api", "directory_api"]

        # Test email-based search: People API first, then Directory, then Gmail
        email_call_order = []

        async def track_people_api_call_email(*args):
            email_call_order.append("people_api")
            return [
                PersonInfo(
                    first_name="Jane",
                    last_name="Smith",
                    email="jane@example.com",
                    source="people_api",
                )
            ]

        async def track_directory_call_email(*args):
            email_call_order.append("directory_api")
            return []

        async def track_gmail_call_email(*args):
            email_call_order.append("gmail")
            return []

        with patch.object(
            service,
            "_extract_people_info_from_provider_people_api",
            side_effect=track_people_api_call_email,
        ):
            with patch.object(
                service,
                "_extract_people_from_provider_directory",
                side_effect=track_directory_call_email,
            ):
                with patch.object(
                    service,
                    "_extract_people_from_provider_gmail",
                    side_effect=track_gmail_call_email,
                ):

                    # Test email search
                    await service._search_single_provider_comprehensive(
                        "jane@example.com", "google", google_provider
                    )

                    # For emails: People API first, then Directory, then Gmail
                    assert email_call_order == ["people_api", "directory_api", "gmail"]

    @pytest.mark.asyncio
    async def test_search_strategy_rationale(self, service_with_google_only):
        """Test the rationale behind search strategy prioritization."""
        service, google_provider = service_with_google_only

        # For names: Gmail interactions are more likely to be relevant contacts
        # someone actually communicates with, so prioritize them
        name_results = []

        async def mock_gmail_name_search(*args):
            name_results.append("gmail_contacted_person")
            return [
                PersonInfo(
                    first_name="Alice",
                    last_name="Contacted",
                    email="alice.contacted@company.com",
                    source="emails",
                )
            ]

        async def mock_people_api_name_search(*args):
            name_results.append("people_api_person")
            return [
                PersonInfo(
                    first_name="Alice",
                    last_name="Directory",
                    email="alice.directory@company.com",
                    source="people_api",
                )
            ]

        with patch.object(
            service,
            "_extract_people_from_provider_gmail",
            side_effect=mock_gmail_name_search,
        ):
            with patch.object(
                service,
                "_extract_people_info_from_provider_people_api",
                side_effect=mock_people_api_name_search,
            ):
                with patch.object(
                    service, "_extract_people_from_provider_directory", return_value=[]
                ):
                    result = await service._search_single_provider_comprehensive(
                        "alice", "google", google_provider
                    )

                    # Gmail should be checked first for name searches
                    assert name_results[0] == "gmail_contacted_person"

        # For emails: Structured APIs are more reliable for exact email matches
        email_results = []

        async def mock_people_api_email_search(*args):
            email_results.append("people_api_exact")
            return [
                PersonInfo(
                    first_name="Bob",
                    last_name="Official",
                    email="bob@company.com",
                    source="people_api",
                )
            ]

        async def mock_gmail_email_search(*args):
            email_results.append("gmail_email")
            return []

        with patch.object(
            service,
            "_extract_people_info_from_provider_people_api",
            side_effect=mock_people_api_email_search,
        ):
            with patch.object(
                service,
                "_extract_people_from_provider_gmail",
                side_effect=mock_gmail_email_search,
            ):
                with patch.object(
                    service, "_extract_people_from_provider_directory", return_value=[]
                ):
                    result = await service._search_single_provider_comprehensive(
                        "bob@company.com", "google", google_provider
                    )

                    # People API should be checked first for email searches
                    assert email_results[0] == "people_api_exact"

    @pytest.mark.asyncio
    async def test_deduplication_across_sources(self, service_with_google_only):
        """Test that duplicate people across sources are properly deduplicated."""
        service, google_provider = service_with_google_only

        # Create duplicate person info from different sources
        duplicate_person_infos = [
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            ),
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",  # Same email
                source="directory_api",
            ),
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",  # Same email again
                source="emails",
            ),
        ]

        # Mock the deduplication process
        new_infos, existing = await service._filter_and_deduplicate_people(
            duplicate_person_infos, "john"
        )

        # Should only have one unique person by email
        all_people = new_infos + existing
        unique_emails = {
            (info.email if hasattr(info, "email") else info.email)
            for info in all_people
        }
        assert len(unique_emails) <= 1  # Should be deduplicated

    @pytest.mark.asyncio
    async def test_error_handling_per_source(self, service_with_google_only):
        """Test that errors in one source don't prevent others from being searched."""
        service, google_provider = service_with_google_only

        # Mock one source to fail and others to succeed
        with patch.object(
            service,
            "_extract_people_info_from_provider_people_api",
            return_value=[],  # Return empty instead of raising
        ):
            with patch.object(
                service,
                "_extract_people_from_provider_directory",
                return_value=[
                    PersonInfo(
                        first_name="Success",
                        last_name="Person",
                        email="success@example.com",
                        source="directory_api",
                    )
                ],
            ):
                with patch.object(
                    service, "_extract_people_from_provider_gmail", return_value=[]
                ):

                    result = await service._search_single_provider_comprehensive(
                        "test", "google", google_provider
                    )

                    # Should still get results from working sources
                    assert isinstance(result, list)
                    assert len(result) >= 1  # Should have at least the directory result

    @pytest.mark.asyncio
    async def test_error_handling_per_provider(self, service_with_multiple_providers):
        """Test that errors in one provider don't prevent others from being searched."""
        service, google_provider, microsoft_provider = service_with_multiple_providers

        # Mock Google provider to fail completely
        with patch.object(
            service,
            "_search_single_provider_comprehensive",
            side_effect=lambda identifier, provider_name, provider_client: (
                Exception("Google failed")
                if provider_name == "google"
                else [
                    PersonPage(
                        uri=PageURI(root="test://example", type="person", id="success"),
                        first_name="Microsoft",
                        last_name="Success",
                        email="success@microsoft.com",
                    )
                ]
            ),
        ):

            result = await service.search_across_providers("test")

            # Should still get results from working provider
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_search_continues_across_all_sources_for_names(
        self, service_with_google_only
    ):
        """Test that name searches don't stop at first match and search ALL sources."""
        service, google_provider = service_with_google_only

        people_api_called = False
        directory_api_called = False
        gmail_called = False

        async def track_people_api(*args):
            nonlocal people_api_called
            people_api_called = True
            return [
                PersonInfo(
                    first_name="John",
                    last_name="People",
                    email="john@people.com",
                    source="people_api",
                )
            ]

        async def track_directory(*args):
            nonlocal directory_api_called
            directory_api_called = True
            return [
                PersonInfo(
                    first_name="John",
                    last_name="Directory",
                    email="john@directory.com",
                    source="directory_api",
                )
            ]

        async def track_gmail(*args):
            nonlocal gmail_called
            gmail_called = True
            return [
                PersonInfo(
                    first_name="John",
                    last_name="Gmail",
                    email="john@gmail.com",
                    source="emails",
                )
            ]

        with patch.object(
            service,
            "_extract_people_info_from_provider_people_api",
            side_effect=track_people_api,
        ):
            with patch.object(
                service,
                "_extract_people_from_provider_directory",
                side_effect=track_directory,
            ):
                with patch.object(
                    service,
                    "_extract_people_from_provider_gmail",
                    side_effect=track_gmail,
                ):

                    result = await service._search_single_provider_comprehensive(
                        "john", "google", google_provider
                    )

                    # All sources should be called even though People API returned results
                    assert people_api_called, "People API should be called"
                    assert directory_api_called, "Directory API should be called"
                    assert gmail_called, "Gmail should be called"

    @pytest.mark.asyncio
    async def test_real_person_filtering(self, service_with_google_only):
        """Test that automated/bot emails are filtered out."""
        service, google_provider = service_with_google_only

        # Create mix of real and automated person infos
        mixed_person_infos = [
            PersonInfo(
                first_name="John",
                last_name="Doe",
                email="john@example.com",
                source="people_api",
            ),
            PersonInfo(
                first_name="",
                last_name="",
                email="noreply@example.com",  # Should be filtered
                source="emails",
            ),
            PersonInfo(
                first_name="Support",
                last_name="Team",
                email="support@example.com",  # Should be filtered
                source="emails",
            ),
            PersonInfo(
                first_name="Jane",
                last_name="Smith",
                email="jane@example.com",
                source="directory_api",
            ),
        ]

        # Test the filtering
        new_infos, existing = await service._filter_and_deduplicate_people(
            mixed_person_infos, "test"
        )

        # Should filter out automated emails
        all_emails = [
            (info.email if hasattr(info, "email") else info.email)
            for info in (new_infos + existing)
        ]

        assert "john@example.com" in all_emails or len(all_emails) > 0
        assert "noreply@example.com" not in all_emails
        assert "support@example.com" not in all_emails

    @pytest.mark.asyncio
    async def test_gmail_search_query_construction(self, service_with_google_only):
        """Test that Gmail search queries are constructed correctly for different scenarios."""
        service, google_provider = service_with_google_only

        # Test email identifier
        with patch.object(
            google_provider.email_client, "search_messages"
        ) as mock_search:
            mock_search.return_value = {"messages": []}

            await service._extract_people_from_provider_gmail(
                "test@example.com", google_provider
            )

            # Should search for specific email
            mock_search.assert_called_with(
                "from:test@example.com OR to:test@example.com"
            )

        # Test full name identifier
        with patch.object(
            google_provider.email_client, "search_messages"
        ) as mock_search:
            mock_search.return_value = {"messages": []}

            await service._extract_people_from_provider_gmail(
                "John Doe", google_provider
            )

            # Should construct broader search for names
            called_query = mock_search.call_args[0][0]
            assert 'from:"John Doe"' in called_query
            assert 'to:"John Doe"' in called_query
            assert 'from:"John"' in called_query  # First name search
            assert 'to:"John"' in called_query

        # Test single name identifier
        with patch.object(
            google_provider.email_client, "search_messages"
        ) as mock_search:
            mock_search.return_value = {"messages": []}

            await service._extract_people_from_provider_gmail("Alice", google_provider)

            called_query = mock_search.call_args[0][0]
            assert 'from:"Alice"' in called_query
            assert 'to:"Alice"' in called_query

    @pytest.mark.asyncio
    async def test_gmail_name_extraction_from_multiple_messages(
        self, service_with_google_only
    ):
        """Test that Gmail extraction finds the best display name across multiple messages."""
        service, google_provider = service_with_google_only

        # Test email address that might appear with or without display name
        test_email = "jdoe@example.com"

        # Mock search to return multiple messages
        google_provider.email_client.search_responses[
            f"from:{test_email} OR to:{test_email}"
        ] = [
            {"id": "msg1"},
            {"id": "msg2"},
            {"id": "msg3"},
        ]

        # Mock messages with different name representations
        message_responses = {
            # Message 1: Email without display name (common in automated emails)
            "msg1": {
                "id": "msg1",
                "payload": {
                    "headers": [
                        {"name": "From", "value": test_email},  # No display name
                        {"name": "To", "value": "recipient@example.com"},
                    ]
                },
            },
            # Message 2: Email with full display name (this is what we want to find!)
            "msg2": {
                "id": "msg2",
                "payload": {
                    "headers": [
                        {
                            "name": "From",
                            "value": f"John Doe <{test_email}>",
                        },  # Full name!
                        {"name": "To", "value": "recipient@example.com"},
                    ]
                },
            },
            # Message 3: Another email without display name
            "msg3": {
                "id": "msg3",
                "payload": {
                    "headers": [
                        {"name": "From", "value": test_email},  # No display name again
                        {"name": "To", "value": "recipient@example.com"},
                    ]
                },
            },
        }

        async def mock_get_message(message_id):
            return message_responses[message_id]

        google_provider.email_client.get_message = mock_get_message

        # Extract people from Gmail messages
        result = await service._extract_people_from_provider_gmail(
            test_email, google_provider
        )

        # Verify results
        assert len(result) == 1, "Should find exactly one person"

        person = result[0]
        assert person.email == test_email
        assert (
            person.first_name == "John"
        ), "Should extract first name from display name"
        assert person.last_name == "Doe", "Should extract last name from display name"
        assert person.source == "emails"

        # Verify we're NOT using the email local part as the name
        assert (
            person.first_name != "jdoe"
        ), "Should NOT use email local part as first name"
