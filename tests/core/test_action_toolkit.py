"""Tests for ActionToolkit functionality."""

from typing import Any, Dict, List

from praga_core.agents.toolkit import ActionToolkit, action_tool
from praga_core.types import Page, PageURI


class EmailPage(Page):
    """Mock email page for testing."""
    
    sender: str
    subject: str
    read: bool = False

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class CalendarEventPage(Page):
    """Mock calendar event page for testing."""
    
    title: str
    start_time: str
    attendees: List[str] = []

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class MockActionToolkit(ActionToolkit):
    """Mock ActionToolkit for testing purposes."""

    def __init__(self) -> None:
        super().__init__()

    @property
    def name(self) -> str:
        return "MockActionToolkit"


class TestActionToolkitCore:
    """Test core ActionToolkit functionality."""

    def test_toolkit_initialization(self) -> None:
        """Test basic toolkit initialization."""
        toolkit = MockActionToolkit()

        assert toolkit is not None
        assert hasattr(toolkit, "action_tools")
        assert hasattr(toolkit, "_action_tools")
        assert len(toolkit.action_tools) == 0

    def test_action_tool_registration_with_method(self) -> None:
        """Test registering a method as an action tool."""
        toolkit = MockActionToolkit()

        def mark_email_read(email: EmailPage) -> bool:
            email.read = True
            return True

        toolkit.register_action_tool(mark_email_read, "mark_email_read")

        assert "mark_email_read" in toolkit.action_tools
        assert hasattr(toolkit, "mark_email_read")

    def test_action_tool_registration_with_function_no_name(self) -> None:
        """Test registering a standalone function as an action tool without a name."""

        def forward_email(email: EmailPage, recipient: str) -> bool:
            return True

        toolkit = MockActionToolkit()
        toolkit.register_action_tool(forward_email)

        assert "forward_email" in toolkit.action_tools
        action_tool = toolkit.get_action_tool("forward_email")
        assert action_tool.name == "forward_email"

    def test_get_action_tool_success(self) -> None:
        """Test successful action tool retrieval."""
        toolkit = MockActionToolkit()

        def cancel_event(event: CalendarEventPage) -> bool:
            return True

        toolkit.register_action_tool(cancel_event, "cancel_event")

        action_tool = toolkit.get_action_tool("cancel_event")
        assert action_tool.name == "cancel_event"

    def test_get_action_tool_not_found(self) -> None:
        """Test action tool retrieval when tool doesn't exist."""
        toolkit = MockActionToolkit()

        try:
            toolkit.get_action_tool("nonexistent_tool")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Action tool 'nonexistent_tool' not found" in str(e)

    def test_action_tools_property(self) -> None:
        """Test the action_tools property returns correct tool mapping."""
        toolkit = MockActionToolkit()

        def delete_email(email: EmailPage) -> bool:
            return True

        def reschedule_event(event: CalendarEventPage, new_time: str) -> bool:
            return True

        toolkit.register_action_tool(delete_email, "delete_email")
        toolkit.register_action_tool(reschedule_event, "reschedule_event")

        tools = toolkit.action_tools
        assert len(tools) == 2
        assert "delete_email" in tools
        assert "reschedule_event" in tools

    def test_invoke_action_tool_basic(self) -> None:
        """Test basic action tool invocation through invoke_action_tool method."""
        toolkit = MockActionToolkit()

        def mark_important(email: EmailPage) -> bool:
            return True

        toolkit.register_action_tool(mark_important, "mark_important")

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        result = toolkit.invoke_action_tool("mark_important", {"email": email})
        assert result["success"] is True

    def test_invoke_action_tool_with_additional_args(self) -> None:
        """Test action tool invocation with additional arguments."""
        toolkit = MockActionToolkit()

        def forward_email(email: EmailPage, recipient: str, add_note: str = "") -> bool:
            return len(recipient) > 0

        toolkit.register_action_tool(forward_email, "forward_email")

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        result = toolkit.invoke_action_tool("forward_email", {
            "email": email,
            "recipient": "forward@example.com",
            "add_note": "FYI"
        })
        assert result["success"] is True

    def test_invoke_action_tool_failure(self) -> None:
        """Test action tool invocation when action fails."""
        toolkit = MockActionToolkit()

        def unreliable_action(email: EmailPage) -> bool:
            return False

        toolkit.register_action_tool(unreliable_action, "unreliable_action")

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        result = toolkit.invoke_action_tool("unreliable_action", {"email": email})
        assert result["success"] is False

    def test_invoke_action_tool_not_found(self) -> None:
        """Test invoking a non-existent action tool raises appropriate error."""
        toolkit = MockActionToolkit()

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        try:
            toolkit.invoke_action_tool("nonexistent_tool", {"email": email})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Action tool 'nonexistent_tool' not found" in str(e)

    def test_direct_method_access(self) -> None:
        """Test that registered action tools are accessible as toolkit methods."""
        toolkit = MockActionToolkit()

        def archive_email(email: EmailPage) -> bool:
            return True

        toolkit.register_action_tool(archive_email, "archive_email")

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        # Should be able to call the method directly
        result = toolkit.archive_email(email)
        assert result is True


