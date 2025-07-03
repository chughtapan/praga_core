"""Tests for ActionExecutor functionality with ServerContext integration."""

from typing import Any, Dict, List

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


class TestActionExecutorCore:
    """Test core ActionExecutor functionality."""

    def test_context_initialization(self) -> None:
        """Test basic ServerContext initialization with ActionExecutor."""
        context = ServerContext()

        assert context is not None
        assert hasattr(context, "actions")
        assert len(context.actions) == 0

    def test_action_registration_with_decorator(self) -> None:
        """Test registering an action with @action decorator."""
        context = ServerContext()

        @context.action()
        def mark_email_read(email: EmailPage) -> bool:
            email.read = True
            return True

        assert "mark_email_read" in context.actions

    def test_action_registration_directly(self) -> None:
        """Test registering a standalone function as an action."""

        def forward_email(email: EmailPage, recipient: str) -> bool:
            return True

        context = ServerContext()
        context.register_action("forward_email", forward_email)

        assert "forward_email" in context.actions

    def test_get_action_success(self) -> None:
        """Test successful action retrieval."""
        context = ServerContext()

        def cancel_event(event: CalendarEventPage) -> bool:
            return True

        context.register_action("cancel_event", cancel_event)

        action_func = context._action_executor.get_action("cancel_event")
        assert action_func == cancel_event

    def test_get_action_not_found(self) -> None:
        """Test action retrieval when action doesn't exist."""
        context = ServerContext()

        try:
            context._action_executor.get_action("nonexistent_action")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Action 'nonexistent_action' not found" in str(e)

    def test_actions_property(self) -> None:
        """Test the actions property returns correct action mapping."""
        context = ServerContext()

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

    def test_invoke_action_basic(self) -> None:
        """Test basic action invocation with Page objects."""
        context = ServerContext()

        @context.action()
        def mark_important(email: EmailPage) -> bool:
            return True

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        result = context.invoke_action("mark_important", {"email": email})
        assert result["success"] is True

    def test_invoke_action_with_additional_args(self) -> None:
        """Test action invocation with additional arguments."""
        context = ServerContext()

        @context.action()
        def forward_email(email: EmailPage, recipient: str, add_note: str = "") -> bool:
            return len(recipient) > 0

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        result = context.invoke_action("forward_email", {
            "email": email,
            "recipient": "forward@example.com",
            "add_note": "FYI"
        })
        assert result["success"] is True

    def test_invoke_action_failure(self) -> None:
        """Test action invocation when action fails."""
        context = ServerContext()

        @context.action()
        def unreliable_action(email: EmailPage) -> bool:
            return False

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        result = context.invoke_action("unreliable_action", {"email": email})
        assert result["success"] is False

    def test_invoke_action_not_found(self) -> None:
        """Test invoking a non-existent action raises appropriate error."""
        context = ServerContext()

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="test@example.com",
            subject="Test Email"
        )

        try:
            context.invoke_action("nonexistent_action", {"email": email})
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Action 'nonexistent_action' not found" in str(e)


class TestActionDecorator:
    """Test the @action decorator functionality."""

    def test_action_decorator_basic(self) -> None:
        """Test basic @action decorator functionality."""
        context = ServerContext()

        @context.action()
        def mark_read(email: EmailPage) -> bool:
            """Mark an email as read"""
            email.read = True
            return True

        assert "mark_read" in context.actions

    def test_action_decorator_with_custom_name(self) -> None:
        """Test @action decorator with custom name."""
        context = ServerContext()

        @context.action(name="custom_archive")
        def archive_email(email: EmailPage) -> bool:
            """Archive an email"""
            return True

        assert "custom_archive" in context.actions
        assert "archive_email" not in context.actions

    def test_standalone_action_decorator(self) -> None:
        """Test standalone action registration."""
        context = ServerContext()
        
        def standalone_delete(email: EmailPage) -> bool:
            """Delete an email"""
            return True
        
        # Register with context
        context.register_action("standalone_delete", standalone_delete)
        assert "standalone_delete" in context.actions


