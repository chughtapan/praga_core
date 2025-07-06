# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Development Commands

### Environment Setup
- Active the venv in .venv at the start of the session 

### Testing
- `pytest` - Run all tests
- `pytest tests/core/` - Run core tests only
- `pytest tests/services/` - Run service tests only
- `pytest tests/core/test_specific_file.py` - Run specific test file
- `pytest -k "test_name"` - Run specific test by name

### Code Quality
- `black .` - Format code with Black
- `isort .` - Sort imports
- `flake8 .` - Lint code
- `mypy src/` - Type check source code
- `autoflake8 --in-place --recursive .` - Remove unused imports
- Remember to run linter checks and tests after your changes are done and fix any issues that arise

### Build
- `pip install -e .` - Install in development mode
- `python -m build` - Build distribution packages

## Architecture Overview

### Core Components

**Praga Core** is a framework for building document retrieval toolkits and agents for LLM applications, implementing LLMRP (LLM Retrieval Protocol) for standardized document retrieval over HTTP.

#### Key Architectural Layers:

1. **Context Layer** (`context.py`, `global_context.py`, `action_executor.py`)
   - `ServerContext`: Main context inheriting from `ActionExecutorMixin`
   - `ActionExecutorMixin`: Mixin providing action registration and execution
   - `@action` decorator: Transforms Page signatures to PageURI signatures
   - Global context management for service-wide state

2. **Agent Layer** (`agents/`)
   - `ReactAgent`: ReAct methodology implementation for document retrieval
   - `RetrieverToolkit`: Tool collection for document operations
   - Template-based agent responses with JSON parsing
   - Integration with OpenAI API for LLM interactions

3. **Page Cache System** (`page_cache/`)
   - `PageCache`: Async SQLite-based caching with separated concerns
   - `PageStorage`: Core CRUD operations
   - `PageRegistry`: Type registration and table management
   - `PageValidator`: Validation logic
   - `ProvenanceManager`: Relationship tracking between pages

4. **Integration Layer** (`integrations/`)
   - MCP (Model Context Protocol) server implementation
   - FastMCP integration for exposing context functionality
   - Action and search tool descriptions

5. **Service Layer** (`service.py`, `pragweb/`)
   - Base `Service` class for external API integrations
   - Google API services (Calendar, Docs, Gmail, People)
   - Slack integration stub
   - Secrets management

### Key Design Patterns

- **Async-first architecture**: All core operations are async
- **Mixin-based composition**: `ActionExecutorMixin` avoids circular dependencies
- **Signature transformation**: Actions defined with Page params, exposed as PageURI API
- **Type safety**: Comprehensive type hints and mypy checking
- **Separation of concerns**: Clear component boundaries in PageCache
- **Protocol-based design**: LLMRP for standardized retrieval

### Action System Architecture

The action system uses a sophisticated signature transformation pattern:

1. **Definition**: Actions are defined with `Page` parameters:
   ```python
   @context.action()
   def mark_email_read(email: EmailPage) -> bool:
       email.read = True
       return True
   ```

2. **Registration**: The `@action` decorator creates wrapper functions that:
   - Accept `PageURI` parameters instead of `Page` parameters
   - Use `context.get_pages()` for bulk async page retrieval
   - Call the original function with resolved `Page` objects

3. **Invocation**: `context.invoke_action()` only accepts `PageURI` arguments:
   ```python
   result = await context.invoke_action("mark_email_read", {"email": page_uri})
   ```

4. **API Boundary**: External API strictly enforces PageURI-only interface, rejecting Page objects with helpful error messages

This design ensures:
- Clean separation between external API (PageURI) and internal logic (Page)
- Efficient bulk page retrieval for performance
- Type safety through wrapper function signature transformation
- Async consistency throughout the codebase

### Testing Configuration

- Uses pytest with asyncio mode enabled
- Test files follow `test_*.py` pattern
- Async tests supported by default
- Comprehensive coverage of core and service layers

### Code Style

- Black formatter with 88-character line length
- isort for import sorting with Black profile
- Strict mypy configuration with comprehensive type checking
- Flake8 linting with extended rules
- Python 3.11+ required