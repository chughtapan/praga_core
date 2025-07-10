# API Reference

This document provides a comprehensive API reference for the Praga Web Server framework.

## Table of Contents

1. [Core Classes](#core-classes)
2. [Page System](#page-system)
3. [Service API](#service-api)
4. [Context API](#context-api)
5. [Agent API](#agent-api)
6. [Cache API](#cache-api)
7. [Tool System](#tool-system)
8. [Action System](#action-system)

## Core Classes

### ServerContext

The main orchestrator for the Praga system.

```python
class ServerContext(ActionExecutorMixin):
    """Server context managing services, routing, and caching."""
    
    # Initialization
    @classmethod
    async def create(
        cls,
        root: str,
        cache_url: str = "sqlite:///:memory:",
        retriever: Optional[RetrieverAgentBase] = None
    ) -> "ServerContext":
        """Create a new ServerContext instance.
        
        Args:
            root: Root URI for the server (e.g., "pragweb://localhost")
            cache_url: SQLite database URL for page cache
            retriever: Optional retriever agent instance
            
        Returns:
            Initialized ServerContext instance
        """
    
    # Service Management
    def register_service(self, name: str, service: Service) -> None:
        """Register a service with the context.
        
        Args:
            name: Service name for registration
            service: Service instance to register
            
        Raises:
            ValueError: If service name is already registered
        """
    
    def get_service(self, name: str) -> Service:
        """Get a registered service by name.
        
        Args:
            name: Service name
            
        Returns:
            Service instance
            
        Raises:
            KeyError: If service not found
        """
    
    # Page Operations
    async def get_page(self, uri: PageURI) -> Page:
        """Get a single page by URI.
        
        Args:
            uri: Page URI
            
        Returns:
            Page instance
            
        Raises:
            PageNotFoundError: If page cannot be retrieved
        """
    
    async def get_pages(self, uris: List[PageURI]) -> List[Page]:
        """Get multiple pages by URIs (bulk operation).
        
        Args:
            uris: List of page URIs
            
        Returns:
            List of Page instances in same order as URIs
        """
    
    # Search
    async def search(self, query: str) -> SearchResult:
        """Search for pages using natural language query.
        
        Args:
            query: Natural language search query
            
        Returns:
            SearchResult with matching page references
        """
    
    # Routing
    def route(
        self,
        page_type: str,
        cache: bool = True
    ) -> Callable:
        """Decorator for registering page handlers.
        
        Args:
            page_type: Type identifier for pages
            cache: Whether to cache pages of this type
            
        Returns:
            Decorator function
        """
```

### Service

Abstract base class for all services.

```python
class Service(ABC):
    """Abstract service interface."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Service name for registration.
        
        Returns:
            Unique service identifier
        """
```

### ServiceContext

Convenience class combining Service and ContextMixin.

```python
class ServiceContext(Service, ContextMixin):
    """Service with automatic context registration."""
    
    def __init__(
        self,
        api_client: Any = None,
        *args: Any,
        **kwargs: Any
    ) -> None:
        """Initialize service and auto-register with context.
        
        Args:
            api_client: Optional API client instance
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments
        """
    
    @property
    def context(self) -> ServerContext:
        """Access the global ServerContext instance."""
    
    @property
    def page_cache(self) -> PageCache:
        """Access the global PageCache instance."""
```

## Page System

### Page

Base class for all page types.

```python
class Page(BaseModel):
    """Base class for all pages in the system."""
    
    uri: PageURI
    """Unique identifier for this page."""
    
    def summary(self) -> str:
        """Return a human-readable summary of this page.
        
        Returns:
            Summary string for display
        """
```

### PageURI

Unique identifier for pages.

```python
class PageURI(BaseModel):
    """URI-like identifier for pages."""
    
    root: str
    """Root URI (e.g., 'pragweb://localhost')"""
    
    type: str
    """Page type identifier"""
    
    id: str
    """Unique ID within the type"""
    
    version: int = 1
    """Version number"""
    
    def __str__(self) -> str:
        """String representation as URI.
        
        Returns:
            URI string (e.g., 'pragweb://localhost/email/123#v1')
        """
    
    @classmethod
    def from_string(cls, uri_str: str) -> "PageURI":
        """Parse PageURI from string.
        
        Args:
            uri_str: URI string to parse
            
        Returns:
            PageURI instance
            
        Raises:
            ValueError: If URI format is invalid
        """
```

### PageReference

Reference to a page with search relevance.

```python
class PageReference(BaseModel):
    """Reference to a page with search metadata."""
    
    uri: PageURI
    """URI of the referenced page"""
    
    score: float = 0.0
    """Relevance score (0.0-1.0)"""
    
    explanation: Optional[str] = None
    """Explanation of why this page matches"""
```

### Common Page Types

```python
class EmailPage(Page):
    """Page representing an email."""
    
    message_id: str
    thread_id: str
    subject: str
    sender: str
    recipients: List[str]
    cc_list: List[str] = []
    body: str
    time: datetime
    permalink: str

class CalendarEventPage(Page):
    """Page representing a calendar event."""
    
    event_id: str
    calendar_id: str
    summary: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    attendees: List[str] = []
    location: Optional[str]
    permalink: str

class PersonPage(Page):
    """Page representing a person/contact."""
    
    resource_name: str
    display_name: str
    given_name: Optional[str]
    family_name: Optional[str]
    email: str
    phone_numbers: List[str] = []
    organization: Optional[str]
    title: Optional[str]
```

## Service API

### ToolkitService

Base class for services with toolkit functionality.

```python
class ToolkitService(ServiceContext, RetrieverToolkit):
    """Service with integrated toolkit functionality."""
    
    @property
    def toolkit(self) -> RetrieverToolkit:
        """Get the toolkit for this service.
        
        Returns:
            Self, as this class is both service and toolkit
        """
    
    @property
    def toolkits(self) -> List[RetrieverToolkit]:
        """Get all toolkits this service provides.
        
        Returns:
            List containing this service's toolkit
        """
```

### Service Implementation Pattern

```python
class YourService(ToolkitService):
    """Example service implementation."""
    
    def __init__(self, api_client: Optional[Any] = None) -> None:
        """Initialize service.
        
        Args:
            api_client: Optional API client for external integration
        """
        super().__init__(api_client)
        self._register_handlers()
    
    @property
    def name(self) -> str:
        """Service name for registration."""
        return "your_service"
    
    def _register_handlers(self) -> None:
        """Register page handlers and actions."""
        ctx = self.context
        
        @ctx.route(self.name, cache=True)
        async def handle_page(page_uri: PageURI) -> YourPage:
            """Handle page retrieval."""
            return await self.create_page(page_uri)
    
    async def create_page(self, page_uri: PageURI) -> YourPage:
        """Create a page from URI.
        
        Args:
            page_uri: URI of the page to create
            
        Returns:
            Created page instance
        """
```

## Context API

### Global Context Functions

```python
def set_global_context(context: ServerContext) -> None:
    """Set the global ServerContext instance.
    
    Args:
        context: Context instance to set as global
        
    Raises:
        RuntimeError: If global context already set
    """

def get_global_context() -> ServerContext:
    """Get the global ServerContext instance.
    
    Returns:
        Global context instance
        
    Raises:
        RuntimeError: If global context not set
    """

def clear_global_context() -> None:
    """Clear the global context (useful for testing)."""

def has_global_context() -> bool:
    """Check if global context is set.
    
    Returns:
        True if global context exists
    """
```

### ContextMixin

```python
class ContextMixin:
    """Mixin providing access to global context."""
    
    @property
    def context(self) -> ServerContext:
        """Access the global ServerContext instance.
        
        Returns:
            Global context
            
        Raises:
            RuntimeError: If global context not set
        """
```

## Agent API

### RetrieverAgentBase

```python
class RetrieverAgentBase(ABC):
    """Base class for retriever agents."""
    
    @abstractmethod
    async def search(self, query: str) -> SearchResult:
        """Search for pages matching query.
        
        Args:
            query: Natural language search query
            
        Returns:
            Search results with page references
        """
```

### ReactAgent

```python
class ReactAgent(RetrieverAgentBase):
    """ReAct pattern implementation for retrieval."""
    
    def __init__(
        self,
        model: str = "gpt-4",
        toolkits: List[RetrieverToolkit] = None,
        max_iterations: int = 5,
        temperature: float = 0.0
    ):
        """Initialize ReAct agent.
        
        Args:
            model: OpenAI model name
            toolkits: List of toolkits to use
            max_iterations: Maximum ReAct loop iterations
            temperature: LLM temperature setting
        """
    
    async def search(self, query: str) -> SearchResult:
        """Execute ReAct loop to answer query."""
```

### SearchResult

```python
class SearchResult(BaseModel):
    """Result of a search operation."""
    
    query: str
    """Original search query"""
    
    results: List[PageReference]
    """List of matching page references"""
    
    metadata: Dict[str, Any] = {}
    """Additional metadata about the search"""
```

## Cache API

### PageCache

```python
class PageCache:
    """Async page cache with SQLite backend."""
    
    @classmethod
    async def create(cls, db_url: str) -> "PageCache":
        """Create and initialize page cache.
        
        Args:
            db_url: SQLite database URL
            
        Returns:
            Initialized cache instance
        """
    
    async def get(self, uri: PageURI) -> Optional[Page]:
        """Get page from cache.
        
        Args:
            uri: Page URI
            
        Returns:
            Page if found, None otherwise
        """
    
    async def set(
        self,
        page: Page,
        provenance: Optional[List[PageURI]] = None
    ) -> None:
        """Store page in cache.
        
        Args:
            page: Page to store
            provenance: Optional related page URIs
        """
    
    async def delete(self, uri: PageURI) -> bool:
        """Delete page from cache.
        
        Args:
            uri: Page URI to delete
            
        Returns:
            True if deleted, False if not found
        """
    
    async def search(
        self,
        query: str,
        page_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Page]:
        """Search cache with SQL query.
        
        Args:
            query: SQL WHERE clause
            page_type: Optional type filter
            limit: Maximum results
            
        Returns:
            List of matching pages
        """
```

## Tool System

### Tool Decorator

```python
def tool(
    name: Optional[str] = None,
    description: Optional[str] = None
) -> Callable:
    """Decorator for marking methods as tools.
    
    Args:
        name: Optional tool name (defaults to method name)
        description: Optional description (defaults to docstring)
        
    Returns:
        Decorator function
    """
```

### Tool Implementation

```python
class YourService(ToolkitService):
    
    @tool()
    async def search_items(
        self,
        query: str,
        filter_type: Optional[str] = None,
        cursor: Optional[str] = None
    ) -> PaginatedResponse[YourPage]:
        """Search for items matching query.
        
        Args:
            query: Search query
            filter_type: Optional type filter
            cursor: Pagination cursor
            
        Returns:
            Paginated response with results
        """
```

### PaginatedResponse

```python
class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""
    
    results: List[T]
    """List of results for current page"""
    
    next_cursor: Optional[str] = None
    """Cursor for next page (if any)"""
    
    total_count: Optional[int] = None
    """Total count of all results (if known)"""
```

### RetrieverToolkit

```python
class RetrieverToolkit:
    """Base class for tool collections."""
    
    def list_tools(self) -> List[ToolInfo]:
        """List all available tools.
        
        Returns:
            List of tool information
        """
    
    async def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Invoke a specific tool.
        
        Args:
            tool_name: Name of tool to invoke
            arguments: Tool arguments
            
        Returns:
            Tool result
            
        Raises:
            ValueError: If tool not found
        """
```

### ToolInfo

```python
class ToolInfo(BaseModel):
    """Information about a tool."""
    
    name: str
    """Tool name"""
    
    description: str
    """Tool description"""
    
    parameters: Dict[str, Any]
    """JSON schema for parameters"""
    
    returns: Dict[str, Any]
    """JSON schema for return type"""
```

## Action System

### Action Decorator

```python
def action(
    name: Optional[str] = None
) -> Callable:
    """Decorator for registering actions.
    
    Actions are methods that can modify state and are exposed
    through the action executor system.
    
    Args:
        name: Optional action name (defaults to method name)
        
    Returns:
        Decorator function
    """
```

### Action Implementation

```python
@context.action()
async def send_email(
    person: PersonPage,
    subject: str,
    message: str,
    cc_list: Optional[List[PersonPage]] = None
) -> bool:
    """Send an email to a person.
    
    Args:
        person: Primary recipient
        subject: Email subject
        message: Email body
        cc_list: Optional CC recipients
        
    Returns:
        True if sent successfully
    """
```

### ActionExecutorMixin

```python
class ActionExecutorMixin:
    """Mixin for action registration and execution."""
    
    def action(self, name: Optional[str] = None) -> Callable:
        """Decorator for registering actions."""
    
    async def invoke_action(
        self,
        action_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Execute a registered action.
        
        Args:
            action_name: Name of action to execute
            arguments: Action arguments (PageURIs only)
            
        Returns:
            Action result
            
        Raises:
            ValueError: If action not found
            TypeError: If arguments contain Page objects
        """
    
    def list_actions(self) -> List[ActionInfo]:
        """List all registered actions.
        
        Returns:
            List of action information
        """
```

### ActionInfo

```python
class ActionInfo(BaseModel):
    """Information about an action."""
    
    name: str
    """Action name"""
    
    description: str
    """Action description from docstring"""
    
    parameters: Dict[str, Any]
    """Parameter information"""
    
    returns: str
    """Return type description"""
```

## Exception Types

```python
class PragaError(Exception):
    """Base exception for all Praga errors."""

class PageNotFoundError(PragaError):
    """Page could not be found or created."""

class ServiceError(PragaError):
    """Service-related error."""

class CacheError(PragaError):
    """Cache operation error."""

class ActionError(PragaError):
    """Action execution error."""

class ToolError(PragaError):
    """Tool invocation error."""

class ProvenanceError(PragaError):
    """Provenance tracking error."""
```

## Usage Examples

### Basic Setup

```python
import asyncio
from praga_core import ServerContext, set_global_context
from pragweb.google_api.gmail import GmailService
from pragweb.google_api.client import GoogleAPIClient

async def main():
    # Initialize context
    context = await ServerContext.create(
        root="pragweb://localhost",
        cache_url="sqlite:///cache.db"
    )
    set_global_context(context)
    
    # Initialize services
    google_client = GoogleAPIClient()
    gmail_service = GmailService(google_client)
    
    # Use the service
    emails = await gmail_service.get_recent_emails(days=7)
    for email in emails.results:
        print(f"- {email.subject} from {email.sender}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Custom Service

```python
from pragweb.toolkit_service import ToolkitService
from praga_core.agents import tool, PaginatedResponse
from praga_core.types import Page, PageURI

class CustomPage(Page):
    title: str
    content: str

class CustomService(ToolkitService):
    @property
    def name(self) -> str:
        return "custom"
    
    def _register_handlers(self) -> None:
        @self.context.route("custom", cache=True)
        async def handle_custom(uri: PageURI) -> CustomPage:
            # Fetch and return custom page
            pass
    
    @tool()
    async def search_custom(
        self, query: str
    ) -> PaginatedResponse[CustomPage]:
        # Implement search logic
        pass
```

### Using Actions

```python
# Invoke an action
result = await context.invoke_action(
    "send_email",
    {
        "person": person_uri,
        "subject": "Hello",
        "message": "This is a test email"
    }
)
```

This API reference covers the main components and interfaces of the Praga Web Server framework. For specific implementation details, refer to the source code and examples.