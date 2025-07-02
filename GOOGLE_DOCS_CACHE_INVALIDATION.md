# Google Docs Cache Invalidation Implementation

## Overview

This document describes the implementation of cache invalidation for the Google Docs service. The implementation ensures that cached Google Docs pages (headers and chunks) automatically become invalid when the underlying document changes, and provides manual controls for cache management.

## Key Features

### 1. **Automatic Cache Validation**
- Pages are automatically validated when accessed
- Uses Google Drive API revision tracking
- Hierarchical validation (chunks validate against parent document)

### 2. **Manual Cache Management**
- Force invalidate specific documents
- Check document freshness status
- Force refresh documents from Google Docs

### 3. **Revision Tracking**
- Stores Google Drive revision IDs with cached pages
- Compares cached revision with current online revision
- Handles API failures gracefully

## Implementation Details

### Page Schema Changes

#### GDocHeader
```python
class GDocHeader(Page):
    # ... existing fields ...
    revision_id: str = Field(description="Document revision ID for cache validation", exclude=True)
```

#### GDocChunk  
```python
class GDocChunk(Page):
    # ... existing fields ...
    doc_revision_id: str = Field(description="Parent document revision ID for cache validation", exclude=True)
```

### API Client Extensions

New methods added to `GoogleAPIClient`:

```python
def get_file_revisions(self, file_id: str) -> List[Dict[str, Any]]:
    """Get all revisions for a Google Drive file."""

def get_latest_revision_id(self, file_id: str) -> Optional[str]:
    """Get the latest revision ID for a Google Drive file."""

def check_file_revision(self, file_id: str, cached_revision_id: str) -> bool:
    """Check if the cached revision ID matches the current latest revision."""
```

### Service Invalidators

The Google Docs service registers invalidator functions that:

1. **Header Validation**: Checks if the document's cached revision matches the current online revision
2. **Chunk Validation**: Checks if the parent document's cached revision is still current

```python
def validate_gdoc_header(page: GDocHeader) -> bool:
    """Validate a Google Docs header page by checking if revision is current."""
    return api_client.check_file_revision(page.document_id, page.revision_id)

def validate_gdoc_chunk(page: GDocChunk) -> bool:
    """Validate a Google Docs chunk page by checking if parent document revision is current."""
    return api_client.check_file_revision(page.document_id, page.doc_revision_id)
```

## Usage Examples

### Automatic Validation

Cache invalidation happens automatically when accessing pages:

```python
# This will automatically validate the cached page
header = context.get_page("myserver/gdoc_header:doc123@1")

# If the document has changed online, this will return None
# and the cache will be marked as invalid
```

### Manual Cache Management

#### Check Document Freshness

```python
service = context.get_service("google_docs")
toolkit = service.toolkit

# Check if a document is fresh
freshness = toolkit.check_document_freshness("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

print(freshness)
# {
#     "cached": True,
#     "fresh": False,
#     "cached_revision": "ALm37BWBzPJoKN2Ng8ZD_lKTQqQKhPUBhBJfJjj8_CcE",
#     "current_revision": "ALm37BWBzPJoKN2Ng8ZD_lKTQqQKhPUBhBJfJjj8_NEW",
#     "cached_modified_time": "2024-01-15T10:30:00",
#     "message": "Document has been modified online"
# }
```

#### Manual Invalidation

```python
# Manually invalidate all cached pages for a document
result = toolkit.invalidate_document_cache("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

print(result)
# {
#     "success": True,
#     "document_id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
#     "invalidated_pages": 8,
#     "message": "Successfully invalidated 8 cached pages"
# }
```

#### Force Refresh

```python
# Force refresh a document (invalidate cache and re-ingest)
fresh_header = toolkit.refresh_document("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")

print(f"Refreshed document: {fresh_header.title}")
print(f"New revision: {fresh_header.revision_id}")
```

### Service-Level Methods

The `GoogleDocsService` also provides direct methods:

```python
service = context.get_service("google_docs")

# Check freshness
freshness_info = service.check_document_freshness("doc_id")

# Invalidate document  
invalidated_count = service.invalidate_document("doc_id")

# Force refresh
fresh_header = service.refresh_document("doc_id")
```

## Cache Validation Flow

