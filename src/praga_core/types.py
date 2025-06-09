import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, Tuple


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


CacheInvalidator = Callable[[str, Dict[str, Any]], bool]
