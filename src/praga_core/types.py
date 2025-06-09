from collections.abc import Sequence as SequenceABC
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional, Sequence, Union, overload


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
class PaginatedResponse(SequenceABC[Document]):
    documents: Sequence[Document]
    metadata: PageMetadata

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
