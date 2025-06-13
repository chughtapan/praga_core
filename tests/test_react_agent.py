"""Comprehensive pytest tests for the ReAct agent."""

import json
from typing import List
from unittest.mock import MagicMock

import pytest
from pydantic import Field

from praga_core import (
    ReActAgent,
    RetrieverToolkit,
)
from praga_core.types import Document


class MockOpenAIClient:
    """Mock OpenAI client for testing that simulates LLM responses."""

    def __init__(self):
        self.responses = []
        self.call_count = 0
        self.messages_history = []
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = self._create_completion

    def add_response(self, response: str):
        """Add a response to the queue."""
        self.responses.append(response)

    def _create_completion(self, **kwargs):
        """Mock completion creation."""
        self.messages_history.append(kwargs.get("messages", []))

        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()

        if self.call_count < len(self.responses):
            content = self.responses[self.call_count]
            self.call_count += 1
        else:
            # Default fallback response
            content = json.dumps(
                {
                    "thought": "Default response",
                    "action": "Final Answer",
                    "action_input": {
                        "response_code": "success",
                        "references": [],
                        "error_message": "",
                    },
                }
            )

        mock_message.content = content
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        return mock_response

    def get_last_messages(self):
        """Get the last set of messages sent to the client."""
        return self.messages_history[-1] if self.messages_history else []

    def reset(self):
        """Reset the mock client state."""
        self.responses = []
        self.call_count = 0
        self.messages_history = []


class MockDocument(Document):
    """A simple document class for testing."""

    content: str = Field(description="The content of the document")
    document_type: str = Field(default="MockDocument", description="Type of document")

    def __init__(self, doc_id: str, content: str, **data):
        super().__init__(
            id=doc_id, content=content, document_type="MockDocument", **data
        )


class MockRetrieverToolkit(RetrieverToolkit):
    """Mock retriever toolkit for testing the ReAct agent."""

    def __init__(self):
        super().__init__()

        # Mock document store
        self.documents = [
            MockDocument("1", "John works in AI research"),
            MockDocument("2", "Sarah is a Machine Learning engineer"),
            MockDocument("3", "Bob teaches Python programming"),
            MockDocument("4", "John likes Python and AI"),
        ]

        # Register mock tools
        self.register_tool(method=self.search_documents, name="search_documents")
        self.register_tool(
            method=self.search_by_person_and_topic, name="search_by_person_and_topic"
        )

    def search_documents(self, query: str) -> List[Document]:
        """Search through documents based on a query."""
        if not query:
            return []
        return [doc for doc in self.documents if query.lower() in doc.content.lower()]

    def search_by_person_and_topic(self, person: str, topic: str) -> List[Document]:
        """Search documents by person name and topic."""
        if not person or not topic:
            return []
        return [
            doc
            for doc in self.documents
            if person.lower() in doc.content.lower()
            and topic.lower() in doc.content.lower()
        ]

    def get_document_by_id(self, document_id: str) -> Document | None:
        """Get document by ID."""
        for doc in self.documents:
            if doc.id == document_id:
                return doc
        return None


class MockEmailToolkit(RetrieverToolkit):
    """Mock email toolkit for testing multiple toolkits."""

    def __init__(self):
        super().__init__()

        # Mock email documents
        self.emails = [
            MockDocument("email_1", "Meeting about AI project from John"),
            MockDocument("email_2", "Budget discussion from Sarah"),
        ]

        # Register email-specific tools
        self.register_tool(method=self.search_emails, name="search_emails")

    def search_emails(self, query: str) -> List[Document]:
        """Search through emails."""
        if not query:
            return []
        return [doc for doc in self.emails if query.lower() in doc.content.lower()]

    def get_document_by_id(self, document_id: str) -> Document | None:
        """Get email by ID."""
        for doc in self.emails:
            if doc.id == document_id:
                return doc
        return None


class MockCalendarToolkit(RetrieverToolkit):
    """Mock calendar toolkit for testing multiple toolkits."""

    def __init__(self):
        super().__init__()

        # Mock calendar documents
        self.events = [
            MockDocument("cal_1", "Daily standup meeting"),
            MockDocument("cal_2", "Team planning session"),
        ]

        # Register calendar-specific tools
        self.register_tool(method=self.search_events, name="search_events")

    def search_events(self, query: str) -> List[Document]:
        """Search through calendar events."""
        if not query:
            return []
        return [doc for doc in self.events if query.lower() in doc.content.lower()]

    def get_document_by_id(self, document_id: str) -> Document | None:
        """Get event by ID."""
        for doc in self.events:
            if doc.id == document_id:
                return doc
        return None


