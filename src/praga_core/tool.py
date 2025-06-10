"""Tool wrapper for RetrieverToolkit with pagination support."""

import inspect
from collections.abc import Sequence as ABCSequence
from dataclasses import dataclass
from functools import cached_property
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Union,
    overload,
)

from .types import Document


@dataclass(frozen=True)
class PaginatedResponse(ABCSequence[Document]):
    """Container for paginated tool responses that implements Sequence[Document]."""

    documents: Sequence[Document]
    page_number: int
    has_next_page: bool
    total_documents: Optional[int] = None
    token_count: Optional[int] = None

    def to_json_dict(self) -> Dict[str, Any]:
        """Convert to a JSON-serializable dictionary."""
        return {
            "documents": [doc.model_dump(mode="json") for doc in self.documents],
            "page_number": self.page_number,
            "has_next_page": self.has_next_page,
            "total_documents": self.total_documents,
            "token_count": self.token_count,
        }

    # Sequence[Document] protocol implementation
    def __len__(self) -> int:
        """Return the number of documents in this page."""
        return len(self.documents)

    @overload
    def __getitem__(self, index: int) -> Document: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[Document]: ...

    def __getitem__(
        self, index: Union[int, slice]
    ) -> Union[Document, Sequence[Document]]:
        """Get a document by index or a sequence of documents by slice."""
        return self.documents[index]

    def __iter__(self) -> Iterator[Document]:
        """Iterate over the documents."""
        return iter(self.documents)

    def __bool__(self) -> bool:
        """Return True if there are any documents."""
        return len(self.documents) > 0

    def __contains__(self, item: object) -> bool:
        """Check if a document is in this response."""
        return item in self.documents


# Now PaginatedResponse is defined, so we can reference it
ToolFunction = Callable[..., Union[Sequence[Document], PaginatedResponse]]


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
        result: Union[Sequence[Document], PaginatedResponse],
    ) -> Dict[str, Any]:
        """Serialize the tool result into a JSON-serializable format."""
        if isinstance(result, PaginatedResponse):
            return result.to_json_dict()
        else:
            # Handle sequence of documents
            return {"documents": [doc.model_dump(mode="json") for doc in result]}

    def _update_paginated_docstring(self, doc: str) -> str:
        """Update docstring to include pagination parameters and return type."""
        doc_lines = doc.split("\n")

        # Add Args section if not present
        if "Args:" not in doc:
            doc += "\n\n    Args:"
            doc_lines = doc.split("\n")

        # Add page parameter to Args
        args_idx = next(i for i, line in enumerate(doc_lines) if "Args:" in line)
        doc_lines.insert(args_idx + 1, "        page: Page number (starting from 0)")

        # Replace or add Returns section
        returns_idx = next(
            (i for i, line in enumerate(doc_lines) if "Returns:" in line), None
        )
        returns_content = [
            "    Returns:",
            "        PaginatedResponse: Contains requested page of documents with pagination metadata.",
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

        # Add page parameter if tool is paginated and doesn't already have one
        params = dict(sig.parameters)
        if self.page_size is not None and "page" not in params:
            params["page"] = inspect.Parameter(
                "page", inspect.Parameter.KEYWORD_ONLY, default=0, annotation=int
            )

            # Update docstring with pagination information
            self.description = self._update_paginated_docstring(self.description)

        return ToolMetadata(
            name=self.name,
            description=self.description,
            parameters=params,
            return_type=sig.return_annotation,
        )

    def _paginate_results(
        self, results: List[Document], page: int
    ) -> PaginatedResponse:
        """Paginate results with both document count and token limits."""
        if not self.page_size:
            raise RuntimeError("_paginate_results called on non-paginated tool")

        total_results = len(results)

        if page < 0:
            raise ValueError("Page number must be >= 0")

        # Calculate page slice boundaries
        page_start = page * self.page_size
        page_end = page_start + self.page_size
        page_documents = results[page_start:page_end]

        # Apply token budget limit within the page if max_tokens is set
        final_documents: List[Document] = []
        total_tokens = 0

        if self.max_tokens is not None:
            for i, document in enumerate(page_documents):
                doc_tokens = document.metadata.token_count or 0

                # Always include at least one document per page, even if it exceeds token limit
                if i == 0:
                    final_documents.append(document)
                    total_tokens += doc_tokens
                elif total_tokens + doc_tokens <= self.max_tokens:
                    final_documents.append(document)
                    total_tokens += doc_tokens
                else:
                    break
        else:
            # No token limit, use all documents in the page
            final_documents = list(page_documents)
            total_tokens = sum(doc.metadata.token_count or 0 for doc in final_documents)

        # Calculate if there are more documents available beyond what we returned
        # This accounts for documents filtered out due to token limits
        documents_returned = len(final_documents)
        documents_processed = page_start + documents_returned
        has_next_page = documents_processed < total_results

        return PaginatedResponse(
            documents=final_documents,
            page_number=page,
            has_next_page=has_next_page,
            total_documents=total_results,
            token_count=total_tokens,
        )

    def __call__(self, **kwargs: Any) -> Union[Sequence[Document], PaginatedResponse]:
        """Execute the tool with the given arguments."""
        if not self.page_size:
            # No pagination, call directly
            return self.func(**kwargs)

        # Extract page parameter
        page = kwargs.pop("page", 0)
        if page < 0:
            raise ValueError("Page number must be >= 0")

        # Call the function to get all results (caching handled by toolkit)
        results = self.func(**kwargs)

        # Convert to list if needed
        if not isinstance(results, list):
            results = list(results)

        # Handle no results case
        if len(results) == 0:
            raise ValueError("No matching documents found")

        return self._paginate_results(results, page)

    def invoke(self, raw_input: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Execute the tool with the given input and serialize the response."""
        try:
            kwargs = self._prepare_arguments(raw_input)
            result = self(**kwargs)
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
