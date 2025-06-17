from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence, Union

import pytest
from pydantic import Field

from praga_core.retriever import PaginatedResponse
from praga_core.retriever.toolkit import (
    RetrieverToolkit,
    _is_page_sequence_type,
    _returns_paginated_response,
)
from praga_core.types import Page, TextPage


class DemoToolkit(RetrieverToolkit):
    def __init__(self) -> None:
        super().__init__()

    @property
    def name(self) -> str:
        return "DemoToolkit"


@DemoToolkit.tool(cache=True, ttl=timedelta(minutes=5))
def get_timestamp() -> List[Page]:
    return [TextPage(id="ts", content=datetime.now().isoformat())]


@DemoToolkit.tool(cache=False)
def get_greeting(name: str) -> List[Page]:
    doc = TextPage(id="greet", content=f"Hello, {name}!")
    doc.metadata.name = name  # type: ignore[attr-defined] # Add custom field to metadata
    return [doc]


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
    assert isinstance(result[0], Page)
    assert result[0].content == "Hello, world!"  # type: ignore[attr-defined]
    assert result[0].metadata.name == "world"  # type: ignore[attr-defined]


def test_invalid_return_type_registration() -> None:
    """Test that tools with invalid return types are rejected during registration."""

    class BadToolkit(RetrieverToolkit):
        @property
        def name(self) -> str:
            return "BadToolkit"

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

        @property
        def name(self) -> str:
            return "PaginatedToolkit"

        def get_many_docs(self) -> List[Page]:
            docs: List[Page] = []
            for i in range(5):
                doc = TextPage(id=f"doc_{i}", content=f"Content {i}")
                doc.metadata.index = i  # type: ignore[attr-defined] # Add custom field
                docs.append(doc)
            return docs

    tk: PaginatedToolkit = PaginatedToolkit()

    # Test pagination using invoke method
    result = tk.invoke_tool("get_many_docs", {})
    assert "documents" in result
    assert "page_number" in result
    assert "has_next_page" in result
    assert len(result["documents"]) == 2
    assert result["page_number"] == 0
    assert result["has_next_page"] is True

    # Test direct method call returns all documents
    direct_result = tk.get_many_docs()
    assert len(direct_result) == 5  # All documents without pagination


class TestTypeCheckingLogic:
    """Test the simplified type checking logic in retriever toolkit."""

    def test_is_document_sequence_type_with_list(self) -> None:
        """Test that List[Document] is considered valid."""

        def tool_with_list() -> List[Page]:
            return []

        assert _is_page_sequence_type(tool_with_list) is True

    def test_is_document_sequence_type_with_sequence(self) -> None:
        """Test that Sequence[Document] is considered valid."""

        def tool_with_sequence() -> Sequence[Page]:
            return []

        assert _is_page_sequence_type(tool_with_sequence) is True

    def test_is_document_sequence_type_with_paginated_response(self) -> None:
        """Test that PaginatedResponse is considered valid."""

        def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], page_number=0, has_next_page=False)

        assert _is_page_sequence_type(tool_with_paginated_response) is True

    def test_is_document_sequence_type_with_invalid_type(self) -> None:
        """Test that invalid return types are rejected."""

        def tool_with_string() -> str:
            return "hello"

        def tool_with_no_annotation() -> List[Any]:
            return []

        def tool_with_wrong_sequence() -> List[str]:
            return ["hello"]

        assert _is_page_sequence_type(tool_with_string) is False  # type: ignore[arg-type]
        assert _is_page_sequence_type(tool_with_no_annotation) is False
        assert _is_page_sequence_type(tool_with_wrong_sequence) is False  # type: ignore[arg-type]

    def test_is_document_sequence_type_covers_all_valid_types(self) -> None:
        """Test that _is_document_sequence_type covers all valid return types."""

        def tool_with_list() -> List[Page]:
            return []

        def tool_with_sequence() -> Sequence[Page]:
            return []

        def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], page_number=0, has_next_page=False)

        assert _is_page_sequence_type(tool_with_list) is True
        assert _is_page_sequence_type(tool_with_sequence) is True
        assert _is_page_sequence_type(tool_with_paginated_response) is True

    def test_returns_paginated_response_specific(self) -> None:
        """Test that _returns_paginated_response only identifies PaginatedResponse."""

        def tool_with_list() -> List[Page]:
            return []

        def tool_with_sequence() -> Sequence[Page]:
            return []

        def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], page_number=0, has_next_page=False)

        assert _returns_paginated_response(tool_with_list) is False
        assert _returns_paginated_response(tool_with_sequence) is False
        assert _returns_paginated_response(tool_with_paginated_response) is True

    def test_can_be_paginated_logic(self) -> None:
        """Test the logic for determining if a tool can be paginated."""

        def tool_with_list() -> List[Page]:
            return []

        def tool_with_sequence() -> Sequence[Page]:
            return []

        def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], page_number=0, has_next_page=False)

        # These should return True (can be paginated - not already paginated responses)
        assert not _returns_paginated_response(tool_with_list)
        assert not _returns_paginated_response(tool_with_sequence)

        # This should return True (cannot be paginated - would create double pagination)
        assert _returns_paginated_response(tool_with_paginated_response)


