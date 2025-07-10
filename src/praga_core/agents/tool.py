"""Tool wrapper for RetrieverToolkit with pagination support."""

import inspect
from collections.abc import Sequence as ABCSequence
from dataclasses import dataclass
from functools import cached_property
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    Iterator,
    List,
    Optional,
    Sequence,
    TypeVar,
    Union,
    overload,
)

from praga_core.types import Page

# Type variable bound to Document for generic pagination
T = TypeVar("T", bound=Page)

# Tool callback types
ToolCallback = Callable[[str, Sequence[Page]], None]


@dataclass(frozen=True)
class PaginatedResponse(Generic[T], ABCSequence[T]):
    """Container for paginated tool responses that implements Sequence[T]."""

    results: Sequence[T]
    next_cursor: Optional[str] = None

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        result = {
            "results": [doc.model_dump(mode="json") for doc in self.results],
            "next_cursor": self.next_cursor,
        }

        return result

    # Sequence[Document] protocol implementation
    def __len__(self) -> int:
        """Return the number of documents in this page."""
        return len(self.results)

    @overload
    def __getitem__(self, index: int) -> T: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[T]: ...

    def __getitem__(self, index: Union[int, slice]) -> Union[T, Sequence[T]]:
        """Get a document by index or a sequence of documents by slice."""
        return self.results[index]

    def __iter__(self) -> Iterator[T]:
        """Iterate over the documents."""
        return iter(self.results)

    def __bool__(self) -> bool:
        """Return True if there are any documents."""
        return len(self.results) > 0

    def __contains__(self, item: object) -> bool:
        """Check if a document is in this response."""
        return item in self.results


# Now PaginatedResponse is defined, so we can reference it
ToolReturnType = Union[Sequence[Page], PaginatedResponse[Page]]
ToolFunction = Callable[..., Awaitable[ToolReturnType]]


@dataclass
class ToolMetadata:
    """Metadata about a tool."""

    name: str
    description: str
    parameters: Dict[str, inspect.Parameter]
    return_type: type


