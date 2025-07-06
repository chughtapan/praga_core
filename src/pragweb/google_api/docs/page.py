"""Google Docs page definitions for headers and chunks."""

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from pydantic import BeforeValidator, Field

from praga_core.types import Page, PageURI


def _ensure_utc(v: datetime | None) -> datetime | None:
    if v is None:
        return v
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


class GDocHeader(Page):
    """A header page representing Google Docs document metadata with chunk index."""

    document_id: str = Field(description="Google Docs document ID", exclude=True)
    title: str = Field(description="Document title")
    summary: str = Field(description="Document summary (first 500 chars)")
    created_time: Annotated[datetime, BeforeValidator(_ensure_utc)] = Field(
        description="Document creation timestamp", exclude=True
    )
    modified_time: Annotated[datetime, BeforeValidator(_ensure_utc)] = Field(
        description="Document last modified timestamp", exclude=True
    )
    owner: Optional[str] = Field(None, description="Document owner/creator email")
    word_count: int = Field(description="Total document word count")
    chunk_count: int = Field(description="Total number of chunks")
    chunk_uris: List[PageURI] = Field(
        description="List of chunk URIs for this document"
    )
    permalink: str = Field(description="Google Docs permalink URL", exclude=True)


class GDocChunk(Page):
    """A chunk page representing a portion of a Google Docs document."""

    document_id: str = Field(description="Google Docs document ID", exclude=True)
    chunk_index: int = Field(description="Chunk index within the document")
    chunk_title: str = Field(description="Chunk title (first few words)")
    content: str = Field(description="Chunk content")
    doc_title: str = Field(description="Parent document title")
    prev_chunk_uri: Optional[PageURI] = Field(None, description="URI of previous chunk")
    next_chunk_uri: Optional[PageURI] = Field(None, description="URI of next chunk")
    header_uri: PageURI = Field(description="URI of the parent document header")
    permalink: str = Field(description="Google Docs permalink URL", exclude=True)
