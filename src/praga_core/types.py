import json
import math
from abc import ABC
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator


class DocumentMetadata(BaseModel):
    """Metadata for documents with extensible fields."""

    model_config = ConfigDict(extra="allow")

    token_count: Optional[int] = Field(
        None, description="Number of tokens in the document"
    )


class Document(BaseModel, ABC):
    """A document with an ID, content, and optional metadata."""

    model_config = ConfigDict(
        json_encoders={datetime: lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S")},
    )

    id: str = Field()
    _metadata: DocumentMetadata = PrivateAttr(
        default_factory=lambda: DocumentMetadata(token_count=None)
    )

    @property
    def metadata(self) -> DocumentMetadata:
        """Access to document metadata."""
        return self._metadata

    @property
    def text(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.text


class TextDocument(Document):
    """A document with text content."""

    content: str = Field(description="The text content of the document")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = math.ceil(len(self.content.split()) * 4 / 3)


class DocumentReference(BaseModel):
    """Document reference for agent results."""

    id: str = Field(description="Unique identifier for the document")
    type: str = Field(description="Document type (schema name)", default="Document")
    score: float = Field(description="Score of the document", default=0.0)
    explanation: str = Field(description="Explanation of the document", default="")
    _document: Optional[Document] = PrivateAttr(default=None)

    @field_validator("id", mode="before")
    @classmethod
    def coerce_id_to_string(cls, v: Any) -> str:
        """Coerce non-string IDs to strings."""
        return str(v)

    @property
    def document(self) -> Document:
        if self._document is None:
            raise KeyError(f"No document associated with reference: {self.id}")
        return self._document

    @document.setter
    def document(self, document: Document) -> None:
        self._document = document
