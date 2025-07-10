# Adding New Services to PragaWeb

This guide provides comprehensive instructions on how to add new services to the PragaWeb project. PragaWeb uses a sophisticated service architecture that integrates with the Praga Core framework for document retrieval and LLM agent interactions.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Service Requirements](#service-requirements)
3. [Step-by-Step Guide](#step-by-step-guide)
4. [Code Examples](#code-examples)
5. [Testing Your Service](#testing-your-service)
6. [Best Practices](#best-practices)

## Architecture Overview

PragaWeb services follow these key architectural patterns:

- **Service Base Classes**: All services inherit from `ToolkitService` (which combines `ServiceContext` and `RetrieverToolkit`)
- **Auto-Registration**: Services automatically register themselves with the global context upon instantiation
- **Page System**: Services define custom Page types for their data structures
- **Tool Integration**: Services expose tools that LLM agents can use for retrieval operations
- **Action System**: Services can register actions that operate on their pages

## Service Requirements

To create a new service, you'll need:

1. **Service Class**: Inherits from `ToolkitService`
2. **Page Types**: Custom page classes extending `Page` for your data structures
3. **API Client**: (Optional) If integrating with external APIs
4. **Tools**: Methods decorated with `@tool()` for agent interactions
5. **Routes**: Page handlers registered with `@context.route()`
6. **Actions**: (Optional) Operations registered with `@context.action()`

## Step-by-Step Guide

### Step 1: Create Your Page Types

First, define the page types your service will work with. Create a new file `src/pragweb/your_service/page.py`:

```python
from datetime import datetime
from typing import List, Optional
from praga_core.types import Page, PageURI

class YourDataPage(Page):
    """Page representing your service's data."""
    
    # Define your page attributes
    title: str
    content: str
    created_at: datetime
    metadata: Optional[dict] = None
    
    def summary(self) -> str:
        """Return a summary of this page for display."""
        return f"{self.title} - Created: {self.created_at}"
```

### Step 2: Create Your Service Class

Create `src/pragweb/your_service/service.py`:

```python
import logging
from typing import List, Optional, Any
from praga_core.agents import PaginatedResponse, tool
from praga_core.types import PageURI
from pragweb.toolkit_service import ToolkitService
from .page import YourDataPage

logger = logging.getLogger(__name__)

class YourService(ToolkitService):
    """Service for managing your data."""
    
    def __init__(self, api_client: Optional[Any] = None) -> None:
        super().__init__(api_client)
        self._register_handlers()
        logger.info(f"{self.name} service initialized")
    
    @property
    def name(self) -> str:
        """Service name used for registration."""
        return "your_service"
    
    def _register_handlers(self) -> None:
        """Register page routes and actions with context."""
        ctx = self.context
        
        # Register page route handler
        @ctx.route(self.name, cache=True)
        async def handle_your_data(page_uri: PageURI) -> YourDataPage:
            return await self.create_data_page(page_uri)
        
        # Register an action (optional)
        @ctx.action()
        async def process_data(data: YourDataPage, operation: str) -> bool:
            """Process data with specified operation."""
            return await self._process_data_internal(data, operation)
    
    async def create_data_page(self, page_uri: PageURI) -> YourDataPage:
        """Create a YourDataPage from a URI."""
        data_id = page_uri.id
        
        # Fetch data from your source (API, database, etc.)
        if self.api_client:
            data = await self.api_client.get_data(data_id)
        else:
            # Mock data for example
            data = {
                "title": f"Data {data_id}",
                "content": "Sample content",
                "created_at": datetime.now()
            }
        
        return YourDataPage(
            uri=page_uri,
            title=data["title"],
            content=data["content"],
            created_at=data["created_at"]
        )
    
    @tool()
    async def search_data(
        self, 
        query: str, 
        cursor: Optional[str] = None
    ) -> PaginatedResponse[YourDataPage]:
        """Search for data matching the query.
        
        Args:
            query: Search query string
            cursor: Pagination cursor
            
        Returns:
            Paginated response of matching data pages
        """
        # Implement your search logic
        results = await self._search_internal(query, cursor)
        
        # Convert results to PageURIs
        uris = [
            PageURI(root=self.context.root, type=self.name, id=item["id"])
            for item in results["items"]
        ]
        
        # Resolve URIs to pages
        pages = await self.context.get_pages(uris)
        
        return PaginatedResponse(
            results=pages,
            next_cursor=results.get("next_cursor")
        )
    
    @tool()
    async def get_recent_data(
        self, 
        limit: int = 10,
        cursor: Optional[str] = None
    ) -> PaginatedResponse[YourDataPage]:
        """Get recent data items.
        
        Args:
            limit: Maximum number of items to return
            cursor: Pagination cursor
            
        Returns:
            Paginated response of recent data pages
        """
        # Implementation similar to search_data
        pass
    
    async def _process_data_internal(
        self, 
        data: YourDataPage, 
        operation: str
    ) -> bool:
        """Internal method for processing data."""
        try:
            # Implement your processing logic
            logger.info(f"Processing {data.uri} with operation: {operation}")
            return True
        except Exception as e:
            logger.error(f"Failed to process data: {e}")
            return False
```

### Step 3: Create an API Client (Optional)

If your service integrates with external APIs, create `src/pragweb/your_service/client.py`:

```python
import aiohttp
from typing import Any, Dict, Optional

class YourAPIClient:
    """Client for interacting with your external API."""
    
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def get_data(self, data_id: str) -> Dict[str, Any]:
        """Fetch data by ID from the API."""
        if not self.session:
            raise RuntimeError("Client not initialized")
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with self.session.get(
            f"{self.base_url}/data/{data_id}",
            headers=headers
        ) as response:
            response.raise_for_status()
            return await response.json()
    
    async def search(self, query: str, page_token: Optional[str] = None) -> Dict[str, Any]:
        """Search for data via the API."""
        params = {"q": query}
        if page_token:
            params["page_token"] = page_token
        
        # Implementation here
        pass
```

### Step 4: Initialize Your Service

Add your service initialization to the main application (e.g., in `app.py`):

```python
from pragweb.your_service.service import YourService
from pragweb.your_service.client import YourAPIClient

# In your initialization code:
async def initialize_services(context):
    # Create API client if needed
    your_api_client = YourAPIClient(
        api_key=os.environ.get("YOUR_API_KEY"),
        base_url="https://api.yourservice.com"
    )
    
    # Create and auto-register the service
    your_service = YourService(your_api_client)
    
    # The service is now available via context.get_service("your_service")
    
    # Return toolkit for agent integration
    return your_service.toolkit
```

### Step 5: Integrate with the Agent

Add your service's toolkit to the agent configuration:

```python
# Collect all toolkits
all_toolkits = [
    gmail_service.toolkit,
    calendar_service.toolkit,
    your_service.toolkit,  # Add your toolkit here
    # ... other toolkits
]

# Configure the agent
agent = ReactAgent(
    model=config.retriever_agent_model,
    toolkits=all_toolkits,
    max_iterations=config.retriever_max_iterations,
)
context.retriever = agent
```

## Code Examples

### Example: Slack Service

Here's a minimal example of adding a Slack service:

```python
# src/pragweb/slack/page.py
from datetime import datetime
from praga_core.types import Page

class SlackMessagePage(Page):
    """Page representing a Slack message."""
    channel: str
    author: str
    text: str
    timestamp: datetime
    thread_ts: Optional[str] = None
    
    def summary(self) -> str:
        return f"[{self.channel}] {self.author}: {self.text[:50]}..."

# src/pragweb/slack/service.py
from pragweb.toolkit_service import ToolkitService
from praga_core.agents import tool, PaginatedResponse
from .page import SlackMessagePage

class SlackService(ToolkitService):
    """Service for Slack integration."""
    
    @property
    def name(self) -> str:
        return "slack"
    
    def _register_handlers(self) -> None:
        ctx = self.context
        
        @ctx.route("slack_message", cache=True)
        async def handle_message(page_uri: PageURI) -> SlackMessagePage:
            return await self.create_message_page(page_uri)
    
    @tool()
    async def search_messages(
        self, 
        query: str,
        channel: Optional[str] = None,
        cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Search Slack messages."""
        # Implementation here
        pass
    
    @tool()
    async def get_channel_messages(
        self,
        channel: str,
        limit: int = 20,
        cursor: Optional[str] = None
    ) -> PaginatedResponse[SlackMessagePage]:
        """Get recent messages from a channel."""
        # Implementation here
        pass
```

## Testing Your Service

Create comprehensive tests for your service:

```python
# tests/services/test_your_service.py
import pytest
from praga_core import ServerContext, set_global_context, clear_global_context
from pragweb.your_service.service import YourService
from pragweb.your_service.page import YourDataPage

@pytest.fixture
async def service():
    """Create service with test context."""
    clear_global_context()
    context = await ServerContext.create(root="test://example")
    set_global_context(context)
    
    service = YourService()
    yield service
    
    clear_global_context()

@pytest.mark.asyncio
async def test_service_registration(service):
    """Test that service registers correctly."""
    context = service.context
    assert context.get_service("your_service") is service

@pytest.mark.asyncio
async def test_search_data(service):
    """Test searching for data."""
    response = await service.search_data("test query")
    assert isinstance(response.results, list)
    assert all(isinstance(page, YourDataPage) for page in response.results)

@pytest.mark.asyncio
async def test_page_creation(service):
    """Test creating a page from URI."""
    uri = PageURI(root="test://example", type="your_service", id="123")
    page = await service.create_data_page(uri)
    
    assert isinstance(page, YourDataPage)
    assert page.uri == uri
```

## Best Practices

1. **Consistent Naming**: Use clear, consistent names for your service, page types, and tools
2. **Error Handling**: Always handle API errors gracefully and log appropriately
3. **Pagination**: Implement pagination for search/list operations using `PaginatedResponse`
4. **Type Safety**: Use type hints throughout and run mypy for type checking
5. **Async First**: All operations should be async for consistency
6. **Documentation**: Document all tools with clear docstrings for LLM understanding
7. **Testing**: Write comprehensive tests including unit and integration tests
8. **Logging**: Use appropriate logging levels for debugging and monitoring
9. **Security**: Never log sensitive information like API keys or user data
10. **Cache Control**: Use `cache=True` for immutable data, `cache=False` for frequently changing data

## Common Patterns

### Pattern 1: Bulk Operations

When you need to operate on multiple items:

```python
@tool()
async def bulk_process(
    self,
    item_ids: List[str],
    operation: str
) -> Dict[str, bool]:
    """Process multiple items in bulk."""
    uris = [
        PageURI(root=self.context.root, type=self.name, id=item_id)
        for item_id in item_ids
    ]
    
    pages = await self.context.get_pages(uris)
    results = {}
    
    for page in pages:
        success = await self._process_internal(page, operation)
        results[page.uri.id] = success
    
    return results
```

### Pattern 2: Cross-Service Integration

When your service needs to interact with other services:

```python
async def enrich_with_person_data(self, data: YourDataPage) -> YourDataPage:
    """Enrich data with person information."""
    people_service = self.context.get_service("people")
    
    # Search for person by email
    person_results = await people_service.search_existing_records(data.author_email)
    if person_results:
        data.author_details = person_results[0]
    
    return data
```

### Pattern 3: Webhook/Event Handling

For services that need to handle external events:

```python
async def handle_webhook(self, event_data: Dict[str, Any]) -> None:
    """Handle incoming webhook events."""
    event_type = event_data.get("type")
    
    if event_type == "data_created":
        # Create a page for the new data
        uri = PageURI(
            root=self.context.root,
            type=self.name,
            id=event_data["id"]
        )
        page = await self.create_data_page(uri)
        
        # Cache it
        await self.context.page_cache.set(page)
```

## Conclusion

Adding new services to PragaWeb follows a consistent pattern that ensures proper integration with the framework's document retrieval and LLM agent capabilities. By following this guide, you can create services that seamlessly integrate with the existing architecture while maintaining code quality and consistency.

Remember to:
- Follow the established patterns from existing services
- Write comprehensive tests
- Document your tools clearly for LLM understanding
- Handle errors gracefully
- Maintain type safety throughout

For examples, refer to the existing service implementations in `src/pragweb/google_api/` directory.