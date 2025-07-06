"""Tests for ActionExecutor functionality with ServerContext integration."""

from typing import List, Optional, Union

import pytest

from praga_core.action_executor import ActionExecutorMixin
from praga_core.context import ServerContext
from praga_core.types import Page, PageURI


class EmailPage(Page):
    """Mock email page for testing."""

    sender: str
    subject: str
    read: bool = False


class CalendarEventPage(Page):
    """Mock calendar event page for testing."""

    title: str
    start_time: str
    attendees: List[str] = []


@pytest.fixture
async def context() -> ServerContext:
    return await ServerContext.create()


class TestActionExecutorCore:
    """Test core ActionExecutor functionality."""

    def test_context_initialization(self, context: ServerContext) -> None:
        """Test basic ServerContext initialization with ActionExecutor."""

        assert context is not None
        assert hasattr(context, "actions")
        assert len(context.actions) == 0

    def test_action_registration_with_decorator(self, context: ServerContext) -> None:
        """Test registering an action with @action decorator."""

        @context.action()
        async def mark_email_read(email: EmailPage) -> bool:
            email.read = True
            return True

        assert "mark_email_read" in context.actions

    def test_action_registration_directly(self, context: ServerContext) -> None:
        """Test registering a standalone function as an action."""

        def forward_email(email: EmailPage, recipient: str) -> bool:
            return True

        context.register_action("forward_email", forward_email)

        assert "forward_email" in context.actions

    def test_get_action_success(self, context: ServerContext) -> None:
        """Test successful action retrieval."""

        def cancel_event(event: CalendarEventPage) -> bool:
            return True

        context.register_action("cancel_event", cancel_event)

        action_func = context.get_action("cancel_event")
        # get_action now returns a wrapper function, not the original
        assert action_func != cancel_event
        assert callable(action_func)

    def test_get_action_not_found(self, context: ServerContext) -> None:
        """Test action retrieval when action doesn't exist."""

        try:
            context.get_action("nonexistent_action")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Action 'nonexistent_action' not found" in str(e)

    def test_actions_property(self, context: ServerContext) -> None:
        """Test the actions property returns correct action mapping."""

        def delete_email(email: EmailPage) -> bool:
            return True

        def reschedule_event(event: CalendarEventPage, new_time: str) -> bool:
            return True

        context.register_action("delete_email", delete_email)
        context.register_action("reschedule_event", reschedule_event)

        actions = context.actions
        assert len(actions) == 2
        assert "delete_email" in actions
        assert "reschedule_event" in actions

    @pytest.mark.asyncio
    async def test_invoke_action_basic(self, context: ServerContext) -> None:
        """Test basic action invocation with PageURIs."""

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email",
        )

        @context.route("EmailPage")
        async def get_email(uri: PageURI) -> EmailPage:
            return email

        @context.action()
        def mark_important(email: EmailPage) -> bool:
            return True

        result = await context.invoke_action("mark_important", {"email": email.uri})
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invoke_action_with_additional_args(
        self, context: ServerContext
    ) -> None:
        """Test action invocation with additional arguments."""

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email",
        )

        @context.route("EmailPage")
        async def get_email(uri: PageURI) -> EmailPage:
            return email

        @context.action()
        def forward_email(email: EmailPage, recipient: str, add_note: str = "") -> bool:
            return len(recipient) > 0

        result = await context.invoke_action(
            "forward_email",
            {"email": email.uri, "recipient": "forward@example.com", "add_note": "FYI"},
        )
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invoke_action_failure(self, context: ServerContext) -> None:
        """Test action invocation when action fails."""

        @context.action()
        def unreliable_action(email: EmailPage) -> bool:
            return False

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email",
        )

        result = await context.invoke_action("unreliable_action", {"email": email})
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_invoke_action_not_found(self, context: ServerContext) -> None:
        """Test invoking a non-existent action raises appropriate error."""

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email",
        )

        try:
            await context.invoke_action("nonexistent_action", {"email": email})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Action 'nonexistent_action' not found" in str(e)


