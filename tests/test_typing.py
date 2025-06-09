from datetime import datetime, timedelta
from typing import List

import pytest

from praga_core.retriever_toolkit import RetrieverToolkit
from praga_core.types import Document, PaginatedResponse


class DemoToolkit(RetrieverToolkit):
    def __init__(self):
        super().__init__()


@DemoToolkit.tool(cache=True, ttl=timedelta(minutes=5))
def get_timestamp() -> List[Document]:
    return [Document(id="ts", content=datetime.now().isoformat(), metadata={})]


@DemoToolkit.tool(cache=False)
def get_greeting(name: str) -> List[Document]:
    return [Document(id="greet", content=f"Hello, {name}!", metadata={"name": name})]


def test_toolkit():
    tk = DemoToolkit()
    assert "get_timestamp" in tk._tools
    assert "get_greeting" in tk._tools


def test_valid_return_types():
    """Test that tools with proper return types work correctly."""
    tk = DemoToolkit()

    # Test List[Document] return
    result = tk.get_greeting("world")
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Document)
    assert result[0].content == "Hello, world!"


def test_invalid_return_type_registration():
    """Test that tools with invalid return types are rejected during registration."""

    class BadToolkit(RetrieverToolkit):
        pass

    # This should fail because it doesn't have proper type annotation
    with pytest.raises(TypeError, match="must have return type annotation"):

        @BadToolkit.tool()
        def bad_tool_no_annotation():
            return [{"id": "bad", "content": "test"}]

        BadToolkit()  # This triggers registration

    # This should fail because it returns wrong type
    with pytest.raises(TypeError, match="must have return type annotation"):

        @BadToolkit.tool()
        def bad_tool_wrong_type() -> List[str]:
            return ["hello", "world"]

        BadToolkit()  # This triggers registration


def test_pagination_with_proper_types():
    """Test that pagination works with properly typed tools."""

    class PaginatedToolkit(RetrieverToolkit):
        def __init__(self):
            super().__init__()
            self.register_tool(
                method=self.get_many_docs,
                name="get_many_docs",
                paginate=True,
                max_docs=2,
            )

        def get_many_docs(self) -> List[Document]:
            return [
                Document(id=f"doc_{i}", content=f"Content {i}", metadata={"index": i})
                for i in range(5)
            ]

    tk = PaginatedToolkit()

    # Test pagination
    result = tk.get_many_docs(page=0)
    assert isinstance(result, PaginatedResponse)
    assert len(result.documents) == 2
    assert result.metadata.page_number == 0
    assert result.metadata.has_next_page is True
