# Cache Invalidation Analysis and Implementation

## Overview

I have successfully analyzed the page_cache system and implemented comprehensive cache invalidation functionality. The implementation adds support for cache invalidation functions that can be registered with page handlers, along with validation that checks both individual pages and their ancestors.

## Key Changes Made

### 1. Database Schema Updates

**File: `src/praga_core/page_cache/schema.py`**

- Added a `valid` boolean column to all page tables
- Column defaults to `True` and is non-nullable
- This allows marking pages as invalid without deleting them

```python
"valid": Column(
    Boolean, default=True, nullable=False
),  # Cache validity flag
```

### 2. PageCache Core Functionality

**File: `src/praga_core/page_cache/core.py`**

#### New Methods Added:

1. **`register_invalidator(page_type, invalidator)`**
   - Registers invalidator functions for specific page types
   - Invalidator functions take a Page and return bool (True = valid, False = invalid)

2. **`invalidate_page(uri)`**
   - Marks a specific page as invalid by URI
   - Updates the `valid` column to `False`
   - Returns `True` if page was found and invalidated

3. **`invalidate_pages_by_prefix(uri_prefix)`**
   - Marks all versions of pages with given prefix as invalid
   - Useful for invalidating all versions of a document
   - Returns count of pages invalidated

4. **`_validate_page_and_ancestors(page)`**
   - Validates a page and all its ancestors using registered invalidators
   - Checks the page itself first, then walks up the provenance chain
   - Automatically marks invalid pages in the cache
   - Returns `True` if page and all ancestors are valid

#### Updated Retrieval Methods:

- **`get_page()`**: Now checks `valid` column and runs validation before returning pages
- **`get_page_by_uri_any_type()`**: Same validation checks applied
- **`find_pages_by_attribute()`**: Filters to only return valid pages and validates each result

### 3. ServerContext Integration

**File: `src/praga_core/context.py`**

#### New Type Definition:
```python
PageInvalidator = Callable[[Page], bool]
```

#### Updated Methods:

1. **`register_handler()`** - Now accepts optional `invalidator_func` parameter
2. **`handler()` decorator** - Now accepts optional `invalidator` parameter
3. **`get_page()`** - Automatically registers invalidators with cache when first encountered

#### New Methods:

1. **`invalidate_page(page_uri)`** - Expose cache invalidation through context
2. **`invalidate_pages_by_prefix(uri_prefix)`** - Expose batch invalidation

### 4. Exception Handling

**File: `src/praga_core/page_cache/exceptions.py`**

- Added `CacheValidationError` exception for validation-related errors
- Updated exports in `__init__.py`

## Usage Examples

### 1. Basic Invalidator Registration

```python
from praga_core.context import ServerContext
from praga_core.types import Page, PageURI

class GoogleDocPage(Page):
    title: str
    content: str
    revision: str = Field(exclude=True)  # Excluded field for validation

def validate_gdoc(page: GoogleDocPage) -> bool:
    # Check if document revision is still current
    # This could make an API call to Google Docs
    return check_google_doc_revision(page.revision)

def handle_gdoc(doc_id: str) -> GoogleDocPage:
    # Fetch document from Google Docs API
    doc_data = fetch_google_doc(doc_id)
    return GoogleDocPage(
        uri=context.create_page_uri("gdoc", doc_id),
        title=doc_data.title,
        content=doc_data.content,
        revision=doc_data.revision  # Store current revision
    )

# Register handler with invalidator
context.register_handler("gdoc", handle_gdoc, validate_gdoc)
```

### 2. Decorator Syntax

```python
@context.handler("gdoc", invalidator=validate_gdoc)
def handle_gdoc(doc_id: str) -> GoogleDocPage:
    return create_google_doc_page(doc_id)
```

### 3. Manual Invalidation

```python
# Invalidate a specific page
context.invalidate_page("myserver/gdoc:doc123@1")

# Invalidate all versions of a document
context.invalidate_pages_by_prefix("myserver/gdoc:doc123")
```

## Validation Logic

The system implements a two-level validation approach:

### 1. Page-Level Validation
- Each page type can have a registered invalidator function
- Function receives the page instance and returns `True` (valid) or `False` (invalid)
- Can check excluded fields like revision numbers, timestamps, etc.

### 2. Ancestor Validation
- When retrieving a page, the system validates the entire provenance chain
- If any ancestor is invalid, the child page is also marked invalid
- This ensures consistency in hierarchical document structures

### Example Scenario: Google Docs with Chunks

```python
# Parent document becomes invalid (revision changed)
header = GoogleDocPage(...)  # revision="old" -> invalid
chunk = ChunkPage(parent_uri=header.uri, ...)  # still has revision="current"

# When retrieving the chunk:
# 1. Chunk itself validates as current -> valid
# 2. Parent header validates as old -> invalid
# 3. Chunk is marked invalid because parent is invalid
# 4. Neither page is returned to the user
```

## Database Impact

- **Backward Compatible**: Existing tables get the `valid` column added with default `True`
- **Performance**: Validation adds minimal overhead as it only runs registered invalidators
- **Storage**: One additional boolean column per page table
- **Indexing**: The `valid` column is included in queries to filter invalid pages

## Testing

Comprehensive tests have been added in:
- `tests/core/test_page_cache.py::TestCacheInvalidation`
- `tests/core/test_context.py::TestInvalidatorIntegration`

Tests cover:
- ✅ Invalidator registration
- ✅ Page validation during retrieval
- ✅ Manual page invalidation
- ✅ Batch invalidation by prefix
- ✅ Ancestor validation
- ✅ ServerContext integration
- ✅ Find queries respecting validity

## Benefits

1. **Automatic Cache Consistency**: Pages are automatically validated when accessed
2. **Flexible Validation**: Each page type can define its own validation logic
3. **Hierarchical Validation**: Ensures consistency across document relationships
4. **Performance**: Invalid pages are filtered at the database level
5. **Manual Control**: Administrators can manually invalidate pages when needed
6. **Batch Operations**: Can invalidate multiple versions efficiently

## Example Use Cases

### Google Docs Service
```python
def validate_google_doc(page: GoogleDocPage) -> bool:
    # Check if revision stored in page matches current online revision
    current_revision = google_docs_api.get_revision(page.document_id)
    return page.revision == current_revision

# When document changes online, cached pages become invalid automatically
```

### Email Service
```python
def validate_email(page: EmailPage) -> bool:
    # Check if email still exists in mailbox
    return email_api.email_exists(page.message_id)

# If email is deleted, cached page becomes invalid
```

### Time-Based Invalidation
```python
def validate_news_article(page: NewsPage) -> bool:
    # Invalidate articles older than 24 hours
    age = datetime.now() - page.published_at
    return age < timedelta(hours=24)

# Old articles automatically become invalid
```

## Conclusion

The cache invalidation implementation provides a robust, flexible system for maintaining cache consistency while preserving performance. It supports both automatic validation through registered functions and manual invalidation for administrative control. The hierarchical validation ensures that document relationships remain consistent, making it ideal for complex document systems like Google Docs with chunked content.