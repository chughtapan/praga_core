import json
import math
from abc import ABC
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


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
        return json.dumps(self.model_dump(), indent=2)

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


@dataclass
class DocumentReference:
    """Document reference for agent results."""

    id: str
    type: str
    score: float = 0.0
    explanation: str = ""
    document: Optional[Document] = None
