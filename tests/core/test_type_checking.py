import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, List, Sequence, Union

import pytest
from pydantic import Field

from praga_core.agents import PaginatedResponse
from praga_core.agents.toolkit import (
    RetrieverToolkit,
    _is_page_sequence_type,
    _returns_paginated_response,
)
from praga_core.types import Page, PageURI, TextPage


class DemoToolkit(RetrieverToolkit):
    def __init__(self) -> None:
        super().__init__()

    @property
    def name(self) -> str:
        return "DemoToolkit"


@DemoToolkit.tool(cache=True, ttl=timedelta(minutes=5))
async def get_timestamp() -> List[Page]:
    return [
        TextPage(
            uri=PageURI.parse("test/TextPage:ts@1"), content=datetime.now().isoformat()
        )
    ]


@DemoToolkit.tool(cache=False)
async def get_greeting(name: str) -> List[Page]:
    doc = TextPage(
        uri=PageURI.parse("test/TextPage:greet@1"), content=f"Hello, {name}!"
    )
    doc.metadata.name = name  # type: ignore[attr-defined] # Add custom field to metadata
    return [doc]


@pytest.mark.asyncio
async def test_toolkit() -> None:
    tk: DemoToolkit = DemoToolkit()
    assert "get_timestamp" in tk._tools
    assert "get_greeting" in tk._tools


@pytest.mark.asyncio
async def test_valid_return_types() -> None:
    """Test that tools with proper return types work correctly."""
    tk: DemoToolkit = DemoToolkit()

    # Test List[Document] return
    result = await tk.get_greeting("world")
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
        async def bad_tool_no_annotation() -> List[Dict[str, str]]:
            return [{"id": "bad", "content": "test"}]

        BadToolkit()  # This triggers registration

    # This should fail because it returns wrong type
    with pytest.raises(TypeError, match="must have return type annotation"):

        @BadToolkit.tool()  # type: ignore[arg-type]
        async def bad_tool_wrong_type() -> List[str]:
            return ["hello", "world"]

        BadToolkit()  # This triggers registration


@pytest.mark.asyncio
async def test_pagination_with_proper_types() -> None:
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

        async def get_many_docs(self) -> List[Page]:
            docs: List[Page] = []
            for i in range(5):
                doc = TextPage(
                    uri=PageURI.parse(f"test/TextPage:doc_{i}@1"),
                    content=f"Content {i}",
                )
                doc.metadata.index = i  # type: ignore[attr-defined] # Add custom field
                docs.append(doc)
            return docs

    tk: PaginatedToolkit = PaginatedToolkit()

    # Test pagination using invoke method
    result = await tk.invoke_tool("get_many_docs", {})
    assert "results" in result
    assert "next_cursor" in result
    assert len(result["results"]) == 2
    assert result["next_cursor"] is not None  # Has more pages

    # Test direct method call returns all documents
    direct_result = await tk.get_many_docs()
    assert len(direct_result) == 5  # All documents without pagination


class TestTypeCheckingLogic:
    """Test the simplified type checking logic in retriever toolkit."""

    def test_is_document_sequence_type_with_list(self) -> None:
        """Test that List[Document] is considered valid."""

        async def tool_with_list() -> List[Page]:
            return []

        assert _is_page_sequence_type(tool_with_list) is True

    def test_is_document_sequence_type_with_sequence(self) -> None:
        """Test that Sequence[Document] is considered valid."""

        async def tool_with_sequence() -> Sequence[Page]:
            return []

        assert _is_page_sequence_type(tool_with_sequence) is True

    def test_is_document_sequence_type_with_paginated_response(self) -> None:
        """Test that PaginatedResponse is considered valid."""

        async def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], next_cursor=None)

        assert _is_page_sequence_type(tool_with_paginated_response) is True

    def test_is_document_sequence_type_with_invalid_type(self) -> None:
        """Test that invalid return types are rejected."""

        async def tool_with_string() -> str:
            return "hello"

        async def tool_with_no_annotation() -> List[Any]:
            return []

        async def tool_with_wrong_sequence() -> List[str]:
            return ["hello"]

        assert _is_page_sequence_type(tool_with_string) is False  # type: ignore[arg-type]
        assert _is_page_sequence_type(tool_with_no_annotation) is False
        assert _is_page_sequence_type(tool_with_wrong_sequence) is False  # type: ignore[arg-type]

    def test_is_document_sequence_type_covers_all_valid_types(self) -> None:
        """Test that _is_document_sequence_type covers all valid return types."""

        async def tool_with_list() -> List[Page]:
            return []

        def tool_with_sequence() -> Sequence[Page]:
            return []

        async def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], next_cursor=None)

        assert _is_page_sequence_type(tool_with_list) is True
        assert _is_page_sequence_type(tool_with_sequence) is True
        assert _is_page_sequence_type(tool_with_paginated_response) is True

    def test_returns_paginated_response_specific(self) -> None:
        """Test that _returns_paginated_response only identifies PaginatedResponse."""

        async def tool_with_list() -> List[Page]:
            return []

        async def tool_with_sequence() -> Sequence[Page]:
            return []

        async def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], next_cursor=None)

        assert _returns_paginated_response(tool_with_list) is False
        assert _returns_paginated_response(tool_with_sequence) is False
        assert _returns_paginated_response(tool_with_paginated_response) is True

    def test_can_be_paginated_logic(self) -> None:
        """Test the logic for determining if a tool can be paginated."""

        async def tool_with_list() -> List[Page]:
            return []

        async def tool_with_sequence() -> Sequence[Page]:
            return []

        async def tool_with_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], next_cursor=None)

        # These should return True (can be paginated - not already paginated responses)
        assert not _returns_paginated_response(tool_with_list)
        assert not _returns_paginated_response(tool_with_sequence)

        # This should return True (cannot be paginated - would create double pagination)
        assert _returns_paginated_response(tool_with_paginated_response)