class TestActionDecorator:
    """Test the @action decorator functionality."""

    def test_action_decorator_basic(self, context: ServerContext) -> None:
        """Test basic @action decorator functionality."""

        @context.action()
        async def mark_read(email: EmailPage) -> bool:
            """Mark an email as read"""
            email.read = True
            return True

        assert "mark_read" in context.actions

    def test_action_decorator_with_custom_name(self, context: ServerContext) -> None:
        """Test @action decorator with custom name."""

        @context.action(name="custom_archive")
        async def archive_email(email: EmailPage) -> bool:
            """Archive an email"""
            return True

        assert "custom_archive" in context.actions
        assert "archive_email" not in context.actions

    def test_standalone_action_decorator(self, context: ServerContext) -> None:
        """Test standalone action registration."""

        async def standalone_delete(email: EmailPage) -> bool:
            """Delete an email"""
            return True

        # Register with context
        context.register_action("standalone_delete", standalone_delete)
        assert "standalone_delete" in context.actions


class TestActionValidation:
    """Test action validation logic."""

    def test_invalid_return_type_registration(self, context: ServerContext) -> None:
        """Test that actions with invalid return types are rejected during registration."""

        # This should fail because it doesn't return Awaitable[bool]
        async def bad_action_wrong_return(email: EmailPage) -> str:
            return "success"

        try:
            context.register_action("bad_action", bad_action_wrong_return)
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert (
                "must have a Page (or subclass) as the first parameter and return an awaitable boolean"
                in str(e)
            )

    def test_invalid_first_parameter_registration(self, context: ServerContext) -> None:
        """Test that actions without Page as first parameter are rejected."""

        # This should fail because first parameter is not Page
        async def bad_action_wrong_param(text: str) -> bool:
            return True

        try:
            context.register_action("bad_action", bad_action_wrong_param)
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert (
                "must have a Page (or subclass) as the first parameter and return an awaitable boolean"
                in str(e)
            )

    def test_valid_action_subclass_page(self, context: ServerContext) -> None:
        """Test that actions with Page subclasses work correctly."""

        async def process_calendar_event(event: CalendarEventPage) -> bool:
            return len(event.attendees) > 0

        # This should work since CalendarEventPage is a subclass of Page
        context.register_action("process_calendar_event", process_calendar_event)
        assert "process_calendar_event" in context.actions

    def test_invalid_action_no_parameters(self, context: ServerContext) -> None:
        """Test that actions with no parameters are rejected."""

        async def bad_action_no_params() -> bool:
            return True

        try:
            context.register_action("bad_action", bad_action_no_params)
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert (
                "must have a Page (or subclass) as the first parameter and return an awaitable boolean"
                in str(e)
            )

    @pytest.mark.asyncio
    async def test_page_object_passed_to_action_wrapper(
        self, context: ServerContext
    ) -> None:
        """Test that passing Page objects to action wrapper raises helpful error."""
        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email",
        )

        @context.action()
        async def test_action(email: EmailPage) -> bool:
            return True

        # This should fail when trying to pass a Page object instead of PageURI
        result = await context.invoke_action("test_action", {"email": email})
        assert result["success"] is False
        assert "error" in result
        assert (
            "received a Page object, but action wrapper expects PageURI"
            in result["error"]
        )
        assert "Pass the page's URI instead" in result["error"]


class TestPageURIConversion:
    """Test PageURI conversion functionality."""

    async def test_invoke_action_with_pageuri(self, context: ServerContext) -> None:
        """Test action invocation with PageURI that gets converted to Page."""

        # Set up page handler
        @context.route("emails")
        async def get_email(uri: PageURI) -> EmailPage:
            return EmailPage(
                uri=uri,
                sender="test@example.com",
                subject=uri.id.replace("_", " "),
                read=False,
            )

        @context.action()
        async def mark_email_read(email: EmailPage) -> bool:
            email.read = True
            return True

        # Create PageURI and invoke action
        email_uri = PageURI.parse("test/emails:email1@1")
        result = await context.invoke_action("mark_email_read", {"email": email_uri})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_invoke_action_with_pageuri_string(
        self, context: ServerContext
    ) -> None:
        """Test action invocation with PageURI string."""

        @context.route("emails")
        async def get_email(uri: PageURI) -> EmailPage:
            return EmailPage(
                uri=uri,
                sender="test@example.com",
                subject=uri.id.replace("_", " "),
                read=False,
            )

        @context.action()
        def archive_email(email: EmailPage) -> bool:
            return True

        # Use string representation of PageURI
        result = await context.invoke_action(
            "archive_email", {"email": "/emails:test_email@1"}
        )
        assert result["success"] is True


