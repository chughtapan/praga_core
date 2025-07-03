"""Page validation logic."""

import asyncio
import logging
from typing import Awaitable, Callable, Dict, Type, TypeVar, Union

from ..types import Page

logger = logging.getLogger(__name__)

P = TypeVar("P", bound=Page)

ValidatorFn = Callable[[P], bool]
AsyncValidatorFn = Callable[[P], Awaitable[bool]]
AnyValidatorFn = Union[ValidatorFn, AsyncValidatorFn]

__all__ = ["PageValidator", "ValidatorFn", "AsyncValidatorFn", "AnyValidatorFn"]


class PageValidator:
    """Handles page validation using registered validator functions."""

    def __init__(self) -> None:
        self._validators: Dict[str, AnyValidatorFn] = {}

    def register(self, page_type: Type[P], validator: AnyValidatorFn) -> None:
        """Register a validator function for a page type.

        The validator function should return True if the page is valid,
        False if it should be considered invalid.
        
        Supports both sync and async validators:
        - def validator(page: MyPage) -> bool: ...
        - async def validator(page: MyPage) -> bool: ...
        """
        type_name = page_type.__name__

        def type_safe_validator(page: Page) -> Union[bool, Awaitable[bool]]:
            """Wrapper that ensures type safety."""
            if not isinstance(page, page_type):
                # If page is not the expected type, consider it valid
                # (another validator will handle it)
                return True
            return validator(page)

        self._validators[type_name] = type_safe_validator
        logger.debug(f"Registered validator for page type: {type_name}")

    def is_valid(self, page: Page) -> bool:
        """Check if a page is valid according to its registered validator.

        If no validator is registered for the page type, the page is
        considered valid by default.
        """
        type_name = page.__class__.__name__

        if type_name in self._validators:
            validator = self._validators[type_name]
            try:
                result = validator(page)
                # If result is a coroutine, we can't await it in sync context
                if asyncio.iscoroutine(result):
                    logger.warning(
                        f"Async validator called in sync context for {page.uri}. "
                        f"Use is_valid_async() instead."
                    )
                    # Clean up the coroutine to avoid warnings
                    result.close()
                    return False
                
                is_valid = bool(result)
                if not is_valid:
                    logger.debug(f"Page failed validation: {page.uri}")
                return is_valid
            except Exception as e:
                logger.warning(f"Validator error for {page.uri}: {e}")
                # If validator fails, treat as invalid
                return False

        # No validator registered - consider valid by default
        return True

    async def is_valid_async(self, page: Page) -> bool:
        """Async version of is_valid that can handle both sync and async validators."""
        type_name = page.__class__.__name__

        if type_name in self._validators:
            validator = self._validators[type_name]
            try:
                result = validator(page)
                
                # Handle both sync and async validators
                if asyncio.iscoroutine(result):
                    is_valid = await result
                else:
                    is_valid = bool(result)
                    
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
