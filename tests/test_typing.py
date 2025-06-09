from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Sequence, cast

import pytest

from praga_core.retriever_toolkit import (
    RetrieverToolkit,
    _is_document_sequence_type,
    _returns_paginated_response,
)
from praga_core.types import Document, PageMetadata, PaginatedResponse


class DemoToolkit(RetrieverToolkit):
    def __init__(self) -> None:
        super().__init__()


@DemoToolkit.tool(cache=True, ttl=timedelta(minutes=5))
def get_timestamp() -> List[Document]:
    return [Document(id="ts", content=datetime.now().isoformat(), metadata={})]


@DemoToolkit.tool(cache=False)
def get_greeting(name: str) -> List[Document]:
    return [Document(id="greet", content=f"Hello, {name}!", metadata={"name": name})]


def test_toolkit() -> None:
    tk: DemoToolkit = DemoToolkit()
    assert "get_timestamp" in tk._tools
    assert "get_greeting" in tk._tools


def test_valid_return_types() -> None:
    """Test that tools with proper return types work correctly."""
    tk: DemoToolkit = DemoToolkit()

    # Test List[Document] return
    result = tk.get_greeting("world")
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], Document)
    assert result[0].content == "Hello, world!"


def test_invalid_return_type_registration() -> None:
    """Test that tools with invalid return types are rejected during registration."""

    class BadToolkit(RetrieverToolkit):
        pass

    # This should fail because it doesn't have proper type annotation
    with pytest.raises(TypeError, match="must have return type annotation"):

        @BadToolkit.tool()  # type: ignore[arg-type]
        def bad_tool_no_annotation() -> List[Dict[str, str]]:
            return [{"id": "bad", "content": "test"}]

        BadToolkit()  # This triggers registration

    # This should fail because it returns wrong type
    with pytest.raises(TypeError, match="must have return type annotation"):

        @BadToolkit.tool()  # type: ignore[arg-type]
        def bad_tool_wrong_type() -> List[str]:
            return ["hello", "world"]

        BadToolkit()  # This triggers registration


def test_pagination_with_proper_types() -> None:
    """Test that pagination works with properly typed tools."""

    class PaginatedToolkit(RetrieverToolkit):
        def __init__(self) -> None:
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

    tk: PaginatedToolkit = PaginatedToolkit()

    # Test pagination
    # Cast to a callable that accepts 'page' for mypy
    paginated_method = cast(Callable[..., PaginatedResponse], tk.get_many_docs)
    result = paginated_method(page=0)
    assert isinstance(result, PaginatedResponse)
    assert len(result.documents) == 2
    assert result.metadata.page_number == 0
    assert result.metadata.has_next_page is True


class TestTypeCheckingLogic:
    """Test the simplified type checking logic in retriever toolkit."""

    def test_is_document_sequence_type_with_list(self) -> None:
        """Test that List[Document] is considered valid."""

        def tool_with_list() -> List[Document]:
            return []

        assert _is_document_sequence_type(tool_with_list) is True

    def test_is_document_sequence_type_with_sequence(self) -> None:
        """Test that Sequence[Document] is considered valid."""

        def tool_with_sequence() -> Sequence[Document]:
            return []

        assert _is_document_sequence_type(tool_with_sequence) is True

    def test_is_document_sequence_type_with_paginated_response(self) -> None:
        """Test that PaginatedResponse is considered valid."""

        def tool_with_paginated_response() -> PaginatedResponse:
            metadata = PageMetadata(page_number=0, has_next_page=False)
            return PaginatedResponse(documents=[], metadata=metadata)

        assert _is_document_sequence_type(tool_with_paginated_response) is True

    def test_is_document_sequence_type_with_invalid_type(self) -> None:
        """Test that invalid return types are rejected."""

        def tool_with_string() -> str:
            return "hello"

        def tool_with_no_annotation() -> List[Any]:
            return []

        def tool_with_wrong_sequence() -> List[str]:
            return ["hello"]

        assert _is_document_sequence_type(tool_with_string) is False  # type: ignore[arg-type]
        assert _is_document_sequence_type(tool_with_no_annotation) is False
        assert _is_document_sequence_type(tool_with_wrong_sequence) is False  # type: ignore[arg-type]

    def test_is_document_sequence_type_covers_all_valid_types(self) -> None:
        """Test that _is_document_sequence_type covers all valid return types."""

        def tool_with_list() -> List[Document]:
            return []

        def tool_with_sequence() -> Sequence[Document]:
            return []

        def tool_with_paginated_response() -> PaginatedResponse:
            metadata = PageMetadata(page_number=0, has_next_page=False)
            return PaginatedResponse(documents=[], metadata=metadata)

        assert _is_document_sequence_type(tool_with_list) is True
        assert _is_document_sequence_type(tool_with_sequence) is True
        assert _is_document_sequence_type(tool_with_paginated_response) is True

    def test_returns_paginated_response_specific(self) -> None:
        """Test that _returns_paginated_response only identifies PaginatedResponse."""

        def tool_with_list() -> List[Document]:
            return []

        def tool_with_sequence() -> Sequence[Document]:
            return []

        def tool_with_paginated_response() -> PaginatedResponse:
            metadata = PageMetadata(page_number=0, has_next_page=False)
            return PaginatedResponse(documents=[], metadata=metadata)

        assert _returns_paginated_response(tool_with_list) is False
        assert _returns_paginated_response(tool_with_sequence) is False
        assert _returns_paginated_response(tool_with_paginated_response) is True

    def test_can_be_paginated_logic(self) -> None:
        """Test the logic for determining if a tool can be paginated."""

        def tool_with_list() -> List[Document]:
            return []

        def tool_with_sequence() -> Sequence[Document]:
            return []

        def tool_with_paginated_response() -> PaginatedResponse:
            metadata = PageMetadata(page_number=0, has_next_page=False)
            return PaginatedResponse(documents=[], metadata=metadata)

        # These should return True (can be paginated - not already paginated responses)
        assert not _returns_paginated_response(tool_with_list)
        assert not _returns_paginated_response(tool_with_sequence)

        # This should return True (cannot be paginated - would create double pagination)
        assert _returns_paginated_response(tool_with_paginated_response)