class TestActionToolDecorator:
    """Test the @action_tool decorator functionality."""

    def test_action_tool_decorator_basic(self) -> None:
        """Test basic @action_tool decorator functionality."""

        class TestActionToolkit(ActionToolkit):
            def __init__(self):
                super().__init__()

            @property
            def name(self) -> str:
                return "TestActionToolkit"

            @action_tool()
            def mark_read(self, email: EmailPage) -> bool:
                """Mark an email as read"""
                email.read = True
                return True

        toolkit = TestActionToolkit()
        assert "mark_read" in toolkit.action_tools
        assert hasattr(toolkit, "mark_read")

    def test_action_tool_decorator_with_custom_name(self) -> None:
        """Test @action_tool decorator with custom name."""

        class TestActionToolkit(ActionToolkit):
            def __init__(self):
                super().__init__()

            @property
            def name(self) -> str:
                return "TestActionToolkit"

            @action_tool(name="custom_archive")
            def archive_email(self, email: EmailPage) -> bool:
                """Archive an email"""
                return True

        toolkit = TestActionToolkit()
        assert "custom_archive" in toolkit.action_tools
        assert "archive_email" not in toolkit.action_tools

    def test_action_tool_decorator_with_manual_registration(self) -> None:
        """Test that @action_tool decorator can coexist with manual tool registration."""

        class TestActionToolkit(ActionToolkit):
            def __init__(self):
                super().__init__()
                # Manually register an action tool
                self.register_action_tool(self.manual_action, "manual_action")

            @property
            def name(self) -> str:
                return "TestActionToolkit"

            @action_tool()
            def decorated_action(self, email: EmailPage) -> bool:
                """Decorated action tool"""
                return True

            def manual_action(self, email: EmailPage) -> bool:
                """Manually registered action tool"""
                return True

        toolkit = TestActionToolkit()

        # Both action tools should be available
        assert len(toolkit.action_tools) == 2
        assert "decorated_action" in toolkit.action_tools
        assert "manual_action" in toolkit.action_tools

        # Both should work
        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        decorated_result = toolkit.decorated_action(email)
        manual_result = toolkit.manual_action(email)

        assert decorated_result is True
        assert manual_result is True


class TestActionToolValidation:
    """Test action tool validation logic."""

    def test_invalid_return_type_registration(self) -> None:
        """Test that action tools with invalid return types are rejected during registration."""

        class BadActionToolkit(ActionToolkit):
            @property
            def name(self) -> str:
                return "BadActionToolkit"

        toolkit = BadActionToolkit()

        # This should fail because it doesn't return bool
        def bad_action_wrong_return(email: EmailPage) -> str:
            return "success"

        try:
            toolkit.register_action_tool(bad_action_wrong_return, "bad_action")
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "must have a Page (or subclass) as the first parameter and return a boolean" in str(e)

    def test_invalid_first_parameter_registration(self) -> None:
        """Test that action tools without Page as first parameter are rejected."""

        class BadActionToolkit(ActionToolkit):
            @property
            def name(self) -> str:
                return "BadActionToolkit"

        toolkit = BadActionToolkit()

        # This should fail because first parameter is not Page
        def bad_action_wrong_param(text: str) -> bool:
            return True

        try:
            toolkit.register_action_tool(bad_action_wrong_param, "bad_action")
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "must have a Page (or subclass) as the first parameter and return a boolean" in str(e)

    def test_valid_action_tool_subclass_page(self) -> None:
        """Test that action tools with Page subclasses work correctly."""
        toolkit = MockActionToolkit()

        def process_calendar_event(event: CalendarEventPage) -> bool:
            return len(event.attendees) > 0

        # This should work since CalendarEventPage is a subclass of Page
        toolkit.register_action_tool(process_calendar_event, "process_calendar_event")
        assert "process_calendar_event" in toolkit.action_tools


class TestActionToolExamples:
    """Test example action tools mentioned in the issue."""

    def test_mark_email_as_read_example(self) -> None:
        """Test the 'mark email as read' example."""
        toolkit = MockActionToolkit()

        def mark_email_as_read(email: EmailPage) -> bool:
            """Mark an email as read."""
            email.read = True
            return True

        toolkit.register_action_tool(mark_email_as_read, "mark_email_as_read")

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="sender@example.com",
            subject="Important Email",
            read=False
        )

        result = toolkit.invoke_action_tool("mark_email_as_read", {"email": email})
        assert result["success"] is True
        assert email.read is True

    def test_forward_email_example(self) -> None:
        """Test the 'forward email to person' example."""
        toolkit = MockActionToolkit()

        def forward_email_to_person(email: EmailPage, recipient: str) -> bool:
            """Forward an email to a specific person."""
            return "@" in recipient  # Simple validation

        toolkit.register_action_tool(forward_email_to_person, "forward_email_to_person")

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="sender@example.com",
            subject="Forward this"
        )

        # Test successful forward
        result = toolkit.invoke_action_tool("forward_email_to_person", {
            "email": email,
            "recipient": "recipient@example.com"
        })
        assert result["success"] is True

        # Test failed forward (invalid recipient)
        result = toolkit.invoke_action_tool("forward_email_to_person", {
            "email": email,
            "recipient": "invalid_email"
        })
        assert result["success"] is False

    def test_change_calendar_event_time_example(self) -> None:
        """Test the 'change calendar event to another time' example."""
        toolkit = MockActionToolkit()

        def change_calendar_event_time(event: CalendarEventPage, new_time: str) -> bool:
            """Change a calendar event to another time."""
            if len(new_time) > 0:
                event.start_time = new_time
                return True
            return False

        toolkit.register_action_tool(change_calendar_event_time, "change_calendar_event_time")

        event = CalendarEventPage(
            uri=PageURI.parse("test/CalendarEventPage:event1@1"),
            title="Team Meeting",
            start_time="2024-01-01T10:00:00",
            attendees=["alice@example.com", "bob@example.com"]
        )

        # Test successful time change
        result = toolkit.invoke_action_tool("change_calendar_event_time", {
            "event": event,
            "new_time": "2024-01-01T14:00:00"
        })
        assert result["success"] is True
        assert event.start_time == "2024-01-01T14:00:00"

        # Test failed time change (empty time)
        result = toolkit.invoke_action_tool("change_calendar_event_time", {
            "event": event,
            "new_time": ""
        })
        assert result["success"] is False