# Project Overview

This document provides a comprehensive overview of the Praga Web Server architecture, core concepts, and design principles.

## Table of Contents

1. [Introduction](#introduction)
2. [Architecture Overview](#architecture-overview)
3. [Core Concepts](#core-concepts)
4. [Component Deep Dive](#component-deep-dive)
5. [Data Flow](#data-flow)
6. [Design Principles](#design-principles)
7. [Use Cases](#use-cases)

## Introduction

Praga Web Server is a framework for building document retrieval toolkits and agents for LLM applications. It implements the LLMRP (LLM Retrieval Protocol) to provide standardized document retrieval over HTTP, enabling LLM agents to seamlessly interact with various data sources.

### Key Goals

- **Unified Interface**: Provide a consistent API for accessing diverse data sources
- **LLM Integration**: Design tools and actions optimized for LLM agent interaction
- **Extensibility**: Easy addition of new services and data sources
- **Performance**: Async-first architecture for concurrent operations
- **Type Safety**: Comprehensive type hints and validation

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        External Clients                          │
│                    (LLMs, Applications, APIs)                    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ServerContext                               │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │   Router    │  │Action Executor│  │   Retriever Agent      │ │
│  │             │  │              │  │   (ReAct Pattern)      │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────────┐
│                        Services Layer                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
│  │   Gmail    │  │  Calendar  │  │Google Docs │  │  People  │ │
│  │  Service   │  │  Service   │  │  Service   │  │ Service  │ │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────────┐
│                      Page Cache Layer                            │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐ │
│  │   Storage  │  │  Registry  │  │ Validator  │  │Provenance│ │
│  │   (SQLite) │  │            │  │            │  │ Manager  │ │
│  └────────────┘  └────────────┘  └────────────┘  └──────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Descriptions

1. **External Clients**: LLM agents, applications, or APIs that interact with the system
2. **ServerContext**: Central orchestrator managing routing, actions, and agent interactions
3. **Services Layer**: Pluggable services that integrate with external APIs and data sources
4. **Page Cache Layer**: Persistent storage and management of retrieved documents

## Core Concepts

### 1. Pages

Pages are the fundamental unit of data in the system. Every piece of information is represented as a Page object.

```python
class Page(BaseModel):
    """Base class for all page types."""
    uri: PageURI  # Unique identifier
    
class EmailPage(Page):
    """Specific page type for emails."""
    subject: str
    sender: str
    body: str
    time: datetime
```

**Key characteristics:**
- Immutable data structures
- Strongly typed with Pydantic
- Cacheable by default
- Support for relationships (provenance)

### 2. PageURI

PageURI provides a unique, URL-like identifier for every page in the system.

```python
PageURI(
    root="pragweb://localhost",  # System root
    type="email",                # Page type
    id="msg_123",               # Unique ID
    version=1                   # Version number
)
# Serializes to: pragweb://localhost/email/msg_123#v1
```

### 3. Services

Services are the bridge between external data sources and the page system.

```python
class YourService(ToolkitService):
    """Service implementation pattern."""
    
    @property
    def name(self) -> str:
        return "your_service"
    
    @tool()
    async def search_data(self, query: str) -> PaginatedResponse[YourPage]:
        """Tool exposed to LLM agents."""
        pass
```

**Service responsibilities:**
- Integrate with external APIs
- Create Page objects from raw data
- Register page routes and handlers
- Expose tools for LLM agents
- Define actions for page manipulation

### 4. Tools and Actions

**Tools** are read operations exposed to LLM agents:
```python
@tool()
async def search_emails(self, query: str) -> PaginatedResponse[EmailPage]:
    """Search for emails matching query."""
    pass
```

**Actions** are write operations that modify state:
```python
@context.action()
async def send_email(person: PersonPage, subject: str, message: str) -> bool:
    """Send an email to a person."""
    pass
```

### 5. Context System

The context system provides global access to services and functionality:

```python
# Global context pattern
context = await ServerContext.create(root="pragweb://localhost")
set_global_context(context)

# Services auto-register on instantiation
gmail_service = GmailService(api_client)  # Automatically registered

# Access from anywhere
context = get_global_context()
service = context.get_service("email")
```

## Component Deep Dive

### ServerContext

The `ServerContext` is the central orchestrator of the system:

```python
class ServerContext(ActionExecutorMixin):
    """Main context managing all system components."""
    
    # Core components
    root: str                    # System root URI
    page_cache: PageCache       # Cache instance
    retriever: Optional[Agent]  # LLM agent
    
    # Service management
    async def register_service(name: str, service: Service)
    def get_service(name: str) -> Service
    
    # Page operations
    async def get_page(uri: PageURI) -> Page
    async def search(query: str) -> SearchResult
    
    # Routing
    def route(page_type: str, cache: bool = True)
```

### ActionExecutorMixin

Provides action registration and execution capabilities:

```python
class ActionExecutorMixin:
    """Mixin for action registration and execution."""
    
    def action(self) -> Callable:
        """Decorator for registering actions."""
        
    async def invoke_action(
        self,
        action_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Execute a registered action."""
```

**Key feature**: Automatic signature transformation
- Actions are defined with `Page` parameters
- External API accepts only `PageURI` parameters
- Automatic bulk fetching and resolution

### PageCache

The caching layer with separated concerns:

```python
class PageCache:
    """Main cache interface."""
    
    def __init__(self, storage, registry, validator, provenance):
        self.storage = storage      # CRUD operations
        self.registry = registry    # Type registration
        self.validator = validator  # Validation logic
        self.provenance = provenance # Relationship tracking
    
    async def get(uri: PageURI) -> Optional[Page]
    async def set(page: Page) -> None
    async def search(query: str) -> List[Page]
```

### RetrieverToolkit

Base class for creating tool collections:

```python
class RetrieverToolkit:
    """Base class for retriever toolkits."""
    
    def list_tools(self) -> List[ToolInfo]:
        """List all available tools."""
        
    async def invoke_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Any:
        """Invoke a specific tool."""
```

### ReactAgent

Implements the ReAct (Reasoning + Acting) pattern for LLM agents:

```python
class ReactAgent(RetrieverAgentBase):
    """ReAct pattern implementation."""
    
    def __init__(
        self,
        model: str,
        toolkits: List[RetrieverToolkit],
        max_iterations: int = 5
    ):
        self.model = model
        self.toolkits = toolkits
        self.max_iterations = max_iterations
    
    async def search(self, query: str) -> SearchResult:
        """Execute ReAct loop to answer query."""
```

## Data Flow

### 1. Search Query Flow

```
User Query → ServerContext.search()
    ↓
ReactAgent.search()
    ↓
ReAct Loop:
    1. Thought: Analyze query
    2. Action: Choose tool
    3. Observation: Execute tool
    4. Repeat until answer found
    ↓
Return SearchResult with PageReferences
```

### 2. Page Retrieval Flow

```
PageURI → ServerContext.get_page()
    ↓
Check PageCache
    ↓
If not cached:
    Router → Service Handler → External API
    ↓
Create Page object
    ↓
Store in PageCache
    ↓
Return Page
```

### 3. Action Execution Flow

```
Action Request (with PageURIs) → ActionExecutor
    ↓
Resolve PageURIs to Pages (bulk fetch)
    ↓
Execute action with Page objects
    ↓
Update state/external systems
    ↓
Return result
```

## Design Principles

### 1. Separation of Concerns

Each component has a single, well-defined responsibility:
- Services: External integration
- Pages: Data representation
- Cache: Storage and retrieval
- Context: Orchestration
- Agent: Query understanding

### 2. Async-First

All I/O operations are asynchronous:
```python
async def get_page(uri: PageURI) -> Page
async def search(query: str) -> SearchResult
async def invoke_action(name: str, args: Dict) -> Any
```

### 3. Type Safety

Comprehensive type hints throughout:
```python
def register_service(self, name: str, service: Service) -> None:
async def get_pages(self, uris: List[PageURI]) -> List[Page]:
```

### 4. Extensibility

Easy to add new:
- Services (implement Service interface)
- Page types (extend Page class)
- Tools (use @tool decorator)
- Actions (use @action decorator)

### 5. Clean API Boundaries

Clear separation between internal and external APIs:
- External: PageURI-only interface
- Internal: Page object manipulation
- Automatic transformation at boundaries

## Use Cases

### 1. Email Assistant

```python
# Search for important emails
result = await context.search(
    "unread emails from my manager about the Q4 report"
)

# Reply to an email thread
await context.invoke_action(
    "reply_to_email_thread",
    {
        "thread": thread_uri,
        "message": "Thanks for the update. I'll review and respond by EOD."
    }
)
```

### 2. Calendar Management

```python
# Find available meeting slots
result = await context.search(
    "free slots next week for a 1-hour meeting with John"
)

# Schedule a meeting
await context.invoke_action(
    "create_event",
    {
        "calendar": calendar_uri,
        "title": "Project Review",
        "start_time": "2024-01-15T14:00:00",
        "attendees": [john_uri, sarah_uri]
    }
)
```

### 3. Document Collaboration

```python
# Search across documents
result = await context.search(
    "design documents mentioning the new API architecture"
)

# Create a new document
await context.invoke_action(
    "create_document",
    {
        "title": "API Design Proposal",
        "content": "## Overview\n\nThis document outlines..."
    }
)
```

### 4. Cross-Service Workflows

```python
# Complex workflow: Schedule meeting based on email
result = await context.search(
    "latest email from Sarah about scheduling a design review"
)

# Extract meeting details from email
email = await context.get_page(result.results[0].uri)

# Find available slots
slots = await context.search(
    f"free slots this week for meeting with {email.sender}"
)

# Create calendar event
await context.invoke_action(
    "create_event_from_email",
    {
        "email": email.uri,
        "slot": slots.results[0].uri
    }
)
```

## Conclusion

Praga Web Server provides a powerful, extensible framework for building LLM-powered applications that interact with multiple data sources. Its clean architecture, strong typing, and async-first design make it suitable for both simple integrations and complex, cross-service workflows.

The combination of the page system, service architecture, and LLM agent integration creates a flexible platform that can adapt to various use cases while maintaining consistency and type safety throughout the system.