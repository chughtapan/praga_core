# Page Tracking Mechanism with Parent-Child Relationships

## Current Implementation Analysis

### Existing Infrastructure

The codebase already has a robust page caching system built on SQLAlchemy with automatic schema generation from Pydantic models:

1. **Page Cache System** (`src/praga_core/page_cache.py`):
   - Automatic SQL table generation from Page models
   - URI-based primary keys using PageURI format (`root/type:id@version`)
   - Type-safe querying with SQLAlchemy expressions
   - Support for PageURI fields with automatic serialization/deserialization

2. **Page Types** (`src/praga_core/types.py`):
   - Base `Page` class with structured `PageURI` identifiers
   - Support for complex field types including nested PageURIs
   - Metadata tracking capabilities

### Current Parent-Child Patterns

The codebase already demonstrates several parent-child relationship patterns:

#### 1. Google Docs: Header-Chunk Relationship
```python
class GDocHeader(Page):
    chunk_uris: List[PageURI] = Field(description="List of chunk URIs for this document")

class GDocChunk(Page):
    header_uri: PageURI = Field(description="URI of the parent document header")
    prev_chunk_uri: Optional[PageURI] = Field(None, description="URI of previous chunk")
    next_chunk_uri: Optional[PageURI] = Field(None, description="URI of next chunk")
```

#### 2. Gmail: Email-Thread Relationship (Separate Assembly)
```python
class EmailPage(Page):
    @computed_field
    def thread_uri(self) -> PageURI:
        return PageURI(root=self.uri.root, type="email_thread", id=self.thread_id, version=self.uri.version)

class EmailThreadPage(Page):
    emails: List[EmailSummary] = Field(description="List of compressed email summaries in this thread")
```

## Proposed Enhancement: Formal Parent-Child Tracking

### Requirements Implementation

Based on the specifications, here's the recommended implementation:

#### 1. Enhanced Page Base Class

```python
class Page(BaseModel, ABC):
    uri: Annotated[PageURI, BeforeValidator(PageURI.parse)] = Field(
        description="Structured URI for the page"
    )
    parent_uri: Optional[PageURI] = Field(
        None, 
        description="URI of the parent page (for derived/chunk relationships only)"
    )
    _metadata: PageMetadata = PrivateAttr(default_factory=lambda: PageMetadata(token_count=None))
```

#### 2. Enhanced PageCache with Relationship Validation

```python
class PageCache:
    def store_page(self, page: Page, parent_uri: Optional[PageURI] = None) -> bool:
        """Store a page with optional parent relationship validation."""
        
        # If parent_uri is provided, perform pre-checks
        if parent_uri is not None:
            self._validate_parent_child_relationship(page, parent_uri)
            page.parent_uri = parent_uri
        
        # Existing storage logic...
    
    def _validate_parent_child_relationship(self, child_page: Page, parent_uri: PageURI) -> None:
        """Validate parent-child relationship according to requirements."""
        
        # Pre-check 1: Ensure parent exists in cache
        parent_page = self._get_page_by_uri(parent_uri)
        if parent_page is None:
            raise ValueError(f"Parent page {parent_uri} not found in cache")
        
        # Pre-check 2: Ensure parent has fixed version number
        if parent_uri.version <= 0:
            raise ValueError(f"Parent URI must have a fixed version number: {parent_uri}")
        
        # Pre-check 3: Ensure child does not exist in cache
        if self._get_page_by_uri(child_page.uri) is not None:
            raise ValueError(f"Child page {child_page.uri} already exists in cache")
        
        # Pre-check 4: Check that child and parent are not the same page type
        parent_type = parent_uri.type
        child_type = child_page.uri.type
        if parent_type == child_type:
            raise ValueError(f"Parent and child cannot be the same page type: {parent_type}")
        
        # Pre-check 5: Check for potential loops (though unlikely since child should not exist)
        if self._would_create_loop(child_page.uri, parent_uri):
            raise ValueError(f"Adding relationship would create a loop")
    
    def _would_create_loop(self, child_uri: PageURI, parent_uri: PageURI) -> bool:
        """Check if adding this relationship would create a loop."""
        # Walk up the parent chain from parent_uri
        current_uri = parent_uri
        visited = set()
        
        while current_uri is not None:
            if current_uri in visited:
                return True  # Already found a loop
            if current_uri == child_uri:
                return True  # Would create a loop
            
            visited.add(current_uri)
            current_page = self._get_page_by_uri(current_uri)
            current_uri = current_page.parent_uri if current_page else None
        
        return False
    
    def get_children(self, parent_uri: PageURI) -> List[Page]:
        """Get all child pages of a given parent."""
        return self.find_pages_by_attribute(
            Page,  # This would need to be refined for specific types
            lambda t: t.parent_uri == str(parent_uri)
        )
    
    def get_parent(self, child_uri: PageURI) -> Optional[Page]:
        """Get the parent page of a given child."""
        child_page = self._get_page_by_uri(child_uri)
        if child_page and child_page.parent_uri:
            return self._get_page_by_uri(child_page.parent_uri)
        return None
```

### Example Implementations

#### 1. Slack Pages (Complex Hierarchy)