class TestActionExamples:
    """Test example actions mentioned in the issue."""

    @pytest.mark.asyncio
    async def test_mark_email_as_read_example(self, context: ServerContext) -> None:
        """Test the 'mark email as read' example."""

        # Store email for page handler
        stored_email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="sender@example.com",
            subject="Important Email",
            read=False,
        )

        @context.route("EmailPage")
        async def get_email(uri: PageURI) -> EmailPage:
            return stored_email

        @context.action()
        def mark_email_as_read(email: EmailPage) -> bool:
            """Mark an email as read."""
            email.read = True
            return True

        result = await context.invoke_action(
            "mark_email_as_read", {"email": stored_email.uri}
        )
        assert result["success"] is True
        assert stored_email.read is True

    @pytest.mark.asyncio
    async def test_forward_email_example(self, context: ServerContext) -> None:
        """Test the 'forward email to person' example."""

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="sender@example.com",
            subject="Forward this",
        )

        @context.route("EmailPage")
        async def get_email(uri: PageURI) -> EmailPage:
            return email

        @context.action()
        def forward_email_to_person(email: EmailPage, recipient: str) -> bool:
            """Forward an email to a specific person."""
            return "@" in recipient  # Simple validation

        # Test successful forward
        result = await context.invoke_action(
            "forward_email_to_person",
            {"email": email.uri, "recipient": "recipient@example.com"},
        )
        assert result["success"] is True

        # Test failed forward (invalid recipient)
        result = await context.invoke_action(
            "forward_email_to_person",
            {"email": email.uri, "recipient": "invalid_email"},
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_change_calendar_event_time_example(
        self, context: ServerContext
    ) -> None:
        """Test the 'change calendar event to another time' example."""

        # Store event for page handler
        stored_event = CalendarEventPage(
            uri=PageURI.parse("test/CalendarEventPage:event1@1"),
            title="Team Meeting",
            start_time="2024-01-01T10:00:00",
            attendees=["alice@example.com", "bob@example.com"],
        )

        @context.route("CalendarEventPage")
        async def get_event(uri: PageURI) -> CalendarEventPage:
            return stored_event

        @context.action()
        def change_calendar_event_time(event: CalendarEventPage, new_time: str) -> bool:
            """Change a calendar event to another time."""
            if len(new_time) > 0:
                event.start_time = new_time
                return True
            return False

        # Test successful time change
        result = await context.invoke_action(
            "change_calendar_event_time",
            {"event": stored_event.uri, "new_time": "2024-01-01T14:00:00"},
        )
        assert result["success"] is True
        assert stored_event.start_time == "2024-01-01T14:00:00"

        # Test failed time change (empty time)
        result = await context.invoke_action(
            "change_calendar_event_time", {"event": stored_event.uri, "new_time": ""}
        )
        assert result["success"] is False


class TestActionExecutorMixinHelpers:
    """Test helper methods in ActionExecutorMixin."""

    @pytest.fixture
    def mock_executor(self) -> ActionExecutorMixin:
        """Create a mock executor for testing helper methods."""

        class MockExecutor(ActionExecutorMixin):
            async def get_pages(self, page_uris: List[PageURI]) -> List[Page]:
                return []

        return MockExecutor()

    def test_is_page_type_with_page_class(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _is_page_type with Page class."""
        assert mock_executor._is_page_type(Page) is True

    def test_is_page_type_with_page_subclass(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _is_page_type with Page subclass."""
        assert mock_executor._is_page_type(EmailPage) is True
        assert mock_executor._is_page_type(CalendarEventPage) is True

    def test_is_page_type_with_non_page_type(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _is_page_type with non-Page types."""
        assert mock_executor._is_page_type(str) is False
        assert mock_executor._is_page_type(int) is False
        assert mock_executor._is_page_type(bool) is False

    def test_is_optional_page_type_with_optional_page(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _is_optional_page_type with Optional[Page]."""
        assert mock_executor._is_optional_page_type(Optional[Page]) is True
        assert mock_executor._is_optional_page_type(Union[Page, None]) is True

    def test_is_optional_page_type_with_optional_page_subclass(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _is_optional_page_type with Optional[PageSubclass]."""
        assert mock_executor._is_optional_page_type(Optional[EmailPage]) is True
        assert (
            mock_executor._is_optional_page_type(Union[CalendarEventPage, None]) is True
        )

    def test_is_optional_page_type_with_non_optional_types(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _is_optional_page_type with non-optional types."""
        assert mock_executor._is_optional_page_type(Page) is False
        assert mock_executor._is_optional_page_type(str) is False
        assert mock_executor._is_optional_page_type(Optional[str]) is False
        assert mock_executor._is_optional_page_type(Union[str, int]) is False

    def test_convert_page_type_to_uri_type_with_page(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _convert_page_type_to_uri_type with Page."""
        result = mock_executor._convert_page_type_to_uri_type(Page)
        assert result == PageURI

    def test_convert_page_type_to_uri_type_with_page_subclass(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _convert_page_type_to_uri_type with Page subclass."""
        result = mock_executor._convert_page_type_to_uri_type(EmailPage)
        assert result == PageURI

    def test_convert_page_type_to_uri_type_with_list_page(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _convert_page_type_to_uri_type with List[Page]."""
        result = mock_executor._convert_page_type_to_uri_type(List[Page])
        assert result == List[PageURI]

        result = mock_executor._convert_page_type_to_uri_type(List[EmailPage])
        assert result == List[PageURI]

    def test_convert_page_type_to_uri_type_with_optional_page(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _convert_page_type_to_uri_type with Optional[Page]."""
        result = mock_executor._convert_page_type_to_uri_type(Optional[Page])
        assert result == Union[PageURI, None]

        result = mock_executor._convert_page_type_to_uri_type(Optional[EmailPage])
        assert result == Union[PageURI, None]

    def test_convert_page_type_to_uri_type_with_non_page_types(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _convert_page_type_to_uri_type with non-Page types."""
        assert mock_executor._convert_page_type_to_uri_type(str) == str
        assert mock_executor._convert_page_type_to_uri_type(int) == int
        assert mock_executor._convert_page_type_to_uri_type(bool) == bool
        assert mock_executor._convert_page_type_to_uri_type(List[str]) == List[str]
        assert (
            mock_executor._convert_page_type_to_uri_type(Optional[str]) == Optional[str]
        )

    def test_update_wrapper_annotations_with_page_parameters(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _update_wrapper_annotations with Page parameters."""

        def original_func(email: EmailPage, recipient: str) -> bool:
            return True

        def wrapper_func(**kwargs) -> bool:
            return True

        mock_executor._update_wrapper_annotations(wrapper_func, original_func)

        expected_annotations = {"email": PageURI, "recipient": str, "return": bool}
        assert wrapper_func.__annotations__ == expected_annotations

    def test_update_wrapper_annotations_with_complex_types(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _update_wrapper_annotations with complex Page types."""

        def original_func(
            pages: List[EmailPage],
            optional_page: Optional[CalendarEventPage],
            count: int,
        ) -> bool:
            return True

        def wrapper_func(**kwargs) -> bool:
            return True

        mock_executor._update_wrapper_annotations(wrapper_func, original_func)

        expected_annotations = {
            "pages": List[PageURI],
            "optional_page": Union[PageURI, None],
            "count": int,
            "return": bool,
        }
        assert wrapper_func.__annotations__ == expected_annotations

    def test_update_wrapper_annotations_no_annotations(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _update_wrapper_annotations with function that has no annotations."""

        def original_func():
            return True

        def wrapper_func():
            return True

        # Should raise an error when original function has no return type annotation
        try:
            mock_executor._update_wrapper_annotations(wrapper_func, original_func)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "must have a return type annotation" in str(e)

    def test_update_wrapper_annotations_missing_param_annotation(
        self, mock_executor: ActionExecutorMixin
    ) -> None:
        """Test _update_wrapper_annotations with function missing parameter annotation."""

        def original_func(email, recipient: str) -> bool:  # missing type for 'email'
            return True

        def wrapper_func():
            return True

        # Should raise an error when original function has missing parameter annotation
        try:
            mock_executor._update_wrapper_annotations(wrapper_func, original_func)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "parameter 'email' must have a type annotation" in str(e)
