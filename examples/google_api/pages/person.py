"""Person page definition."""

from typing import Optional

from pydantic import Field

from praga_core.types import Page


class PersonPage(Page):
    """A page representing a person with their basic information."""

    first_name: str = Field(description="Person's first name")
    last_name: str = Field(description="Person's last name")
    email: str = Field(description="Person's email address")
    full_name: Optional[str] = Field(None, description="Person's full name (computed)")

    def __init__(self, **data):
        super().__init__(**data)
        # Compute full_name if not provided
        if self.full_name is None:
            self.full_name = f"{self.first_name} {self.last_name}".strip()
