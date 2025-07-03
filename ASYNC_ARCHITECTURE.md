# Async Architecture Support

This document describes the async architecture support added to praga_core, enabling efficient handling of I/O-bound operations in page handlers and validators.

## Overview

The async architecture allows you to:

- **Use async page handlers** for operations that involve API calls, database queries, or other I/O
- **Use async validators** for validation logic that requires external services
- **Bulk page retrieval** with parallel execution for better performance
- **Mix sync and async patterns** while maintaining full backward compatibility

## Key Features

### 1. Async Page Handlers

Register async handlers using the same `@context.route()` decorator:

```python
from praga_core import ServerContext
from praga_core.types import Page, PageURI

# Traditional sync handler (still supported)
@context.route("documents")
def handle_documents(uri: PageURI) -> DocumentPage:
    return DocumentPage(uri=uri, content="...")

# New async handler capability
@context.route("emails")
async def handle_emails(uri: PageURI) -> EmailPage:
    # Can make async API calls, database queries, etc.
    email_data = await fetch_from_api(uri.id)
    return EmailPage(uri=uri, **email_data)
```

### 2. Async Page Retrieval

Use the new async methods for better performance:

```python
# Single page retrieval (works with both sync and async handlers)
page = await context.get_page_async(uri)

# Bulk retrieval with parallel execution
pages = await context.get_pages_async([uri1, uri2, uri3])
```

### 3. Async Validators

Register validators that can perform async validation logic:

```python
# Sync validator (existing pattern)
@context.validator
def validate_document(page: DocumentPage) -> bool:
    return len(page.content) > 0

# Async validator (new capability)
@context.validator
async def validate_email(page: EmailPage) -> bool:
    # Can check external reputation services, etc.
    reputation = await check_sender_reputation(page.sender)
    return reputation.is_trusted
```

## API Reference

### New Type Definitions

- `AsyncHandlerFn`: Type for async page handlers
- `AnyHandlerFn`: Union type supporting both sync and async handlers
- `AsyncValidatorFn`: Type for async validators
- `AnyValidatorFn`: Union type supporting both sync and async validators

### New Methods

#### ServerContext

- `async get_page_async(page_uri) -> Page`: Async version of get_page
- `get_pages(page_uris) -> List[Page]`: Bulk sync page retrieval
- `async get_pages_async(page_uris) -> List[Page]`: Bulk async page retrieval

#### PageRouter

- `async get_page_async(page_uri) -> Page`: Async page retrieval
- `get_pages(page_uris) -> List[Page]`: Bulk sync retrieval
- `async get_pages_async(page_uris) -> List[Page]`: Bulk async retrieval

#### PageValidator

- `async is_valid_async(page) -> bool`: Async validation

## Performance Benefits

### Parallel Execution

Bulk async operations execute handlers in parallel:

```python
# Sequential execution (~300ms for 3 handlers with 100ms each)
pages = [context.get_page(uri) for uri in uris]

# Parallel execution (~100ms for same 3 handlers)
pages = await context.get_pages_async(uris)
```

### Mixed Handler Types

You can mix sync and async handlers in the same bulk operation:

```python
uris = [
    PageURI(type="sync_handler", id="1"),    # Runs in thread pool
    PageURI(type="async_handler", id="2"),   # Native async execution
    PageURI(type="sync_handler", id="3"),    # Runs in thread pool
]

# All execute in parallel
pages = await context.get_pages_async(uris)
```

## Backward Compatibility

All existing sync code continues to work unchanged:

- Existing sync handlers work exactly as before
- Existing sync validators work exactly as before
- All existing `context.get_page()` calls work unchanged
- No breaking changes to any existing APIs

## Error Handling

Async methods properly propagate errors:

```python
try:
    pages = await context.get_pages_async(uris)
except SomeHandlerError as e:
    # Errors from any handler are propagated
    print(f"Handler failed: {e}")
```

## Thread Pool Execution

When sync handlers are called from async context, they automatically run in a thread pool to avoid blocking the event loop:

```python
# This sync handler runs in thread pool when called via get_page_async()
@context.route("documents") 
def sync_handler(uri: PageURI) -> DocumentPage:
    # Blocking I/O here won't block the event loop
    data = requests.get(f"https://api.example.com/{uri.id}").json()
    return DocumentPage(uri=uri, **data)

# Async execution automatically uses thread pool for sync handler
page = await context.get_page_async(document_uri)
```

## Migration Guide

### Step 1: Update Handlers (Optional)

Convert I/O-heavy handlers to async for better performance:

```python
# Before
@context.route("emails")
def handle_emails(uri: PageURI) -> EmailPage:
    response = requests.get(f"https://api.example.com/emails/{uri.id}")
    return EmailPage(uri=uri, **response.json())

# After  
@context.route("emails")
async def handle_emails(uri: PageURI) -> EmailPage:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.example.com/emails/{uri.id}") as response:
            data = await response.json()
    return EmailPage(uri=uri, **data)
```

### Step 2: Use Bulk Operations

Replace individual page retrievals with bulk operations where beneficial:

```python
# Before
pages = []
for uri in uris:
    page = context.get_page(uri)
    pages.append(page)

# After
pages = await context.get_pages_async(uris)
```

### Step 3: Add Async Validators (Optional)

Convert validators that need external data to async:

```python
# Before - limited to local validation
@context.validator
def validate_email(page: EmailPage) -> bool:
    return "@" in page.sender

# After - can check external services
@context.validator
async def validate_email(page: EmailPage) -> bool:
    reputation = await reputation_service.check(page.sender)
    return reputation.score > 0.8
```

## Best Practices

1. **Use async handlers for I/O-bound operations**: API calls, database queries, file operations
2. **Use bulk operations for multiple pages**: Better performance through parallelism
3. **Keep sync handlers for CPU-bound work**: No benefit from async for pure computation
4. **Use async validators sparingly**: Only when external validation is required
5. **Handle errors appropriately**: Async errors propagate through the call stack

## Examples

See `examples/async_demo.py` for a complete working example demonstrating all async features.