class TestActionValidation:
    """Test action validation logic."""

    def test_invalid_return_type_registration(self) -> None:
        """Test that actions with invalid return types are rejected during registration."""
        context = ServerContext()

        # This should fail because it doesn't return bool
        def bad_action_wrong_return(email: EmailPage) -> str:
            return "success"

        try:
            context.register_action("bad_action", bad_action_wrong_return)
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "must have a Page (or subclass) as the first parameter and return a boolean" in str(e)

    def test_invalid_first_parameter_registration(self) -> None:
        """Test that actions without Page as first parameter are rejected."""
        context = ServerContext()

        # This should fail because first parameter is not Page
        def bad_action_wrong_param(text: str) -> bool:
            return True

        try:
            context.register_action("bad_action", bad_action_wrong_param)
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "must have a Page (or subclass) as the first parameter and return a boolean" in str(e)

    def test_valid_action_subclass_page(self) -> None:
        """Test that actions with Page subclasses work correctly."""
        context = ServerContext()

        def process_calendar_event(event: CalendarEventPage) -> bool:
            return len(event.attendees) > 0

        # This should work since CalendarEventPage is a subclass of Page
        context.register_action("process_calendar_event", process_calendar_event)
        assert "process_calendar_event" in context.actions


class TestPageURIConversion:
    """Test PageURI conversion functionality."""

    def test_invoke_action_with_pageuri(self) -> None:
        """Test action invocation with PageURI that gets converted to Page."""
        context = ServerContext()

        # Set up page handler
        @context.route("emails")
        def get_email(uri: PageURI) -> EmailPage:
            return EmailPage(
                uri=uri,
                sender="test@example.com",
                subject=uri.id.replace("_", " "),
                read=False
            )

        @context.action()
        def mark_email_read(email: EmailPage) -> bool:
            email.read = True
            return True

        # Create PageURI and invoke action
        email_uri = context.create_page_uri(EmailPage, "emails", "test_email", 1)
        result = context.invoke_action("mark_email_read", {"email": email_uri})

        assert result["success"] is True

    def test_invoke_action_with_pageuri_string(self) -> None:
        """Test action invocation with PageURI string."""
        context = ServerContext()

        @context.route("emails")
        def get_email(uri: PageURI) -> EmailPage:
            return EmailPage(
                uri=uri,
                sender="test@example.com",
                subject=uri.id.replace("_", " "),
                read=False
            )

        @context.action()
        def archive_email(email: EmailPage) -> bool:
            return True

        # Use string representation of PageURI
        result = context.invoke_action("archive_email", {"email": "/emails:test_email@1"})
        assert result["success"] is True


class TestActionExamples:
    """Test example actions mentioned in the issue."""

    def test_mark_email_as_read_example(self) -> None:
        """Test the 'mark email as read' example."""
        context = ServerContext()

        @context.action()
        def mark_email_as_read(email: EmailPage) -> bool:
            """Mark an email as read."""
            email.read = True
            return True

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="sender@example.com",
            subject="Important Email",
            read=False
        )

        result = context.invoke_action("mark_email_as_read", {"email": email})
        assert result["success"] is True
        assert email.read is True

    def test_forward_email_example(self) -> None:
        """Test the 'forward email to person' example."""
        context = ServerContext()

        @context.action()
        def forward_email_to_person(email: EmailPage, recipient: str) -> bool:
            """Forward an email to a specific person."""
            return "@" in recipient  # Simple validation

        email = EmailPage(
            uri=PageURI.parse("test/EmailPage:email1@1"),
            sender="sender@example.com",
            subject="Forward this"
        )

        # Test successful forward
        result = context.invoke_action("forward_email_to_person", {
            "email": email,
            "recipient": "recipient@example.com"
        })
        assert result["success"] is True

        # Test failed forward (invalid recipient)
        result = context.invoke_action("forward_email_to_person", {
            "email": email,
            "recipient": "invalid_email"
        })
        assert result["success"] is False

    def test_change_calendar_event_time_example(self) -> None:
        """Test the 'change calendar event to another time' example."""
        context = ServerContext()

        @context.action()
        def change_calendar_event_time(event: CalendarEventPage, new_time: str) -> bool:
            """Change a calendar event to another time."""
            if len(new_time) > 0:
                event.start_time = new_time
                return True
            return False

        event = CalendarEventPage(
            uri=PageURI.parse("test/CalendarEventPage:event1@1"),
            title="Team Meeting",
            start_time="2024-01-01T10:00:00",
            attendees=["alice@example.com", "bob@example.com"]
        )

        # Test successful time change
        result = context.invoke_action("change_calendar_event_time", {
            "event": event,
            "new_time": "2024-01-01T14:00:00"
        })
        assert result["success"] is True
        assert event.start_time == "2024-01-01T14:00:00"

        # Test failed time change (empty time)
        result = context.invoke_action("change_calendar_event_time", {
            "event": event,
            "new_time": ""
        })
        assert result["success"] is False