"""Provider-agnostic document page definitions."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, List, Optional

from pydantic import BeforeValidator, Field

from praga_core.types import Page, PageURI


def _ensure_utc(v: datetime | None) -> datetime | None:
    if v is None:
        return v
    if v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc)


class DocumentType(str, Enum):
    """Document type enumeration."""

    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"
    PRESENTATION = "presentation"
    FORM = "form"
    DRAWING = "drawing"
    FOLDER = "folder"
    OTHER = "other"


class DocumentPermission(str, Enum):
    """Document permission levels."""

    OWNER = "owner"
    EDITOR = "editor"
    COMMENTER = "commenter"
    VIEWER = "viewer"
    NONE = "none"


class DocumentHeader(Page):
    """A header page representing document metadata with chunk index."""

    # Provider-specific metadata
    provider_document_id: str = Field(
        description="Provider-specific document ID", exclude=True
    )

    # Core document fields
    title: str = Field(description="Document title")
    summary: str = Field(description="Document summary (first 500 chars)")

    # Timestamps
    created_time: Annotated[datetime, BeforeValidator(_ensure_utc)] = Field(
        description="Document creation timestamp", exclude=True
    )
    modified_time: Annotated[datetime, BeforeValidator(_ensure_utc)] = Field(
        description="Document last modified timestamp", exclude=True
    )

    # Ownership and permissions
    owner: Optional[str] = Field(None, description="Document owner/creator email")

    # Document metrics
    word_count: int = Field(description="Total document word count")
    chunk_count: int = Field(description="Total number of chunks")

    # Chunk references
    chunk_uris: List[PageURI] = Field(
        description="List of chunk URIs for this document"
    )

    # URLs and links
    permalink: str = Field(
        description="Provider-specific document permalink URL", exclude=True
    )


class DocumentChunk(Page):
    """A chunk page representing a portion of a document."""

    # Provider-specific metadata
    provider_document_id: str = Field(
        description="Provider-specific document ID", exclude=True
    )

    # Chunk identification
    chunk_index: int = Field(description="Chunk index within the document")
    chunk_title: str = Field(description="Chunk title (first few words)")

    # Content
    content: str = Field(description="Chunk content")

    # Parent document information
    doc_title: str = Field(description="Parent document title")
    header_uri: PageURI = Field(description="URI of the parent document header")

    # Navigation
    prev_chunk_uri: Optional[PageURI] = Field(None, description="URI of previous chunk")
    next_chunk_uri: Optional[PageURI] = Field(None, description="URI of next chunk")

    # Links
    permalink: str = Field(
        description="Provider-specific document permalink URL", exclude=True
    )


class DocumentComment(Page):
    """A page representing a comment on a document."""

    # Provider-specific metadata
    provider_comment_id: str = Field(
        description="Provider-specific comment ID", exclude=True
    )
    provider_document_id: str = Field(
        description="Provider-specific document ID", exclude=True
    )

    # Comment content
    content: str = Field(description="Comment content")
    author: str = Field(description="Comment author email")
    author_name: Optional[str] = Field(None, description="Comment author name")

    # Timestamps
    created_time: Annotated[datetime, BeforeValidator(_ensure_utc)] = Field(
        description="Comment creation timestamp"
    )
    modified_time: Optional[Annotated[datetime, BeforeValidator(_ensure_utc)]] = Field(
        None, description="Comment last modified timestamp"
    )

    # Comment metadata
    is_resolved: bool = Field(default=False, description="Whether comment is resolved")
    reply_count: int = Field(default=0, description="Number of replies to this comment")

    # Document reference
    document_header_uri: PageURI = Field(
        description="URI of the parent document header"
    )

    # Position information
    quoted_text: Optional[str] = Field(
        None, description="Text that was quoted/selected"
    )
    anchor_text: Optional[str] = Field(None, description="Anchor text for the comment")