class Tool:
    """Tool wrapper with optional pagination support."""

    def __init__(
        self,
        func: ToolFunction,
        name: str,
        description: str = "",
        page_size: Optional[int] = None,
        max_tokens: Optional[int] = None,
    ):
        """Initialize the tool wrapper.

        Args:
            func: The toolkit function to wrap
            name: Name of the tool
            description: Description of the tool
            page_size: Optional size for paginated results. If None, pagination is disabled
            max_tokens: Optional token limit per page for paginated results

        Raises:
            ValueError: If page_size is less than 1
        """
        self.func = func
        self.name = name
        self.description = description or func.__doc__ or ""
        self.page_size = page_size
        self.max_tokens = max_tokens
        self.metadata = self._extract_metadata()

        if self.page_size is not None:
            if self.page_size < 1:
                raise ValueError("page_size must be a positive integer")

    def _prepare_arguments(
        self, raw_input: Union[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Prepare the input arguments for tool execution."""
        if isinstance(raw_input, str):
            # If input is a string, map it to the first parameter
            param_name = next(iter(self.parameters))
            return {param_name: raw_input}
        return raw_input

    def _serialize_result(
        self,
        result: Union[Sequence[Page], PaginatedResponse[Page]],
    ) -> Dict[str, Any]:
        """Serialize the tool result into a JSON-serializable format."""
        if isinstance(result, PaginatedResponse):
            return result.to_json_dict()
        else:
            # Handle sequence of documents
            return {"results": [doc.model_dump(mode="json") for doc in result]}

    def _update_paginated_docstring(self, doc: str) -> str:
        """Update docstring to include pagination parameters and return type."""
        doc_lines = doc.split("\n")

        # Add Args section if not present
        if "Args:" not in doc:
            doc += "\n\n    Args:"
            doc_lines = doc.split("\n")

        # Add cursor parameter to Args
        args_idx = next(i for i, line in enumerate(doc_lines) if "Args:" in line)
        doc_lines.insert(
            args_idx + 1, "        cursor: Cursor token for pagination (optional)"
        )

        # Replace or add Returns section
        returns_idx = next(
            (i for i, line in enumerate(doc_lines) if "Returns:" in line), None
        )
        returns_content = [
            "    Returns:",
            "        PaginatedResponse: Contains results and optional next_cursor for pagination.",
        ]

        if returns_idx is not None:
            # Remove old Returns section
            next_section_idx = next(
                (
                    i
                    for i, line in enumerate(
                        doc_lines[returns_idx + 1 :], returns_idx + 1
                    )
                    if line.strip() and not line.startswith(" ")
                ),
                len(doc_lines),
            )
            doc_lines[returns_idx:next_section_idx] = returns_content
        else:
            # Add new Returns section
            doc_lines.extend([""] + returns_content)

        return "\n".join(doc_lines)

    def _extract_metadata(self) -> ToolMetadata:
        """Extract metadata from the function signature."""
        sig = inspect.signature(self.func)

        # Add cursor parameter if tool is paginated and doesn't already have one
        params = dict(sig.parameters)
        if self.page_size is not None and "cursor" not in params:
            params["cursor"] = inspect.Parameter(
                "cursor",
                inspect.Parameter.KEYWORD_ONLY,
                default=None,
                annotation=Optional[str],
            )

            # Update docstring with pagination information
            self.description = self._update_paginated_docstring(self.description)

        return ToolMetadata(
            name=self.name,
            description=self.description,
            parameters=params,
            return_type=sig.return_annotation,
        )

    def _parse_cursor(self, cursor: Optional[str]) -> int:
        """Parse cursor string to get starting position for pagination."""
        if cursor is None:
            return 0

        try:
            start_pos = int(cursor)
        except ValueError:
            raise ValueError("Invalid cursor format")

        if start_pos < 0:
            raise ValueError("Cursor position must be >= 0")

        return start_pos

    def _create_next_cursor(
        self, start_pos: int, documents_returned: int, total_results: int
    ) -> Optional[str]:
        """Create next cursor if there are more results available."""
        documents_processed = start_pos + documents_returned
        has_next_page = documents_processed < total_results
        return str(documents_processed) if has_next_page else None

    def _paginate_results(
        self, results: List[Page], cursor: Optional[str]
    ) -> PaginatedResponse[Page]:
        """Paginate results with both document count and token limits."""
        if not self.page_size:
            raise RuntimeError("_paginate_results called on non-paginated tool")

        total_results = len(results)
        start_pos = self._parse_cursor(cursor)

        # Extract page slice
        end_pos = start_pos + self.page_size
        page_documents = results[start_pos:end_pos]
        next_cursor = self._create_next_cursor(
            start_pos, len(page_documents), total_results
        )

        return PaginatedResponse(
            results=page_documents,
            next_cursor=next_cursor,
        )

    async def _handle_native_pagination(self, **kwargs: Any) -> PaginatedResponse[Page]:
        """Handle tools that support native pagination (accept cursor parameter)."""
        results = await self.func(**kwargs)

        # If function returns PaginatedResponse, use it directly
        assert isinstance(results, PaginatedResponse)
        return results

    async def _handle_client_side_pagination(
        self, **kwargs: Any
    ) -> PaginatedResponse[Page]:
        """Handle tools that need client-side pagination (don't accept cursor parameter)."""
        # Extract cursor from kwargs before calling function
        cursor = kwargs.pop("cursor", None)

        # Call the function without cursor parameter
        results = await self.func(**kwargs)

        # Convert to list if needed
        if not isinstance(results, list):
            results = list(results)
        return self._paginate_results(results, cursor)

    def _supports_native_pagination(self) -> bool:
        """Check if the underlying function accepts a cursor parameter."""
        sig = inspect.signature(self.func)
        return "cursor" in sig.parameters

    async def __call__(self, **kwargs: Any) -> ToolReturnType:
        """Execute the tool with the given arguments."""
        # No pagination configured - call function directly
        if not self.page_size:
            return await self.func(**kwargs)

        # Route to appropriate pagination handler
        if self._supports_native_pagination():
            return await self._handle_native_pagination(**kwargs)
        else:
            return await self._handle_client_side_pagination(**kwargs)

    async def invoke(
        self,
        raw_input: Union[str, Dict[str, Any]],
        callbacks: Optional[List[ToolCallback]] = None,
    ) -> Dict[str, Any]:
        """Execute the tool with the given input and serialize the response."""
        try:
            kwargs = self._prepare_arguments(raw_input)
            result = await self(**kwargs)
            if len(result) == 0:
                return {
                    "response_code": "error_no_documents_found",
                    "references": [],
                    "error_message": "No matching documents found",
                }

            # Execute callbacks before serialization if provided
            if callbacks:
                # Extract the actual pages from the result
                pages = (
                    result.results if isinstance(result, PaginatedResponse) else result
                )
                for callback in callbacks:
                    callback(self.name, pages)

            return self._serialize_result(result)

        except ValueError as e:
            # Handle specific "No matching documents found" error
            if e.__class__ is ValueError and str(e) == "No matching documents found":
                return {
                    "response_code": "error_no_documents_found",
                    "references": [],
                    "error_message": str(e),
                }
            raise
        except Exception as e:
            error_msg = f"Tool execution failed - {str(e)}"
            raise ValueError(error_msg) from e

    @property
    def parameters(self) -> Dict[str, inspect.Parameter]:
        """Get the parameters of the tool function."""
        return self.metadata.parameters

    @cached_property
    def formatted_description(self) -> str:
        """Get a formatted description of the tool including parameters."""
        # Get base parameters
        params = [
            f"{name}: {param.annotation.__name__ if param.annotation != inspect.Parameter.empty else 'Any'}"
            for name, param in self.metadata.parameters.items()
        ]

        # Join parameters and add description
        params_str = ", ".join(params)
        description = f"{self.description}"
        if self.page_size is not None:
            description += f" (Paginated with {self.page_size} items per page"
            if self.max_tokens is not None:
                description += f", max {self.max_tokens} tokens"
            description += ")"

        return f"- {self.name}({params_str}): {description}"
