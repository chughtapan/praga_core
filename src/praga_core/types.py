import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple, Union


@dataclass
class Document:
    id: str
    content: str
    metadata: Dict[str, Any] | None = None


@dataclass
class PageMetadata:
    page_number: int
    has_next_page: bool
    total_documents: Optional[int] = None
    token_count: Optional[int] = None


@dataclass
class PaginatedResponse:
    documents: Sequence[Document]
    metadata: PageMetadata


@dataclass
class FunctionInvocation:
    tool_name: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]

    def serialise(self) -> str:
        payload = {
            "tool": self.tool_name,
            "args": self.args,
            "kwargs": tuple(sorted(self.kwargs.items())),
        }
        return json.dumps(payload, sort_keys=True, default=str)


# ========================================================
# ================  Tool Type Definitions  ==============
# ========================================================

# Valid return types for retriever tools
ToolReturnType = Union[Sequence[Document], PaginatedResponse]

# Function signature for a valid retriever tool
ToolFunction = Callable[..., ToolReturnType]

# Function that returns only Document sequences (used for pagination input)
DocumentSequenceFunction = Callable[..., Sequence[Document]]

# Function that returns paginated results
PaginatedFunction = Callable[..., PaginatedResponse]

# Cache invalidation function
CacheInvalidator = Callable[[str, Dict[str, Any]], bool]
