from __future__ import annotations

import json
import logging
import math
import re
from abc import ABC
from datetime import datetime
from typing import Annotated, Any, List, Optional, Union, overload

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PrivateAttr,
    model_serializer,
)

logger = logging.getLogger(__name__)


class PageURI(BaseModel):
    """A structured URI for identifying pages with root/type:id@version format."""

    root: str = Field(description="Root identifier for the server/context")
    type: str = Field(description="Type of the page")
    id: str = Field(description="Unique identifier within the type")
    version: int = Field(description="Version number of the page", default=1)

    def __init__(
        self, root: str, type: str, id: str, version: int = 1, **data: Any
    ) -> None:
        """Initialize PageURI with validation."""
        # Validate that components don't contain forbidden characters
        if "/" in type or ":" in type or "@" in type:
            raise ValueError(f"Type cannot contain '/', ':', or '@' characters: {type}")
        if ":" in id or "@" in id:
            raise ValueError(f"ID cannot contain ':' or '@' characters: {id}")
        if version < 0:
            raise ValueError(f"Version must be non-negative: {version}")

        super().__init__(root=root, type=type, id=id, version=version, **data)

    @overload
    @classmethod
    def parse(cls, uri: PageURI) -> "PageURI":
        """Parse a PageURI object."""
        ...

    @overload
    @classmethod
    def parse(cls, uri: dict[str, Any]) -> "PageURI":
        """Parse a URI dict into a PageURI object."""
        ...

    @overload
    @classmethod
    def parse(cls, uri: str) -> "PageURI":
        """Parse a URI string into a PageURI object."""
        ...

    @classmethod
    def parse(cls, uri: Union[PageURI, str, dict[str, Any]]) -> "PageURI":
        """Parse a URI from various formats into a PageURI object."""
        if isinstance(uri, PageURI):
            return uri
        elif isinstance(uri, dict):
            return cls(**uri)
        else:
            assert isinstance(uri, str)
            return cls._parse_str(uri)

    @classmethod
    def _parse_str(cls, uri: str) -> "PageURI":
        # Regex pattern with optional version: root/type:id[@version]
        pattern = re.compile(r"^([^/]*)/([^:]+):([^@]+)(?:@(\d+))?$")
        match = pattern.match(uri)

        if not match:
            raise ValueError(
                f"Invalid URI format: {uri}. Expected: root/type:id@version or root/type:id"
            )

        root, type_name, id_part, version_str = match.groups()

        # Default to version 1 if not specified
        if version_str is None:
            version = 1
        else:
            try:
                version = int(version_str)
            except ValueError:
                raise ValueError(f"Invalid version number: {version_str}")

        return cls(root=root, type=type_name, id=id_part, version=version)

    def __str__(self) -> str:
        """Return string representation in root/type:id@version format."""
        return f"{self.root}/{self.type}:{self.id}@{self.version}"

    def __hash__(self) -> int:
        """Make PageURI hashable for use as dict keys."""
        return hash((self.root, self.type, self.id, self.version))

    def __eq__(self, other: Any) -> bool:
        """Equality comparison for PageURI objects."""
        if not isinstance(other, PageURI):
            return False
        return (
            self.root == other.root
            and self.type == other.type
            and self.id == other.id
            and self.version == other.version
        )

    @model_serializer
    def ser_model(self) -> str:
        """Serialize PageURI as string representation."""
        return str(self)


class Page(BaseModel, ABC):
    """A document with a URI, content, and optional metadata."""

    uri: Annotated[PageURI, BeforeValidator(PageURI.parse)] = Field(
        description="Structured URI for the page"
    )
    parent_uri: Optional[Annotated[PageURI, BeforeValidator(PageURI.parse)]] = Field(
        None, description="Optional parent page URI for provenance tracking"
    )
    _metadata: PageMetadata = PrivateAttr(
        default_factory=lambda: PageMetadata(token_count=None)
    )

    model_config = ConfigDict(
        json_encoders={datetime: lambda dt: dt.strftime("%Y-%m-%d %H:%M:%S")},
    )

    @property
    def metadata(self) -> PageMetadata:
        """Access to document metadata."""
        return self._metadata

    @property
    def text(self) -> str:
        return json.dumps(self.model_dump(mode="json"), indent=2)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:
        return self.text


class PageMetadata(BaseModel):
    """Metadata for documents with extensible fields."""

    model_config = ConfigDict(extra="allow")

    token_count: Optional[int] = Field(
        None, description="Number of tokens in the document"
    )


class TextPage(Page):
    """A document with text content."""

    content: str = Field(description="The text content of the document")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self._metadata.token_count = math.ceil(len(self.content.split()) * 4 / 3)


class PageReference(BaseModel):
    """Document reference for agent results."""

    uri: Annotated[PageURI, BeforeValidator(PageURI.parse)] = Field(
        description="Structured URI for the referenced page"
    )
    score: float = Field(description="Score of the document", default=0.0)
    explanation: str = Field(description="Explanation of the document", default="")
    _page: Optional[Page] = PrivateAttr(default=None)

    @property
    def page(self) -> Page:
        if self._page is None:
            raise KeyError(f"No page associated with reference: {self.uri}")
        return self._page

    @page.setter
    def page(self, page: Page) -> None:
        self._page = page


class SearchRequest(BaseModel):
    instruction: str = Field(description="Search instruction")


class SearchResponse(BaseModel):
    results: List[PageReference] = Field(description="Search results")