class TestPaginationPrevention:
    """Test that we prevent double-pagination correctly."""

    def test_toolkit_prevents_paginating_paginated_response(self) -> None:
        """Test that trying to paginate a tool that returns PaginatedResponse raises an error."""

        def tool_returning_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], page_number=0, has_next_page=False)

        class MockToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "MockToolkit"

        toolkit = MockToolkit()

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
            @property
            def name(self) -> str:
                return "TestToolkit"

        def tool_returning_list() -> List[Page]:
            return [
                TextPage(id="1", content="Content 1"),
                TextPage(id="2", content="Content 2"),
                TextPage(id="3", content="Content 3"),
            ]

        def tool_returning_sequence() -> Sequence[Page]:
            return [
                TextPage(id="1", content="Content 1"),
                TextPage(id="2", content="Content 2"),
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
        assert "list_tool" in toolkit.tools
        assert "sequence_tool" in toolkit.tools

        # Test direct calls return all documents (no pagination)
        direct_result1 = toolkit.list_tool()
        direct_result2 = toolkit.sequence_tool()

        assert isinstance(direct_result1, list)
        assert isinstance(direct_result2, list)
        assert len(direct_result1) == 3
        assert len(direct_result2) == 2

        # Test invoke calls apply pagination
        invoke_result1 = toolkit.invoke_tool("list_tool", {})
        invoke_result2 = toolkit.invoke_tool("sequence_tool", {})

        assert "documents" in invoke_result1
        assert "page_number" in invoke_result1
        assert "documents" in invoke_result2
        assert "page_number" in invoke_result2

    def test_toolkit_allows_non_paginated_paginated_response(self) -> None:
        """Test that we can register tools that return PaginatedResponse without pagination."""

        def tool_returning_paginated_response() -> PaginatedResponse[TextPage]:
            docs = [TextPage(id="1", content="Content 1")]
            return PaginatedResponse(
                results=docs,
                page_number=0,
                has_next_page=False,
                total_results=1,
                token_count=4,
            )

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        toolkit = TestToolkit()

        # This should work fine (no pagination requested)
        toolkit.register_tool(
            method=tool_returning_paginated_response,
            name="paginated_tool",
            paginate=False,
        )

        # Verify the tool was registered
        assert "paginated_tool" in toolkit.tools

        # Verify it returns PaginatedResponse directly
        result = toolkit.paginated_tool()
        assert isinstance(result, PaginatedResponse)
        assert len(result.results) == 1
        assert result.results[0].id == "1"


class SimpleTestDocumentSubclassTypeChecking:
    """Test that the type checking system accepts Document subclasses."""

    def test_text_document_subclass_accepted(self) -> None:
        """Test that functions returning List[TextDocument] are accepted."""

        def tool_with_text_document() -> List[TextPage]:
            return [TextPage(id="1", content="Test content")]

        assert _is_page_sequence_type(tool_with_text_document) is True

    def test_sequence_of_text_document_accepted(self) -> None:
        """Test that functions returning Sequence[TextDocument] are accepted."""

        def tool_with_text_document_sequence() -> Sequence[TextPage]:
            return [TextPage(id="1", content="Test content")]

        assert _is_page_sequence_type(tool_with_text_document_sequence) is True

    def test_custom_document_subclass_accepted(self) -> None:
        """Test that custom Document subclasses are accepted."""

        # Create a custom document subclass for testing
        class CustomDocument(Page):
            custom_field: str = Field(description="A custom field")

            def __init__(self, **data: Any) -> None:
                super().__init__(**data)

        def tool_with_custom_document() -> List[CustomDocument]:
            return [CustomDocument(id="1", custom_field="test")]

        assert _is_page_sequence_type(tool_with_custom_document) is True

    def test_deeply_nested_subclass_accepted(self) -> None:
        """Test that subclasses of subclasses are accepted."""

        # Create a subclass of TextDocument
        class SpecialTextDocument(TextPage):
            special_field: str = Field(description="A special field")

            def __init__(self, **data: Any) -> None:
                super().__init__(**data)

        def tool_with_special_document() -> List[SpecialTextDocument]:
            return [
                SpecialTextDocument(id="1", content="test", special_field="special")
            ]

        assert _is_page_sequence_type(tool_with_special_document) is True

    def test_non_document_subclass_rejected(self) -> None:
        """Test that classes that don't inherit from Document are rejected."""

        class NotADocument:
            id: str

        def tool_with_non_document() -> List[NotADocument]:
            return [NotADocument()]

        assert _is_page_sequence_type(tool_with_non_document) is False  # type: ignore[arg-type]

    def test_mixed_types_rejected(self) -> None:
        """Test that functions with mixed or union types are rejected."""

        def tool_with_union() -> List[Union[Page, str]]:
            return []

        # This should be rejected as it's not a pure Document sequence
        assert _is_page_sequence_type(tool_with_union) is False  # type: ignore[arg-type]

    def test_subclass_with_toolkit_registration(self) -> None:
        """Test that Document subclasses work with actual toolkit registration."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        def text_document_tool() -> List[TextPage]:
            return [TextPage(id="test", content="Test content")]

        toolkit = TestToolkit()

        # This should not raise an error
        toolkit.register_tool(
            method=text_document_tool,
            name="text_tool",
            cache=False,
            paginate=False,
        )

        # Verify the tool was registered successfully
        assert "text_tool" in toolkit.tools

        # Verify it can be called and returns the correct type
        result = toolkit.text_tool()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextPage)
        assert result[0].content == "Test content"

    def test_subclass_pagination_compatibility(self) -> None:
        """Test that Document subclasses work with pagination."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        def many_text_documents() -> List[TextPage]:
            return [TextPage(id=f"doc_{i}", content=f"Content {i}") for i in range(5)]

        toolkit = TestToolkit()

        # Register with pagination
        toolkit.register_tool(
            method=many_text_documents,
            name="paginated_text_tool",
            paginate=True,
            max_docs=2,
        )

        # Verify the tool was registered
        assert "paginated_text_tool" in toolkit.tools

        # Test direct call returns all documents
        direct_result = toolkit.paginated_text_tool()
        assert len(direct_result) == 5
        for doc in direct_result:
            assert isinstance(doc, TextPage)

        # Test invoke call applies pagination
        invoke_result = toolkit.invoke_tool("paginated_text_tool", {})
        assert "documents" in invoke_result
        assert "page_number" in invoke_result
        assert len(invoke_result["documents"]) == 2
        assert invoke_result["page_number"] == 0
        assert invoke_result["has_next_page"] is True

        # Test we can get the next page via invoke
        invoke_result_page2 = toolkit.invoke_tool("paginated_text_tool", {"page": 1})
        assert len(invoke_result_page2["documents"]) == 2
        assert (
            invoke_result_page2["documents"][0]["id"]
            != invoke_result["documents"][0]["id"]
        )


class TestTypeEquivalence:
    """Test that PaginatedResponse is now properly recognized as a Sequence[Document]."""

    def test_paginated_response_implements_sequence_protocol(self) -> None:
        """Test that PaginatedResponse is recognized as implementing Sequence[Document]."""

        docs = [TextPage(id="1", content="Content 1")]
        response: PaginatedResponse[TextPage] = PaginatedResponse(
            results=docs,
            page_number=0,
            has_next_page=False,
            total_results=1,
            token_count=4,
        )

        # This should work now that PaginatedResponse implements Sequence[Document]
        assert isinstance(response, Sequence)

        # It should also work as a sequence in function calls
        def process_sequence(seq: Sequence[Page]) -> int:
            return len(seq)

        # This should not raise a type error
        result = process_sequence(response)
        assert result == 1


class TestGenericPaginatedResponseTypeConstraints:
    """Test that PaginatedResponse generic type constraints work properly."""

    def test_paginated_response_rejects_non_document_types(self) -> None:
        """Test that PaginatedResponse[T] only accepts Document subclasses at runtime."""
        # Note: These are compile-time checks that would be caught by mypy/type checkers
        # At runtime, Python's typing system is more permissive, but we can test the intent

        class NotADocument:
            id: str = "test"

        # This should work fine with proper Document types
        valid_docs = [TextPage(id="1", content="Content")]
        valid_response = PaginatedResponse[TextPage](
            results=valid_docs,
            page_number=0,
            has_next_page=False,
            total_results=1,
        )
        assert len(valid_response) == 1
        assert isinstance(valid_response[0], TextPage)

        # At runtime, Python allows this but type checkers should catch it
        # We test that the generic constraint is at least properly declared
        import typing

        if hasattr(typing, "get_args") and hasattr(typing, "get_origin"):
            # Check that PaginatedResponse has the right generic structure
            paginated_type = type(valid_response)
            # The generic information should be available for type checking tools
            assert hasattr(paginated_type, "__orig_bases__")

    def test_paginated_response_with_document_subclasses(self) -> None:
        """Test that PaginatedResponse works correctly with various Document subclasses."""

        # Test with TextDocument
        text_docs = [TextPage(id="1", content="Text content")]
        text_response: PaginatedResponse[TextPage] = PaginatedResponse(
            results=text_docs,
            page_number=0,
            has_next_page=False,
            total_results=1,
        )

        # Test with custom Document subclass
        class CustomDocument(Page):
            custom_field: str = "custom"

            def __init__(self, **data: Any) -> None:
                super().__init__(**data)

        custom_docs = [CustomDocument(id="2", custom_field="value")]
        custom_response: PaginatedResponse[CustomDocument] = PaginatedResponse(
            results=custom_docs,
            page_number=0,
            has_next_page=False,
            total_results=1,
        )

        # Verify type safety - the responses should maintain their specific types
        assert isinstance(text_response[0], TextPage)
        assert hasattr(text_response[0], "content")

        assert isinstance(custom_response[0], CustomDocument)
        assert hasattr(custom_response[0], "custom_field")
        assert custom_response[0].custom_field == "value"

        # Both should be assignable to PaginatedResponse[Document] for polymorphism
        def process_any_docs(response: PaginatedResponse[Page]) -> int:
            return len(response)

        assert process_any_docs(text_response) == 1
        assert process_any_docs(custom_response) == 1
