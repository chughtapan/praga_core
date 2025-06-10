# Praga Core

A toolkit for document retrieval and agent-based search, featuring a ReAct (Reasoning and Acting) agent implementation.

## Overview

Praga Core provides a flexible framework for building document retrieval systems with intelligent agents. The key components include:

- **Document Types**: Abstract document models for various content types
- **Retriever Toolkit**: Extensible toolkit for implementing retrieval tools
- **ReAct Agent**: Intelligent agent that can reason about and execute retrieval tasks
- **Tool System**: Powerful tool system with pagination and caching support

## Key Features

### ReAct Agent

The ReAct agent implements the Reasoning and Acting paradigm, allowing it to:
- Think through complex retrieval tasks step by step
- Use available tools to search for and retrieve documents
- Provide explanations for why documents are relevant
- Handle pagination and large result sets intelligently

### Toolkit Integration

The agent integrates seamlessly with the `RetrieverToolkit` system:
- **Tool Registration**: Easy registration of retrieval functions as tools
- **Pagination Support**: Automatic pagination for large result sets
- **Caching**: Optional caching of expensive operations
- **Document Resolution**: Abstract method for resolving documents by ID

### OpenAI Integration

The agent integrates directly with OpenAI's API:
- **Direct OpenAI API**: Uses OpenAI's chat completions API
- **Flexible Configuration**: Support for different models and parameters
- **Easy Setup**: Simple initialization with API key

## Quick Start

### Basic Usage

```python
from praga_core import ReActAgent, RetrieverToolkit, TextDocument

# Create a custom toolkit
class MyToolkit(RetrieverToolkit):
    def __init__(self):
        super().__init__()
        # Register your retrieval tools
        self.register_tool(
            method=self.search_documents,
            name="search_documents",
            paginate=True,
            max_docs=20
        )
    
    def search_documents(self, query: str) -> List[TextDocument]:
        # Your search implementation
        return [
            TextDocument(id="1", content="Document about AI"),
            TextDocument(id="2", content="Machine learning paper")
        ]
    
    def get_document_by_id(self, document_id: str) -> TextDocument | None:
        # Your document resolution implementation
        return TextDocument(id=document_id, content="Document content")

# Create and use the agent
toolkit = MyToolkit()
agent = ReActAgent(
    toolkit=toolkit,
    api_key="your-openai-api-key",  # or set OPENAI_API_KEY environment variable
    model="gpt-4o-mini"
)

# Execute searches
results = agent.search("Find documents about artificial intelligence")
for result in results:
    print(f"Document {result.id}: {result.explanation}")
```

### Tool Registration

The toolkit supports various tool registration options:

```python
# Basic tool registration
toolkit.register_tool(
    method=my_search_function,
    name="search_tool"
)

# With pagination and caching
toolkit.register_tool(
    method=my_search_function,
    name="search_tool",
    paginate=True,
    max_docs=50,
    max_tokens=4096,
    cache=True,
    ttl=timedelta(hours=1)
)

# Using decorators for stateless tools
@RetrieverToolkit.tool(paginate=True, max_docs=10)
def search_emails(query: str) -> List[EmailDocument]:
    return find_emails(query)
```

### Document Types

Create custom document types by extending the base `Document` class:

```python
from praga_core import Document
from pydantic import Field

class EmailDocument(Document):
    sender: str = Field(description="Email sender")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body")
    
    @property
    def text(self) -> str:
        return f"From: {self.sender}\nSubject: {self.subject}\n\n{self.body}"
```

## Architecture

### ReAct Agent Flow

1. **Query Processing**: Agent receives a natural language query
2. **Reasoning**: Agent thinks about what tools to use and how to approach the task
3. **Action**: Agent executes tools using the toolkit
4. **Observation**: Agent processes tool results and decides next steps
5. **Iteration**: Process repeats until final answer is reached
6. **Response**: Agent returns structured document references with explanations

### Tool System

The tool system provides:
- **Automatic Pagination**: Tools can automatically handle large result sets
- **Parameter Validation**: Type checking and validation of tool parameters
- **Result Formatting**: Consistent formatting of tool outputs
- **Error Handling**: Graceful handling of tool execution errors

### Response Format

The agent returns structured responses with:
- **Document References**: ID, type, and relevance explanation for each document
- **Response Codes**: Success, not found, missing capability, or internal error
- **Error Messages**: Detailed error information when applicable

## Examples

See the `examples/` directory for complete working examples:
- `react_agent_example.py`: Basic ReAct agent usage with mock implementations

## Testing

Run the test suite:

```bash
python -m pytest tests/
```

Or run a specific test:

```bash
python tests/test_react_agent.py
```

## Extension Points

### OpenAI Configuration

Configure the agent with different OpenAI models and parameters:

```python
# Using different models
agent = ReActAgent(
    toolkit=toolkit,
    model="gpt-4",  # or "gpt-3.5-turbo", "gpt-4o", etc.
    api_key="your-api-key"
)

# Passing a custom OpenAI client
from openai import OpenAI

custom_client = OpenAI(
    api_key="your-api-key",
    base_url="your-custom-endpoint"  # for custom deployments
)

agent = ReActAgent(
    toolkit=toolkit,
    openai_client=custom_client
)
```

### Custom Toolkits

Extend `RetrieverToolkit` to create domain-specific toolkits:

```python
class DatabaseToolkit(RetrieverToolkit):
    def __init__(self, connection_string):
        super().__init__()
        self.db = connect(connection_string)
        self._register_database_tools()
    
    def get_document_by_id(self, document_id: str) -> Document | None:
        return self.db.get_document(document_id)
```

### Custom Document Types

Create specialized document types for your domain:

```python
class CodeDocument(Document):
    language: str
    file_path: str
    code: str
    
    @property
    def text(self) -> str:
        return f"File: {self.file_path}\nLanguage: {self.language}\n\n{self.code}"
```

## API Reference

### Core Classes

- `ReActAgent`: Main agent class for reasoning and acting
- `RetrieverToolkit`: Base class for implementing retrieval toolkits
- `Document`: Abstract base class for all document types
- `Tool`: Wrapper class for toolkit functions

### Response Types

- `AgentResponse`: Structured response from agent operations
- `DocumentReference`: Reference to a document with explanation
- `ResponseCode`: Enumeration of possible response codes

### Utilities

- `get_agent_format_instructions()`: Generate format instructions for agents
- `parse_agent_response()`: Parse agent responses from text
- `process_agent_response()`: Convert agent responses to document references

## Migration from tinyrag

If you're migrating from tinyrag/praga, key differences include:

1. **No BaseRetriever**: ReAct agent doesn't inherit from BaseRetriever
2. **Toolkit-based**: Agent uses toolkit directly instead of tools list
3. **OpenAI Integration**: Uses OpenAI API directly instead of generic engine interface
4. **Document Resolution**: Added `get_document_by_id()` abstract method to toolkit
5. **Simplified Architecture**: Cleaner separation of concerns

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

[Add your license information here]