```python
class SlackChannel(Page):
    """Slack channel - can have conversations as children."""
    channel_id: str
    name: str
    description: Optional[str] = None

class SlackConversation(Page):
    """Slack conversation - derived from SlackChannel."""
    conversation_id: str
    channel_id: str
    participants: List[str]
    # parent_uri points to SlackChannel

class SlackMessage(Page):
    """Slack message - assembled separately, no parent relationship."""
    message_id: str
    conversation_id: str
    sender: str
    content: str
    timestamp: datetime

class SlackThread(Page):
    """Slack thread - assembled separately, no parent relationship."""
    thread_id: str
    parent_message_id: str
    messages: List[str]
```

**Relationship Rules:**
- `SlackConversation` can have `SlackChannel` as parent (chunks derived from channel)
- `SlackMessage` and `SlackThread` have NO parent relationships (assembled separately)

#### 2. Google Docs (Current Pattern Enhanced)

```python
class GDocHeader(Page):
    """Google Docs header - no parent."""
    document_id: str
    title: str
    chunk_count: int

class GDocChunk(Page):
    """Google Docs chunk - derived from header."""
    chunk_index: int
    content: str
    # parent_uri points to GDocHeader
```

**Relationship Rules:**
- `GDocChunk` can have `GDocHeader` as parent (chunks derived from document)

#### 3. Email (Current Pattern - No Parent Relationships)

```python
class EmailPage(Page):
    """Email - assembled separately, no parent relationship."""
    message_id: str
    thread_id: str
    subject: str
    # No parent_uri

class EmailThreadPage(Page):
    """Email thread - assembled separately, no parent relationship."""
    thread_id: str
    emails: List[EmailSummary]
    # No parent_uri
```

**Relationship Rules:**
- No parent-child relationships (emails and threads assembled separately)

### Usage Examples

```python
# Example 1: Creating Google Doc chunks from header
cache = PageCache("sqlite:///pages.db")

# Store header first
header = GDocHeader(
    uri=PageURI(root="google", type="gdoc_header", id="doc123", version=1),
    document_id="doc123",
    title="My Document",
    chunk_count=3
)
cache.store_page(header)

# Store chunks with parent relationship
for i in range(3):
    chunk = GDocChunk(
        uri=PageURI(root="google", type="gdoc_chunk", id=f"doc123({i})", version=1),
        chunk_index=i,
        content=f"Content of chunk {i}"
    )
    # This will validate the relationship and set parent_uri
    cache.store_page(chunk, parent_uri=header.uri)

# Example 2: Slack conversation from channel
channel = SlackChannel(
    uri=PageURI(root="slack", type="channel", id="C123", version=1),
    channel_id="C123",
    name="general"
)
cache.store_page(channel)

conversation = SlackConversation(
    uri=PageURI(root="slack", type="conversation", id="C123-conv1", version=1),
    conversation_id="conv1",
    channel_id="C123",
    participants=["user1", "user2"]
)
cache.store_page(conversation, parent_uri=channel.uri)

# Example 3: Email (no parent relationship)
email = EmailPage(
    uri=PageURI(root="gmail", type="email", id="msg123", version=1),
    message_id="msg123",
    thread_id="thread456",
    subject="Test Email"
)
cache.store_page(email)  # No parent_uri - assembled separately

thread = EmailThreadPage(
    uri=PageURI(root="gmail", type="email_thread", id="thread456", version=1),
    thread_id="thread456",
    emails=[...]
)
cache.store_page(thread)  # No parent_uri - assembled separately
```

### Error Scenarios

```python
# Error 1: Parent doesn't exist
try:
    cache.store_page(chunk, parent_uri=PageURI(root="google", type="gdoc_header", id="nonexistent"))
except ValueError as e:
    print(f"Error: {e}")  # Parent page not found in cache

# Error 2: Same page type
try:
    header1 = GDocHeader(uri=PageURI(root="google", type="gdoc_header", id="doc1", version=1))
    header2 = GDocHeader(uri=PageURI(root="google", type="gdoc_header", id="doc2", version=1))
    cache.store_page(header1)
    cache.store_page(header2, parent_uri=header1.uri)
except ValueError as e:
    print(f"Error: {e}")  # Parent and child cannot be the same page type

# Error 3: Child already exists
try:
    cache.store_page(chunk)  # Store without parent first
    cache.store_page(chunk, parent_uri=header.uri)  # Try to store again with parent
except ValueError as e:
    print(f"Error: {e}")  # Child page already exists in cache
```

## Migration Strategy

1. **Phase 1**: Add optional `parent_uri` field to base `Page` class
2. **Phase 2**: Enhance `PageCache.store_page()` with validation logic
3. **Phase 3**: Update existing integrations to use new pattern where appropriate
4. **Phase 4**: Add relationship query methods (`get_children`, `get_parent`)

## Benefits

1. **Type Safety**: Leverages existing PageURI system for type-safe relationships
2. **Validation**: Prevents invalid relationships and loops
3. **Flexibility**: Supports both derived relationships (chunks) and separate assembly (emails)
4. **Backward Compatibility**: Optional parent_uri field maintains existing functionality
5. **Query Support**: Enables efficient parent/child queries using existing SQLAlchemy infrastructure