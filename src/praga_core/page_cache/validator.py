"""Page validation logic."""

import logging
from typing import Awaitable, Callable, Dict, Type, TypeVar

from ..types import Page

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)

ValidatorFn = Callable[[P], Awaitable[bool]]

__all__ = ["PageValidator", "ValidatorFn"]


class PageValidator:
    """Handles page validation using registered async validator functions."""

    def __init__(self) -> None:
        self._validators: Dict[str, ValidatorFn] = {}

    def register(self, page_type: Type[P], validator: ValidatorFn) -> None:
        """Register an async validator function for a page type.

        The validator function should return True if the page is valid,
        False if it should be considered invalid.
        
        All validators must be async:
        - async def validator(page: MyPage) -> bool: ...
        """
        type_name = page_type.__name__

        def type_safe_validator(page: Page) -> Awaitable[bool]:
            """Wrapper that ensures type safety."""
            if not isinstance(page, page_type):
                # If page is not the expected type, consider it valid
                # (another validator will handle it)
                async def return_true() -> bool:
                    return True
                return return_true()
            return validator(page)

        self._validators[type_name] = type_safe_validator
        logger.debug(f"Registered async validator for page type: {type_name}")

    async def is_valid(self, page: Page) -> bool:
        """Check if a page is valid according to its registered async validator.

        If no validator is registered for the page type, the page is
        considered valid by default.
        """
        type_name = page.__class__.__name__

        if type_name in self._validators:
            validator = self._validators[type_name]
            try:
                is_valid = await validator(page)
                    
                if not is_valid:
                    logger.debug(f"Page failed validation: {page.uri}")
                return is_valid
            except Exception as e:
                logger.warning(f"Validator error for {page.uri}: {e}")
                # If validator fails, treat as invalid
                return False

        # No validator registered - consider valid by default
        return True

    def has_validator(self, page_type: Type[Page]) -> bool:
        """Check if a validator is registered for a page type."""
        return page_type.__name__ in self._validators

    def clear(self) -> None:
        """Clear all registered validators."""
        self._validators.clear()
        logger.debug("Cleared all page validators")
