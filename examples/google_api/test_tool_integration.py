"""Test script to demonstrate the Tool integration with RetrieverToolkit."""

from datetime import timedelta
from typing import List

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.types import Document


class SimpleDocument(Document):
    """Simple document for testing."""

    title: str
    content: str

    def __init__(self, **data):
        super().__init__(**data)
        # Simple token count estimation
        self._metadata.token_count = (len(self.title) + len(self.content)) // 4


class TestToolkit(RetrieverToolkit):
    """Simple toolkit for testing tool integration."""

    def __init__(self):
        super().__init__()

        # Register a tool with pagination enabled
        self.register_tool(
            self.search_documents,
            "search_documents",
            cache=True,
            ttl=timedelta(minutes=5),
            paginate=True,  # Enable pagination via invoke
            max_docs=3,  # Small page size for testing
            max_tokens=100,
        )

        # Register a tool without pagination
        self.register_tool(
            self.get_document_count,
            "get_document_count",
            cache=False,
            paginate=False,  # No pagination
        )

    def search_documents(self, query: str, limit: int = 10) -> List[SimpleDocument]:
        """Search for documents matching the query."""
        # Mock data - simulate finding documents
        all_docs = [
            SimpleDocument(
                id=f"doc_{i}",
                title=f"Document {i} - {query}",
                content=f"This is the content of document {i} about {query}. " * 5,
            )
            for i in range(limit)
        ]

        print(f"search_documents called with query='{query}', limit={limit}")
        print(f"Returning {len(all_docs)} documents")
        return all_docs

    def get_document_count(self, query: str) -> List[SimpleDocument]:
        """Get a single document with the count."""
        count_doc = SimpleDocument(
            id="count_doc",
            title="Document Count",
            content=f"Found documents matching '{query}'",
        )
        print(f"get_document_count called with query='{query}'")
        return [count_doc]


# Test the functionality
if __name__ == "__main__":
    toolkit = TestToolkit()

    print("=" * 50)
    print("TESTING TOOL INTEGRATION")
    print("=" * 50)

    # Test 1: Direct method call (no pagination)
    print("\n1. DIRECT METHOD CALL (No Pagination)")
    print("-" * 40)
    docs_direct = toolkit.search_documents("python", limit=8)
    print(f"Direct call returned {len(docs_direct)} documents")
    for i, doc in enumerate(docs_direct[:3]):  # Show first 3
        print(f"  {i+1}. {doc.title}")

    # Test 2: Invoke method call - page 0 (with pagination)
    print("\n2. INVOKE METHOD CALL - Page 0 (With Pagination)")
    print("-" * 40)
    result_page0 = toolkit.invoke_tool(
        "search_documents", {"query": "python", "limit": 8, "page": 0}
    )
    print(f"Page 0 result structure: {list(result_page0.keys())}")
    print(f"Documents in page 0: {len(result_page0['documents'])}")
    print(f"Has next page: {result_page0['has_next_page']}")
    print(f"Total documents: {result_page0['total_documents']}")

    # Test 3: Invoke method call - page 1
    print("\n3. INVOKE METHOD CALL - Page 1")
    print("-" * 40)
    result_page1 = toolkit.invoke_tool(
        "search_documents", {"query": "python", "limit": 8, "page": 1}
    )
    print(f"Documents in page 1: {len(result_page1['documents'])}")
    print(f"Has next page: {result_page1['has_next_page']}")

    # Test 4: String input for invoke
    print("\n4. STRING INPUT FOR INVOKE")
    print("-" * 40)
    result_string = toolkit.invoke_tool("search_documents", "javascript")
    print(f"String input result - documents: {len(result_string['documents'])}")

    # Test 5: Tool without pagination
    print("\n5. TOOL WITHOUT PAGINATION")
    print("-" * 40)
    # Direct call
    count_direct = toolkit.get_document_count("test")
    print(f"Direct call to non-paginated tool: {len(count_direct)} documents")

    # Invoke call (should work the same as direct call)
    count_invoke = toolkit.invoke_tool("get_document_count", "test")
    print(f"Invoke call to non-paginated tool: {count_invoke}")

    # Test 6: Tool access and inspection
    print("\n6. TOOL INSPECTION")
    print("-" * 40)
    search_tool = toolkit.get_tool("search_documents")
    count_tool = toolkit.get_tool("get_document_count")

    print(
        f"Search tool - name: {search_tool.name}, description: {search_tool.description[:50]}..."
    )
    print(
        f"Count tool - name: {count_tool.name}, description: {count_tool.description[:50]}..."
    )

    print(f"\nAll available tools: {list(toolkit.tools.keys())}")

    print("\n" + "=" * 50)
    print("TEST COMPLETE")
    print("=" * 50)