class TestPaginationPrevention:
    """Test that we prevent double-pagination correctly."""

    def test_toolkit_prevents_paginating_paginated_response(self) -> None:
        """Test that trying to paginate a tool that returns PaginatedResponse raises an error."""

        class TestToolkit(RetrieverToolkit):
            pass

        def tool_returning_paginated_response() -> PaginatedResponse:
            metadata = PageMetadata(page_number=0, has_next_page=False)
            return PaginatedResponse(documents=[], metadata=metadata)

        toolkit = TestToolkit()

        # This should raise an error because we can't paginate something that already returns PaginatedResponse
        with pytest.raises(TypeError, match="Cannot paginate tool"):
            toolkit.register_tool(
                method=tool_returning_paginated_response,
                name="test_tool",
                paginate=True,
            )

    def test_toolkit_allows_paginating_document_sequence(self) -> None:
        """Test that we can paginate tools that return document sequences."""

        class TestToolkit(RetrieverToolkit):
            pass

        def tool_returning_list() -> List[Document]:
            return [
                Document(id="1", content="Content 1"),
                Document(id="2", content="Content 2"),
                Document(id="3", content="Content 3"),
            ]

        def tool_returning_sequence() -> Sequence[Document]:
            return [
                Document(id="1", content="Content 1"),
                Document(id="2", content="Content 2"),
            ]

        toolkit = TestToolkit()

        # These should work fine
        toolkit.register_tool(
            method=tool_returning_list, name="list_tool", paginate=True
        )

        toolkit.register_tool(
            method=tool_returning_sequence, name="sequence_tool", paginate=True
        )

        # Verify the tools were registered
        assert "list_tool" in toolkit._tools
        assert "sequence_tool" in toolkit._tools

        # Verify they return PaginatedResponse after pagination wrapping
        result1 = toolkit.list_tool()
        result2 = toolkit.sequence_tool()

        assert isinstance(result1, PaginatedResponse)
        assert isinstance(result2, PaginatedResponse)

    def test_toolkit_allows_non_paginated_paginated_response(self) -> None:
        """Test that we can register tools that return PaginatedResponse without pagination."""

        class TestToolkit(RetrieverToolkit):
            pass

        def tool_returning_paginated_response() -> PaginatedResponse:
            docs = [Document(id="1", content="Content 1")]
            metadata = PageMetadata(page_number=0, has_next_page=False)
            return PaginatedResponse(documents=docs, metadata=metadata)

        toolkit = TestToolkit()

        # This should work fine (no pagination requested)
        toolkit.register_tool(
            method=tool_returning_paginated_response,
            name="paginated_tool",
            paginate=False,
        )

        # Verify the tool was registered
        assert "paginated_tool" in toolkit._tools

        # Verify it returns PaginatedResponse directly
        result = toolkit.paginated_tool()
        assert isinstance(result, PaginatedResponse)
        assert len(result.documents) == 1
        assert result.documents[0].id == "1"


class TestTypeEquivalence:
    """Test that PaginatedResponse is now properly recognized as a Sequence[Document]."""

    def test_paginated_response_implements_sequence_protocol(self) -> None:
        """Test that PaginatedResponse is recognized as implementing Sequence[Document]."""

        docs = [Document(id="1", content="Content 1")]
        metadata = PageMetadata(page_number=0, has_next_page=False)
        response = PaginatedResponse(documents=docs, metadata=metadata)

        # This should work now that PaginatedResponse implements Sequence[Document]
        assert isinstance(response, Sequence)

        # It should also work as a sequence in function calls
        def process_sequence(seq: Sequence[Document]) -> int:
            return len(seq)

        # This should not raise a type error
        result = process_sequence(response)
        assert result == 1