class TestReActAgentBasic:
    """Test basic ReAct agent functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MockOpenAIClient()
        self.toolkit = MockRetrieverToolkit()
        self.agent = ReActAgent(
            toolkit=self.toolkit, openai_client=self.mock_client, max_iterations=3
        )

    def test_search_basic(self):
        """Test basic search functionality."""
        # Set up mock responses
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for documents about AI",
                "action": "search_documents",
                "action_input": {"query": "AI"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found relevant documents about AI",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "1", "explanation": "Contains AI research"},
                        {"id": "4", "explanation": "Contains AI"},
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        # Execute search
        references = self.agent.search("Find documents about AI")

        # Verify results
        assert len(references) == 2
        assert references[0].id == "1"
        assert references[1].id == "4"

        # Verify the client was called correctly
        messages = self.mock_client.get_last_messages()
        assert len(messages) >= 2  # System message + user query
        assert messages[1]["content"] == "Find documents about AI"

    def test_search_no_results(self):
        """Test search with query that should return no results."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for documents about quantum physics",
                "action": "search_documents",
                "action_input": {"query": "quantum physics"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "No documents found about quantum physics",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "error_no_documents_found",
                    "references": [],
                    "error_message": "No matching documents found",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find documents about quantum physics")
        assert len(references) == 0

    def test_search_by_person_and_topic(self):
        """Test search using a tool with multiple arguments."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should use the search_by_person_and_topic tool",
                "action": "search_by_person_and_topic",
                "action_input": {"person": "John", "topic": "AI"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found documents where John talks about AI",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "1", "explanation": "John works in AI research"},
                        {"id": "4", "explanation": "John likes AI"},
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find where John talks about AI")

        assert len(references) == 2
        assert references[0].id == "1"
        assert references[1].id == "4"

    def test_max_iterations_limit(self):
        """Test that agent respects max iterations limit."""
        # Add responses that will cause the agent to loop
        for _ in range(5):  # More than max_iterations
            self.mock_client.add_response(
                json.dumps(
                    {
                        "thought": "Still searching...",
                        "action": "search_documents",
                        "action_input": {"query": "test"},
                    }
                )
            )

        references = self.agent.search("Test max iterations")
        assert len(references) == 0  # Should return empty due to max iterations

    def test_markdown_json_parsing(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        markdown_response = """
        Here's my response:
        ```json
        {
            "thought": "Found relevant documents",
            "action": "Final Answer",
            "action_input": {
                "response_code": "success",
                "references": [
                    {"id": "1", "explanation": "Found in markdown"}
                ],
                "error_message": ""
            }
        }
        ```
        """

        self.mock_client.add_response(markdown_response)

        references = self.agent.search("Test markdown parsing")
        assert len(references) == 1
        assert references[0].id == "1"

    def test_raw_document_retrieval(self):
        """Test that documents are properly retrieved and included in results."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for documents about AI",
                "action": "search_documents",
                "action_input": {"query": "AI"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found relevant documents about AI",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "1", "explanation": "Contains AI research"},
                        {"id": "4", "explanation": "Contains AI"},
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        # Execute search
        references = self.agent.search("Find documents about AI")

        # Verify results include documents
        assert len(references) == 2

        # Check first document
        assert references[0].id == "1"
        assert references[0].document is not None
        assert references[0].document.id == "1"
        assert references[0].document.content == "John works in AI research"

        # Check second document
        assert references[1].id == "4"
        assert references[1].document is not None
        assert references[1].document.id == "4"
        assert references[1].document.content == "John likes Python and AI"

    def test_raw_document_not_found(self):
        """Test behavior when document ID is not found in any toolkit."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for documents",
                "action": "search_documents",
                "action_input": {"query": "test"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found a document",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "999", "explanation": "Non-existent document"},
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        # Execute search
        references = self.agent.search("Find non-existent document")

        # Verify that the reference is created but document is None
        assert len(references) == 1
        assert references[0].id == "999"
        assert references[0].document is None


class TestReActAgentMultipleToolkits:
    """Test ReAct agent with multiple toolkits."""

    def setup_method(self):
        """Set up test fixtures with multiple toolkits."""
        self.mock_client = MockOpenAIClient()
        self.email_toolkit = MockEmailToolkit()
        self.calendar_toolkit = MockCalendarToolkit()

        # Test with multiple toolkits
        self.agent = ReActAgent(
            toolkit=[self.email_toolkit, self.calendar_toolkit],
            openai_client=self.mock_client,
            max_iterations=3,
        )

    def test_multiple_toolkits_initialization(self):
        """Test that multiple toolkits are properly initialized."""
        # Should have tools from both toolkits
        assert "search_emails" in self.agent._tool_registry
        assert "search_events" in self.agent._tool_registry

        # Should map tools to correct toolkits
        assert self.agent._toolkit_for_tool["search_emails"] == self.email_toolkit
        assert self.agent._toolkit_for_tool["search_events"] == self.calendar_toolkit

    def test_search_email_tool(self):
        """Test searching using email toolkit tool."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for emails about meetings",
                "action": "search_emails",
                "action_input": {"query": "meeting"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found email about AI meeting",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "email_1", "explanation": "Meeting about AI project"}
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find emails about meetings")
        assert len(references) == 1
        assert references[0].id == "email_1"

    def test_search_calendar_tool(self):
        """Test searching using calendar toolkit tool."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for calendar events about standup",
                "action": "search_events",
                "action_input": {"query": "standup"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found standup meeting",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "cal_1", "explanation": "Daily standup meeting"}
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find standup meetings")
        assert len(references) == 1
        assert references[0].id == "cal_1"

    def test_tool_name_conflict_warning(self, caplog):
        """Test that tool name conflicts generate warnings."""
        # Create toolkits with conflicting tool names
        toolkit1 = MockRetrieverToolkit()
        toolkit2 = MockRetrieverToolkit()

        # Both have 'search_documents' tool
        with caplog.at_level("WARNING"):
            _ = ReActAgent(toolkit=[toolkit1, toolkit2], openai_client=self.mock_client)

        # Should have logged a warning about tool name conflict
        assert "Tool name conflict" in caplog.text
        assert "search_documents" in caplog.text

    def test_single_toolkit_compatibility(self):
        """Test that single toolkit still works (backwards compatibility)."""
        single_toolkit = MockRetrieverToolkit()
        agent = ReActAgent(
            toolkit=single_toolkit,  # Pass single toolkit
            openai_client=self.mock_client,
        )

        # Should still work with single toolkit
        assert len(agent.toolkits) == 1
        assert agent.toolkits[0] == single_toolkit
        assert "search_documents" in agent._tool_registry

    def test_raw_document_retrieval_multiple_toolkits(self):
        """Test that documents are retrieved from correct toolkit in multi-toolkit setup."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for emails about meetings",
                "action": "search_emails",
                "action_input": {"query": "meeting"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found email about meeting",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "email_1", "explanation": "Meeting about AI project"}
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find emails about meetings")

        # Verify the email document is retrieved with document
        assert len(references) == 1
        assert references[0].id == "email_1"
        assert references[0].document is not None
        assert references[0].document.id == "email_1"
        assert "Meeting about AI project from John" == references[0].document.content

    def test_raw_document_cross_toolkit_fallback(self):
        """Test that the system tries multiple toolkits to find a document."""
        mock_response_1 = json.dumps(
            {
                "thought": "I should search for events",
                "action": "search_events",
                "action_input": {"query": "standup"},
            }
        )

        mock_response_2 = json.dumps(
            {
                "thought": "Found standup meeting",
                "action": "Final Answer",
                "action_input": {
                    "response_code": "success",
                    "references": [
                        {"id": "cal_1", "explanation": "Daily standup meeting"}
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find standup meetings")

        # Verify the calendar document is retrieved with document
        assert len(references) == 1
        assert references[0].id == "cal_1"
        assert references[0].document is not None
        assert references[0].document.id == "cal_1"
        assert "Daily standup meeting" == references[0].document.content


if __name__ == "__main__":
    pytest.main([__file__])
