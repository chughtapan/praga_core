"""Person page definition."""

from typing import Any, Optional
from enum import Enum

from pydantic import Field

from praga_core.types import Page


class SourceType(Enum):
    """Enumeration of different sources for person information."""
    PEOPLE_API = "people_api"  # Explicit source
    DIRECTORY_API = "directory_api"  # Explicit source  
    EMAILS = "emails"  # Implicit source


class PersonPage(Page):
    """A page representing a person with their basic information."""

    first_name: str = Field(description="Person's first name")
    last_name: str = Field(description="Person's last name")
    email: str = Field(description="Person's email address")
    full_name: Optional[str] = Field(None, description="Person's full name (computed)")
    source_enum: Optional[SourceType] = Field(None, exclude=True, description="Source of person information")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Compute full_name if not provided
        if self.full_name is None:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
