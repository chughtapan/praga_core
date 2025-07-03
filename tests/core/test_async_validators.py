"""Tests for async validator functionality."""

import asyncio
from typing import Any

import pytest

from praga_core.page_cache.validator import PageValidator
from praga_core.types import Page, PageURI


class TestValidatorPage(Page):
    """Test page for validator testing."""
    
    title: str
    status: str
    
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class AnotherTestPage(Page):
    """Another test page type."""
    
    name: str
    
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


@pytest.fixture
def validator() -> PageValidator:
    """Provide a fresh PageValidator for each test."""
    return PageValidator()


class TestAsyncPageValidator:
    """Test async validator functionality."""

    @pytest.mark.asyncio
    async def test_async_validator_registration_and_execution(self, validator: PageValidator) -> None:
        """Test registering and executing async validators."""
        validation_calls = []
        
        async def async_validator(page: TestValidatorPage) -> bool:
            await asyncio.sleep(0.01)  # Simulate async validation
            validation_calls.append(page.title)
            return page.status == "valid"

        validator.register(TestValidatorPage, async_validator)
        
        # Test valid page
        valid_page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Valid Page",
            status="valid"
        )
        
        result = await validator.is_valid_async(valid_page)
        assert result is True
        assert "Valid Page" in validation_calls
        
        # Test invalid page
        invalid_page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page2", version=1),
            title="Invalid Page",
            status="invalid"
        )
        
        result = await validator.is_valid_async(invalid_page)
        assert result is False
        assert "Invalid Page" in validation_calls

    @pytest.mark.asyncio
    async def test_sync_validator_in_async_context(self, validator: PageValidator) -> None:
        """Test that sync validators work in async context."""
        validation_calls = []
        
        def sync_validator(page: TestValidatorPage) -> bool:
            validation_calls.append(page.title)
            return page.status == "valid"

        validator.register(TestValidatorPage, sync_validator)
        
        valid_page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Valid Page",
            status="valid"
        )
        
        result = await validator.is_valid_async(valid_page)
        assert result is True
        assert "Valid Page" in validation_calls

    def test_async_validator_in_sync_context_warning(self, validator: PageValidator) -> None:
        """Test that async validators called in sync context produce warnings."""
        async def async_validator(page: TestValidatorPage) -> bool:
            await asyncio.sleep(0.01)
            return page.status == "valid"

        validator.register(TestValidatorPage, async_validator)
        
        page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Test Page",
            status="valid"
        )
        
        # Should return False and log warning when async validator called in sync context
        result = validator.is_valid(page)
        assert result is False

    def test_sync_validator_in_sync_context(self, validator: PageValidator) -> None:
        """Test that sync validators work normally in sync context."""
        validation_calls = []
        
        def sync_validator(page: TestValidatorPage) -> bool:
            validation_calls.append(page.title)
            return page.status == "valid"

        validator.register(TestValidatorPage, sync_validator)
        
        valid_page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Valid Page",
            status="valid"
        )
        
        result = validator.is_valid(valid_page)
        assert result is True
        assert "Valid Page" in validation_calls

    @pytest.mark.asyncio
    async def test_type_safety_async(self, validator: PageValidator) -> None:
        """Test that validators only apply to correct page types in async context."""
        async def test_validator(page: TestValidatorPage) -> bool:
            await asyncio.sleep(0.01)
            return page.status == "valid"

        validator.register(TestValidatorPage, test_validator)
        
        # Wrong page type should be considered valid (not handled by this validator)
        wrong_page = AnotherTestPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            name="Test"
        )
        
        result = await validator.is_valid_async(wrong_page)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_validator_registered_async(self, validator: PageValidator) -> None:
        """Test that pages with no registered validator are considered valid in async context."""
        page = AnotherTestPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            name="Test"
        )
        
        result = await validator.is_valid_async(page)
        assert result is True

    @pytest.mark.asyncio
    async def test_async_validator_exception_handling(self, validator: PageValidator) -> None:
        """Test that exceptions in async validators are handled properly."""
        async def failing_validator(page: TestValidatorPage) -> bool:
            await asyncio.sleep(0.01)
            raise ValueError("Validator error")

        validator.register(TestValidatorPage, failing_validator)
        
        page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Test Page",
            status="valid"
        )
        
        # Should return False when validator raises exception
        result = await validator.is_valid_async(page)
        assert result is False

    def test_sync_validator_exception_handling(self, validator: PageValidator) -> None:
        """Test that exceptions in sync validators are handled properly."""
        def failing_validator(page: TestValidatorPage) -> bool:
            raise RuntimeError("Sync validator error")

        validator.register(TestValidatorPage, failing_validator)
        
        page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Test Page",
            status="valid"
        )
        
        # Should return False when validator raises exception
        result = validator.is_valid(page)
        assert result is False

    @pytest.mark.asyncio
    async def test_multiple_validators_async(self, validator: PageValidator) -> None:
        """Test behavior with multiple validators for same type (last one wins)."""
        async def first_validator(page: TestValidatorPage) -> bool:
            await asyncio.sleep(0.01)
            return True  # Always valid

        async def second_validator(page: TestValidatorPage) -> bool:
            await asyncio.sleep(0.01)
            return page.status == "valid"

        # Register both validators - second should overwrite first
        validator.register(TestValidatorPage, first_validator)
        validator.register(TestValidatorPage, second_validator)
        
        invalid_page = TestValidatorPage(
            uri=PageURI(root="test", type="test", id="page1", version=1),
            title="Invalid Page",
            status="invalid"
        )
        
        # Should use second validator which checks status
        result = await validator.is_valid_async(invalid_page)
        assert result is False

    def test_has_validator_method(self, validator: PageValidator) -> None:
        """Test the has_validator method."""
        assert not validator.has_validator(TestValidatorPage)
        
        def test_validator(page: TestValidatorPage) -> bool:
            return True

        validator.register(TestValidatorPage, test_validator)
        assert validator.has_validator(TestValidatorPage)
        assert not validator.has_validator(AnotherTestPage)

    def test_clear_validators(self, validator: PageValidator) -> None:
        """Test clearing all validators."""
        def test_validator(page: TestValidatorPage) -> bool:
            return True

        validator.register(TestValidatorPage, test_validator)
        assert validator.has_validator(TestValidatorPage)
        
        validator.clear()
        assert not validator.has_validator(TestValidatorPage)