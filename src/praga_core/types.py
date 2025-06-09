from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence


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
