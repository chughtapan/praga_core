"""Abstract base classes for API client providers."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from praga_core.types import PageURI
from pragweb.pages import (
    CalendarEventPage,
    DocumentChunk,
    DocumentHeader,
    EmailPage,
    EmailThreadPage,
    PersonPage,
)


class BaseAuthManager(ABC):
    """Abstract base class for authentication managers."""

    @abstractmethod
    async def get_credentials(self) -> Any:
        """Get authentication credentials."""

    @abstractmethod
    async def refresh_credentials(self) -> Any:
        """Refresh authentication credentials."""

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""


class BaseAPIClient(ABC):
    """Abstract base class for API clients."""

    def __init__(self, auth_manager: BaseAuthManager):
        self.auth_manager = auth_manager

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test API connection."""


class BaseEmailClient(ABC):
    """Abstract base class for email API clients."""

    @abstractmethod
    async def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get a single email message by ID."""

    @abstractmethod
    async def get_thread(self, thread_id: str) -> Dict[str, Any]:
        """Get an email thread by ID."""

    @abstractmethod
    async def search_messages(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search for email messages."""

    @abstractmethod
    async def send_message(
        self,
        to: List[str],
        subject: str,
        body: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email message."""

    @abstractmethod
    async def reply_to_message(
        self, message_id: str, body: str, reply_all: bool = False
    ) -> Dict[str, Any]:
        """Reply to an email message."""

    @abstractmethod
    async def mark_as_read(self, message_id: str) -> bool:
        """Mark a message as read."""

    @abstractmethod
    async def mark_as_unread(self, message_id: str) -> bool:
        """Mark a message as unread."""

    @abstractmethod
    def parse_message_to_email_page(
        self, message_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailPage:
        """Parse provider-specific message data to EmailPage."""

    @abstractmethod
    def parse_thread_to_thread_page(
        self, thread_data: Dict[str, Any], page_uri: PageURI
    ) -> EmailThreadPage:
        """Parse provider-specific thread data to EmailThreadPage."""


class BaseCalendarClient(ABC):
    """Abstract base class for calendar API clients."""

    @abstractmethod
    async def get_event(
        self, event_id: str, calendar_id: str = "primary"
    ) -> Dict[str, Any]:
        """Get a calendar event by ID."""

    @abstractmethod
    async def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[datetime] = None,
        time_max: Optional[datetime] = None,
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List calendar events."""

    @abstractmethod
    async def search_events(
        self,
        query: str,
        calendar_id: str = "primary",
        max_results: int = 10,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search calendar events."""

    @abstractmethod
    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        calendar_id: str = "primary",
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a calendar event."""

    @abstractmethod
    async def update_event(
        self, event_id: str, calendar_id: str = "primary", **updates: Any
    ) -> Dict[str, Any]:
        """Update a calendar event."""

    @abstractmethod
    async def delete_event(self, event_id: str, calendar_id: str = "primary") -> bool:
        """Delete a calendar event."""

    @abstractmethod
    def parse_event_to_calendar_page(
        self, event_data: Dict[str, Any], page_uri: PageURI
    ) -> CalendarEventPage:
        """Parse provider-specific event data to CalendarEventPage."""


class BasePeopleClient(ABC):
    """Abstract base class for people/contacts API clients."""

    @abstractmethod
    async def get_contact(self, contact_id: str) -> Dict[str, Any]:
        """Get a contact by ID."""

    @abstractmethod
    async def search_contacts(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search contacts."""

    @abstractmethod
    async def list_contacts(
        self, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List contacts."""

    @abstractmethod
    async def create_contact(
        self, first_name: str, last_name: str, email: str
    ) -> Dict[str, Any]:
        """Create a new contact."""

    @abstractmethod
    async def update_contact(self, contact_id: str, **updates: Any) -> Dict[str, Any]:
        """Update a contact."""

    @abstractmethod
    async def delete_contact(self, contact_id: str) -> bool:
        """Delete a contact."""

    @abstractmethod
    def parse_contact_to_person_page(
        self, contact_data: Dict[str, Any], page_uri: PageURI
    ) -> PersonPage:
        """Parse provider-specific contact data to PersonPage."""


class BaseDocumentsClient(ABC):
    """Abstract base class for documents API clients."""

    @abstractmethod
    async def get_document(self, document_id: str) -> Dict[str, Any]:
        """Get a document by ID."""

    @abstractmethod
    async def list_documents(
        self, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """List documents."""

    @abstractmethod
    async def search_documents(
        self, query: str, max_results: int = 10, page_token: Optional[str] = None
    ) -> Dict[str, Any]:
        """Search documents."""

    @abstractmethod
    async def get_document_content(self, document_id: str) -> str:
        """Get full document content."""

    @abstractmethod
    async def create_document(
        self, title: str, content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new document."""

    @abstractmethod
    async def update_document(self, document_id: str, **updates: Any) -> Dict[str, Any]:
        """Update a document."""

    @abstractmethod
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document."""

    @abstractmethod
    async def parse_document_to_header_page(
        self, document_data: Dict[str, Any], page_uri: PageURI
    ) -> DocumentHeader:
        """Parse provider-specific document data to DocumentHeader."""

    @abstractmethod
    def parse_document_to_chunks(
        self, document_data: Dict[str, Any], header_uri: PageURI
    ) -> List[DocumentChunk]:
        """Parse provider-specific document data to DocumentChunk list."""


class BaseProviderClient(ABC):
    """Abstract base class for provider API clients that combines all service clients."""

    def __init__(self, auth_manager: BaseAuthManager):
        self.auth_manager = auth_manager

    @property
    @abstractmethod
    def email_client(self) -> BaseEmailClient:
        """Get email client instance."""

    @property
    @abstractmethod
    def calendar_client(self) -> BaseCalendarClient:
        """Get calendar client instance."""

    @property
    @abstractmethod
    def people_client(self) -> BasePeopleClient:
        """Get people client instance."""

    @property
    @abstractmethod
    def documents_client(self) -> BaseDocumentsClient:
        """Get documents client instance."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test connection to provider."""

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name (e.g., 'google', 'microsoft')."""
