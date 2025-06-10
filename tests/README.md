# Test Organization for praga_core

This document describes the reorganized test structure for the praga_core package, designed for better readability, maintainability, and logical grouping.

## Test File Structure

### Core Test Files

#### `test_init.py`
- **Purpose**: Package initialization and import tests
- **Contains**: Basic package structure validation and import verification
- **Key Tests**: Package imports, main class accessibility

#### `conftest.py`
- **Purpose**: Shared test fixtures, utilities, and helper classes
- **Contains**: Common test data factories, mock classes, assertion helpers
- **Key Components**:
  - `SimpleTestDocument` class for consistent test documents
  - `MockRetrieverToolkit` for testing toolkit functionality  
  - Data factories: `create_test_documents()`, `create_text_documents()`
  - Assertion helpers: `assert_valid_pagination_response()`, `assert_valid_document_structure()`
  - Test constants: Sample queries, limits, page sizes

### Tool-Related Tests

#### `test_tool.py`
- **Purpose**: Core Tool class functionality
- **Test Classes**:
  - `TestToolInitialization`: Tool creation and basic properties
  - `TestToolInvocation`: Tool execution with different input types
  - `TestToolErrorHandling`: Exception handling and error scenarios
  - `TestToolArgumentProcessing`: Argument preparation and validation
  - `TestToolResultSerialization`: Result formatting and serialization
  - `TestToolPagination`: Tool-level pagination features
  - `TestToolDocumentation`: Description and docstring handling

### RetrieverToolkit Tests (Split by Functionality)

#### `test_retriever_toolkit_core.py`
- **Purpose**: Core RetrieverToolkit functionality
- **Test Classes**:
  - `TestRetrieverToolkitCore`: Basic toolkit operations, tool registration
  - `TestRetrieverToolkitDecorator`: @tool decorator functionality
  - `TestRetrieverToolkitErrorHandling`: Error scenarios and validation

#### `test_retriever_toolkit_caching.py`
- **Purpose**: Caching mechanisms and behavior
- **Test Classes**:
  - `TestRetrieverToolkitCaching`: Cache hits/misses, TTL, invalidation
  - `TestCachingEdgeCases`: Edge cases and error conditions in caching

#### `test_retriever_toolkit_pagination.py`
- **Purpose**: Comprehensive pagination functionality testing
- **Test Classes**:
  - `TestRetrieverToolkitPagination`: Core pagination behavior via invoke method
  - `TestPaginationWithTokenLimits`: Token-aware pagination and limits
  - `TestPaginationEdgeCases`: Boundary conditions and edge cases

#### `test_retriever_toolkit_integration.py`
- **Purpose**: Integration tests between RetrieverToolkit and Tool classes
- **Focus**: End-to-end workflows, cross-component interactions

### Data Structure Tests

#### `test_paginated_response.py`
- **Purpose**: PaginatedResponse implementation and Document classes
- **Test Classes**:
  - `TestDocumentBasics`: Document creation and metadata
  - `TestPaginatedResponseSequenceProtocol`: Sequence interface implementation
  - `TestPaginatedResponseUtilityMethods`: Helper methods and advanced features
  - `TestPaginatedResponseEdgeCases`: Boundary conditions and edge cases

#### `test_typing.py`
- **Purpose**: Type system validation and type checking
- **Test Classes**:
  - Type annotation validation
  - Document subclass compatibility
  - Type checking logic verification

## Design Principles

### 1. Single Responsibility
Each test file focuses on a specific component or functionality:
- Tool-specific tests in `test_tool.py`
- Caching-specific tests in `test_retriever_toolkit_caching.py`
- Core toolkit tests in `test_retriever_toolkit_core.py`

### 2. Clear Naming Conventions
- **Test Classes**: `TestComponentFeature` (e.g., `TestToolPagination`)
- **Test Methods**: `test_specific_behavior` (e.g., `test_pagination_respects_token_limits`)
- **Fixtures**: Descriptive names indicating their purpose (e.g., `sample_documents`, `mock_toolkit`)

### 3. Logical Grouping
Related tests are grouped into classes that clearly indicate their scope:
- Initialization tests
- Core functionality tests
- Error handling tests
- Edge case tests

### 4. Reduced Duplication
- Common test utilities moved to `conftest.py`
- Shared fixtures available across all test files
- Consistent test data creation through factory functions

### 5. Enhanced Readability
- Comprehensive docstrings for test classes and methods
- Clear test organization within files
- Consistent code formatting and structure

## Running Tests

### Run All Tests
```bash
pytest tests/
```

### Run Specific Component Tests
```bash
# Tool functionality only
pytest tests/test_tool.py

# Caching functionality only
pytest tests/test_retriever_toolkit_caching.py

# Pagination functionality only
pytest tests/test_retriever_toolkit_pagination.py

# Core toolkit functionality
pytest tests/test_retriever_toolkit_core.py

# Integration tests
pytest tests/test_retriever_toolkit_integration.py
```

### Run Tests by Pattern
```bash
# All pagination-related tests
pytest tests/ -k "pagination"

# All caching-related tests
pytest tests/ -k "caching or cache"

# All error handling tests
pytest tests/ -k "error"
```

## Benefits of This Organization

1. **Easier Navigation**: Developers can quickly find tests for specific functionality
2. **Faster Development**: Reduced time spent searching for relevant tests
3. **Better Maintainability**: Changes to specific features only affect related test files
4. **Improved Test Isolation**: Each test file can be run independently
5. **Enhanced Readability**: Clear structure makes tests easier to understand
6. **Reduced Duplication**: Shared utilities eliminate repeated code
7. **Better Coverage**: Organized structure makes it easier to identify test gaps

## Adding New Tests

When adding new tests:

1. **Identify the Component**: Determine which component/feature you're testing
2. **Choose the Right File**: Place tests in the most appropriate existing file
3. **Follow Naming Conventions**: Use consistent class and method names
4. **Use Shared Utilities**: Leverage `conftest.py` fixtures and helpers
5. **Document Clearly**: Add descriptive docstrings
6. **Group Logically**: Add tests to appropriate test classes

If no existing file fits your new tests, create a new file following the established patterns and update this README accordingly. 