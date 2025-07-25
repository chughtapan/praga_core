"""Provider-agnostic people page definitions."""

from typing import Any, Optional

from pydantic import Field

from praga_core.types import Page


class PersonPage(Page):
    """A page representing a person with their basic information."""

    # Provider-specific metadata (stored as internal fields)
    source: Optional[str] = Field(
        None,
        exclude=True,
        description="Source of person information (people_api, directory_api, emails, etc.)",
    )

    # Core person fields (provider-agnostic)
    first_name: str = Field(description="Person's first name")
    last_name: str = Field(description="Person's last name")
    email: str = Field(description="Person's primary email address")

    # Computed field for full name
    full_name: Optional[str] = Field(None, description="Person's full name (computed)")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        # Compute full_name if not provided
        if self.full_name is None:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
