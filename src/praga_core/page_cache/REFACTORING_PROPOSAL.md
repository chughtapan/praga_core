# PageCache Refactoring Proposal

## The Problem

The current `PageCache` class in `core.py` has grown too complex and is difficult to read and maintain. Here are the main issues:

### 1. Too Many Responsibilities
The single `PageCache` class handles:
- Database connection management
- Page type registration and table creation
- Core CRUD operations (store, retrieve, update)
- Complex validation logic with ancestor checking
- Query building and execution
- Provenance tracking and relationship management
- Cache invalidation
- Session management

### 2. Complex Internal Methods
- `_get_page_by_uri_any_type_internal()` with multiple boolean flags
- `_convert_entity_to_page()` scattered throughout
- `_validate_page_and_ancestors()` with complex logic
- Multiple variants of similar methods for different use cases

### 3. Mixed Abstractions
- Users work with both Page objects and SQLAlchemy table expressions
- Validation logic mixed with retrieval logic
- Database concerns mixed with business logic

### 4. Hard to Extend
- Adding new validation logic requires understanding the entire class
- Query improvements require modifying core cache logic
- Storage backend changes affect everything

## The Solution: Separated Components

Instead of one monolithic class, we split responsibilities into focused components:

```
SimplePageCache (orchestrator)
├── PageStorage (CRUD operations)
├── PageRegistry (type registration & tables)
├── PageValidator (validation logic)
├── PageQuery (query building & execution)
└── ProvenanceManager (relationship tracking)
```

## Component Responsibilities

### SimplePageCache
- **Role**: Main interface and orchestrator
- **Responsibilities**: 
  - Initialize and coordinate other components
  - Provide clean public API
  - Handle component interactions

### PageStorage
- **Role**: Core data persistence
- **Responsibilities**:
  - Store and retrieve pages
  - Handle database transactions
  - Manage page validity flags
  - Convert between Page objects and database entities

### PageRegistry
- **Role**: Type and schema management
- **Responsibilities**:
  - Register page types automatically
  - Create and manage SQLAlchemy table classes
  - Map between types and tables

### PageValidator
- **Role**: Page validation
- **Responsibilities**:
  - Register and manage validator functions
  - Validate individual pages
  - Simple, clear validation interface

### PageQuery
- **Role**: Query building and execution
- **Responsibilities**:
  - Build SQLAlchemy queries from filters
  - Execute queries and return results
  - Handle query optimization

### ProvenanceManager
- **Role**: Relationship tracking
- **Responsibilities**:
  - Validate parent-child relationships
  - Prevent cycles
  - Query lineage and relationships

## Interface Comparison

### Old Complex Interface
```python
# Manual type registration
cache.register_page_type(UserPage)

# Complex invalidator registration
def validate_doc(page):
    if not isinstance(page, GoogleDocPage):
        return False
    return page.revision == "current"
cache.register_invalidator(GoogleDocPage, validate_doc)

# Complex query syntax
users = cache.find_pages_by_attribute(
    UserPage,
    lambda table: table.email.like("%@company.com")
)

# Exposed internal methods
if cache._validate_page_and_ancestors(page):
    # ...
```

### New Simple Interface
```python
# Automatic type registration
cache.store(user)  # Type registered automatically

# Simple validator registration
cache.register_validator(GoogleDocPage, lambda doc: doc.revision == "current")

# Fluent query interface
users = (cache.find(UserPage)
              .where(lambda t: t.email.like("%@company.com"))
              .all())

# Clean public methods only
user = cache.get(UserPage, uri)
latest = cache.get_latest(UserPage, "prefix")
```

## Benefits

### 1. Single Responsibility Principle
- Each component has one clear job
- Easy to understand what each piece does
- Changes are localized to relevant components

### 2. Better Testability
- Each component can be tested in isolation
- Mock dependencies easily
- Focused unit tests

### 3. Easier to Extend
- Want new validation logic? Modify `PageValidator`
- Want new query features? Modify `PageQuery`
- Want new storage backend? Modify `PageStorage`
- Components are independent

### 4. Cleaner Interface
- Simple method names: `store()`, `get()`, `find()`
- Fluent query building
- No complex internal methods exposed
- Intuitive for new developers

### 5. Better Separation of Concerns
- Database logic separate from business logic
- Validation separate from storage
- Query building separate from execution

## Migration Strategy

### Phase 1: Create New Components
- ✅ Implement `SimplePageCache` and components
- ✅ Create comparison examples
- ✅ Document the approach

### Phase 2: Gradual Migration
- Create adapter layer for backward compatibility
- Update tests to use new interface
- Migrate existing code gradually

### Phase 3: Deprecation
- Mark old interface as deprecated
- Provide migration guide
- Remove old implementation after transition period

## Files in This Refactoring

### New Implementation
- `simple_core.py` - Main `SimplePageCache` class
- `storage.py` - `PageStorage` component
- `registry.py` - `PageRegistry` component  
- `validator.py` - `PageValidator` component
- `query.py` - `PageQuery` component
- `provenance_manager.py` - `ProvenanceManager` component

### Documentation
- `comparison_example.py` - Side-by-side comparison
- `REFACTORING_PROPOSAL.md` - This document

### Existing Files (unchanged)
- `core.py` - Original complex implementation
- `schema.py` - Database schema (reused)
- `serialization.py` - Serialization utilities (reused)
- `exceptions.py` - Exception classes (reused)

## Example Usage

```python
from praga_core.page_cache.simple_core import SimplePageCache

# Initialize
cache = SimplePageCache("sqlite:///cache.db")

# Store pages (automatic type registration)
user = UserPage(uri=uri, name="John", email="john@company.com")
cache.store(user)

# Simple retrieval
user = cache.get(UserPage, uri)
latest = cache.get_latest(UserPage, "user_prefix")

# Fluent queries
adults = (cache.find(UserPage)
               .where(lambda t: t.age >= 18)
               .where(lambda t: t.email.like("%@company.com"))
               .all())

# Validation
cache.register_validator(DocPage, lambda doc: doc.revision == "current")

# Provenance
cache.store(chunk, parent_uri=doc.uri)
lineage = cache.get_lineage(chunk.uri)
```

## Conclusion

This refactoring dramatically improves the readability and maintainability of the PageCache system while preserving all functionality. The separation of concerns makes the code easier to understand, test, and extend.

The new design follows SOLID principles and provides a much better developer experience while maintaining the same core capabilities. 