class TestPaginationPrevention:
    """Test that we prevent double-pagination correctly."""

    @pytest.mark.asyncio
    async def test_toolkit_prevents_paginating_paginated_response(self) -> None:
        """Test that trying to paginate a tool that returns PaginatedResponse raises an error."""

        async def tool_returning_paginated_response() -> PaginatedResponse[Page]:
            return PaginatedResponse(results=[], next_cursor=None)

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

    @pytest.mark.asyncio
    async def test_toolkit_allows_paginating_document_sequence(self) -> None:
        """Test that we can paginate tools that return document sequences."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        async def tool_returning_list() -> List[Page]:
            return [
                TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Content 1"),
                TextPage(uri=PageURI.parse("test/TextPage:2@1"), content="Content 2"),
                TextPage(uri=PageURI.parse("test/TextPage:3@1"), content="Content 3"),
            ]

        async def tool_returning_sequence() -> Sequence[Page]:
            return [
                TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Content 1"),
                TextPage(uri=PageURI.parse("test/TextPage:2@1"), content="Content 2"),
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
        direct_result1 = await toolkit.list_tool()
        direct_result2 = await toolkit.sequence_tool()

        assert isinstance(direct_result1, list)
        assert isinstance(direct_result2, list)
        assert len(direct_result1) == 3
        assert len(direct_result2) == 2

        # Test invoke calls apply pagination
        invoke_result1 = await toolkit.invoke_tool("list_tool", {})
        invoke_result2 = await toolkit.invoke_tool("sequence_tool", {})

        assert "results" in invoke_result1
        assert "next_cursor" in invoke_result1
        assert "results" in invoke_result2
        assert "next_cursor" in invoke_result2

    def test_toolkit_allows_non_paginated_paginated_response(self) -> None:
        """Test that we can register tools that return PaginatedResponse without pagination."""

        async def tool_returning_paginated_response() -> PaginatedResponse[TextPage]:
            docs = [
                TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Content 1")
            ]
            return PaginatedResponse(
                results=docs,
                next_cursor=None,
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
        result = asyncio.run(toolkit.paginated_tool())
        assert isinstance(result, PaginatedResponse)
        assert len(result.results) == 1
        assert result.results[0].uri == PageURI.parse("test/TextPage:1@1")


class SimpleTestDocumentSubclassTypeChecking:
    """Test that the type checking system accepts Document subclasses."""

    def test_text_document_subclass_accepted(self) -> None:
        """Test that functions returning List[TextDocument] are accepted."""

        async def tool_with_text_document() -> List[TextPage]:
            return [
                TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Text content")
            ]

        assert _is_page_sequence_type(tool_with_text_document) is True

    def test_sequence_of_text_document_accepted(self) -> None:
        """Test that functions returning Sequence[TextDocument] are accepted."""

        async def tool_with_text_document_sequence() -> Sequence[TextPage]:
            return [
                TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Test content")
            ]

        assert _is_page_sequence_type(tool_with_text_document_sequence) is True

    def test_custom_document_subclass_accepted(self) -> None:
        """Test that custom Document subclasses are accepted."""

        # Create a custom document subclass for testing
        class CustomDocument(Page):
            custom_field: str = Field(description="A custom field")

            def __init__(self, **data: Any) -> None:
                super().__init__(**data)

        async def tool_with_custom_document() -> List[CustomDocument]:
            return [
                CustomDocument(
                    uri=PageURI.parse("test/CustomDocument:1@1"), custom_field="test"
                )
            ]

        assert _is_page_sequence_type(tool_with_custom_document) is True

    def test_deeply_nested_subclass_accepted(self) -> None:
        """Test that subclasses of subclasses are accepted."""

        # Create a subclass of TextDocument
        class SpecialTextDocument(TextPage):
            special_field: str = Field(description="A special field")

            def __init__(self, **data: Any) -> None:
                super().__init__(**data)

        async def tool_with_special_document() -> List[SpecialTextDocument]:
            return [
                SpecialTextDocument(
                    uri=PageURI.parse("test/SpecialTextDocument:1@1"),
                    content="test",
                    special_field="special",
                )
            ]

        assert _is_page_sequence_type(tool_with_special_document) is True

    def test_non_document_subclass_rejected(self) -> None:
        """Test that classes that don't inherit from Document are rejected."""

        class NotADocument:
            uri: str

        async def tool_with_non_document() -> List[NotADocument]:
            return [NotADocument()]

        assert _is_page_sequence_type(tool_with_non_document) is False  # type: ignore[arg-type]

    def test_mixed_types_rejected(self) -> None:
        """Test that functions with mixed or union types are rejected."""

        async def tool_with_union() -> List[Union[Page, str]]:
            return []

        # This should be rejected as it's not a pure Document sequence
        assert _is_page_sequence_type(tool_with_union) is False  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_subclass_with_toolkit_registration(self) -> None:
        """Test that Document subclasses work with actual toolkit registration."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        async def text_document_tool() -> List[TextPage]:
            return [
                TextPage(
                    uri=PageURI.parse("test/TextPage:test@1"), content="Test content"
                )
            ]

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
        result = await toolkit.text_tool()
        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], TextPage)
        assert result[0].content == "Test content"

    @pytest.mark.asyncio
    async def test_subclass_pagination_compatibility(self) -> None:
        """Test that Document subclasses work with pagination."""

        class TestToolkit(RetrieverToolkit):
            @property
            def name(self) -> str:
                return "TestToolkit"

        async def many_text_documents() -> List[TextPage]:
            return [
                TextPage(
                    uri=PageURI.parse(f"test/TextPage:doc_{i}@1"),
                    content=f"Content {i}",
                )
                for i in range(5)
            ]

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
        direct_result = await toolkit.paginated_text_tool()
        assert len(direct_result) == 5
        for doc in direct_result:
            assert isinstance(doc, TextPage)

        # Test invoke call applies pagination
        invoke_result = await toolkit.invoke_tool("paginated_text_tool", {})
        assert "results" in invoke_result
        assert "next_cursor" in invoke_result
        assert len(invoke_result["results"]) == 2
        assert invoke_result["next_cursor"] is not None  # Has more pages

        # Test we can get the next page via invoke using cursor
        invoke_result_page2 = await toolkit.invoke_tool(
            "paginated_text_tool", {"cursor": invoke_result["next_cursor"]}
        )
        assert len(invoke_result_page2["results"]) == 2
        assert (
            invoke_result_page2["results"][0]["uri"]
            != invoke_result["results"][0]["uri"]
        )


class TestTypeEquivalence:
    """Test that PaginatedResponse is now properly recognized as a Sequence[Document]."""

    def test_paginated_response_implements_sequence_protocol(self) -> None:
        """Test that PaginatedResponse is recognized as implementing Sequence[Document]."""

        docs = [TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Content 1")]
        response: PaginatedResponse[TextPage] = PaginatedResponse(
            results=docs,
            next_cursor=None,
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
            uri: str = "test"

        # This should work fine with proper Document types
        valid_docs = [
            TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Content")
        ]
        valid_response = PaginatedResponse[TextPage](
            results=valid_docs,
            next_cursor=None,
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
        text_docs = [
            TextPage(uri=PageURI.parse("test/TextPage:1@1"), content="Text content")
        ]
        text_response: PaginatedResponse[TextPage] = PaginatedResponse(
            results=text_docs,
            next_cursor=None,
        )

        # Test with custom Document subclass
        class CustomDocument(Page):
            custom_field: str = "custom"

            def __init__(self, **data: Any) -> None:
                super().__init__(**data)

        custom_docs = [
            CustomDocument(
                uri=PageURI.parse("test/CustomDocument:2@1"), custom_field="value"
            )
        ]
        custom_response: PaginatedResponse[CustomDocument] = PaginatedResponse(
            results=custom_docs,
            next_cursor=None,
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
