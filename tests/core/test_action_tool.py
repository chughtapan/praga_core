"""Tests for ActionTool functionality."""

from typing import Any

from praga_core.agents.tool import ActionTool
from praga_core.types import Page, PageURI


class TestPage(Page):
    """Test page implementation."""
    
    content: str = ""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)


class TestActionTool:
    """Test ActionTool functionality."""

    def test_action_tool_initialization(self) -> None:
        """Test basic ActionTool initialization."""
        def test_action(page: TestPage) -> bool:
            return True

        action_tool = ActionTool(test_action, "test_action")
        
        assert action_tool.name == "test_action"
        assert action_tool.func == test_action
        assert action_tool.description == ""

    def test_action_tool_with_description(self) -> None:
        """Test ActionTool with explicit description."""
        def test_action(page: TestPage) -> bool:
            """This is a test action."""
            return True

        action_tool = ActionTool(test_action, "test_action", "Custom description")
        
        assert action_tool.description == "Custom description"

    def test_action_tool_with_docstring(self) -> None:
        """Test ActionTool uses function docstring if no description provided."""
        def test_action(page: TestPage) -> bool:
            """This is a test action."""
            return True

        action_tool = ActionTool(test_action, "test_action")
        
        assert action_tool.description == "This is a test action."

    def test_invoke_with_dict_input(self) -> None:
        """Test invoking ActionTool with dictionary input."""
        def test_action(page: TestPage, value: str = "default") -> bool:
            return len(page.content) > 0 and len(value) > 0

        action_tool = ActionTool(test_action, "test_action")
        
        page = TestPage(uri=PageURI.parse("test/TestPage:page1@1"), content="test content")
        
        result = action_tool.invoke({"page": page, "value": "test"})
        assert result["success"] is True

    def test_invoke_with_string_input(self) -> None:
        """Test invoking ActionTool with string input (mapped to first parameter)."""
        def test_action(text: str) -> bool:
            return len(text) > 0

        action_tool = ActionTool(test_action, "test_action")
        
        result = action_tool.invoke("test string")
        assert result["success"] is True

    def test_invoke_failure(self) -> None:
        """Test ActionTool returns False on action failure."""
        def failing_action(page: TestPage) -> bool:
            return False

        action_tool = ActionTool(failing_action, "failing_action")
        
        page = TestPage(uri=PageURI.parse("test/TestPage:page1@1"))
        
        result = action_tool.invoke({"page": page})
        assert result["success"] is False

    def test_invoke_exception_handling(self) -> None:
        """Test ActionTool handles exceptions gracefully."""
        def exception_action(page: TestPage) -> bool:
            raise ValueError("Something went wrong")

        action_tool = ActionTool(exception_action, "exception_action")
        
        page = TestPage(uri=PageURI.parse("test/TestPage:page1@1"))
        
        result = action_tool.invoke({"page": page})
        assert result["success"] is False
        assert "error" in result
        assert "Something went wrong" in result["error"]

    def test_string_representation(self) -> None:
        """Test ActionTool string representation."""
        def test_action(page: TestPage, count: int) -> bool:
            """Test action description."""
            return True

        action_tool = ActionTool(test_action, "test_action")
        
        str_repr = str(action_tool)
        assert "test_action" in str_repr
        assert "page: TestPage" in str_repr
        assert "count: int" in str_repr
        assert "Test action description." in str_repr

    def test_metadata_extraction(self) -> None:
        """Test ActionTool metadata extraction."""
        def test_action(page: TestPage, value: str = "default") -> bool:
            return True

        action_tool = ActionTool(test_action, "test_action", "Test description")
        
        metadata = action_tool.metadata
        assert metadata.name == "test_action"
        assert metadata.description == "Test description"
        assert len(metadata.parameters) == 2
        assert "page" in metadata.parameters
        assert "value" in metadata.parameters
        assert metadata.return_type == bool