### 1. Page Access
```
User requests page
    ↓
Check 'valid' column in database
    ↓
If invalid → Return None
    ↓
If valid → Load page from cache
    ↓
Run invalidator function
    ↓
If invalidator returns False → Mark invalid, return None
    ↓
If invalidator returns True → Return page
```

### 2. Invalidator Logic
```
Invalidator called with page
    ↓
Extract document_id and cached revision_id
    ↓
Call Google Drive API to get current revision
    ↓
Compare cached vs current revision
    ↓
Return True if same, False if different
```

### 3. Hierarchical Validation
```
Chunk page accessed
    ↓
Validate chunk's document revision
    ↓
If document revision invalid → Chunk is invalid
    ↓
Also validate ancestor pages in provenance chain
    ↓
If any ancestor invalid → Mark current page invalid
```

## Error Handling

### API Failures
- If revision API calls fail, pages are considered invalid (fail-safe)
- Errors are logged but don't crash the application
- Graceful degradation when Google APIs are unavailable

### Missing Revisions
- If no revision ID can be obtained, uses "unknown" as fallback
- Documents with "unknown" revision are always considered valid
- Prevents cache invalidation when revision tracking is unavailable

### Network Issues
- Invalidator functions catch exceptions and return False (invalid)
- Ensures cache consistency even during network problems
- Logged warnings help with debugging

## Performance Considerations

### Caching Strategy
- Revision checks are only made when pages are accessed
- No background validation processes
- Revision IDs are cached to minimize API calls

### API Rate Limits
- Revision checks use minimal Google Drive API quota
- Only HEAD requests to get revision metadata
- Batching could be added for high-volume scenarios

### Database Impact
- Single additional boolean column per page table
- Revision IDs stored as excluded fields (not in database)
- Minimal storage overhead

## Monitoring and Debugging

### Logging
```python
# Enable debug logging to see invalidation activity
import logging
logging.getLogger("pragweb.google_api.docs.service").setLevel(logging.DEBUG)
```

### Key Log Messages
- `"Failed to validate header {document_id}: {error}"` - Validation errors
- `"Manually invalidated {count} pages for document {document_id}"` - Manual invalidation
- `"Force refreshing document {document_id}"` - Document refresh operations

### Health Checks
```python
# Check if invalidation is working
freshness = service.check_document_freshness("test_document_id")
if not freshness["fresh"]:
    print("Cache invalidation is working - detected stale document")
```

## Integration with Existing Systems

### Backward Compatibility
- Existing cached pages without revision IDs are handled gracefully
- New revision tracking is additive - doesn't break existing functionality
- Migration is automatic when documents are next accessed

### Service Integration
- Works with existing `ToolkitService` architecture
- Integrates with provenance tracking system
- Compatible with existing search and retrieval workflows

## Best Practices

### When to Use Manual Invalidation
- After bulk document operations
- When you know documents have changed externally
- During maintenance or data migration
- For testing cache invalidation functionality

### When to Use Force Refresh
- When you need the absolute latest version
- After document structure changes (new chunks)
- When debugging cache-related issues
- For critical documents that must be current

### Monitoring Recommendations
- Track invalidation rates to understand document change frequency
- Monitor API errors to ensure revision checking is working
- Set up alerts for high invalidation rates (may indicate issues)

## Example: Complete Workflow

```python
from praga_core.context import ServerContext
from pragweb.google_api.docs.service import GoogleDocsService
from pragweb.google_api.client import GoogleAPIClient
from pragweb.google_api.auth import GoogleAuthManager

# Set up service
auth_manager = GoogleAuthManager()
api_client = GoogleAPIClient(auth_manager)
context = ServerContext(root="myapp")
docs_service = GoogleDocsService(api_client)
context.register_service("google_docs", docs_service)

# Access document (automatic validation)
doc_uri = "myapp/gdoc_header:1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms@1"
header = context.get_page(doc_uri)

if header:
    print(f"Document is current: {header.title}")
else:
    print("Document cache is invalid - document may have changed")
    
# Check freshness manually
freshness = docs_service.check_document_freshness("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
print(f"Document freshness: {freshness}")

# Force refresh if needed
if not freshness["fresh"]:
    print("Refreshing document...")
    fresh_header = docs_service.refresh_document("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms")
    print(f"Document refreshed: {fresh_header.title}")
```

This implementation provides robust, automatic cache invalidation for Google Docs while maintaining performance and providing manual controls for advanced use cases.