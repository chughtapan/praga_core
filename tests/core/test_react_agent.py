"""Comprehensive pytest tests for the ReactAgent."""

import json
from typing import List
from unittest.mock import MagicMock

import pytest
from pydantic import Field

from praga_core import Page
from praga_core.agents import ReactAgent, RetrieverToolkit


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


class MockDocument(Page):
    """A simple document class for testing."""

    content: str = Field(description="The content of the document")


class MockRetrieverToolkit(RetrieverToolkit):
    """Mock retriever toolkit for testing the ReAct agent."""

    def __init__(self):
        super().__init__()

        # Mock document store
        self.documents = [
            MockDocument(
                uri="test/MockDocument:1@1", content="John works in AI research"
            ),
            MockDocument(
                uri="test/MockDocument:2@1",
                content="Sarah is a Machine Learning engineer",
            ),
            MockDocument(
                uri="test/MockDocument:3@1", content="Bob teaches Python programming"
            ),
            MockDocument(
                uri="test/MockDocument:4@1", content="John likes Python and AI"
            ),
        ]

        # Register mock tools
        self.register_tool(method=self.search_documents)
        self.register_tool(method=self.search_by_person_and_topic)

    async def search_documents(self, query: str) -> List[Page]:
        """Search through documents based on a query."""
        if not query:
            return []
        return [doc for doc in self.documents if query.lower() in doc.content.lower()]

    async def search_by_person_and_topic(self, person: str, topic: str) -> List[Page]:
        """Search documents by person name and topic."""
        if not person or not topic:
            return []
        return [
            doc
            for doc in self.documents
            if person.lower() in doc.content.lower()
            and topic.lower() in doc.content.lower()
        ]

    @property
    def name(self) -> str:
        return "MockRetrieverToolkit"


class MockEmailToolkit(RetrieverToolkit):
    """Mock email toolkit for testing multiple toolkits."""

    def __init__(self):
        super().__init__()

        # Mock email documents
        self.emails = [
            MockDocument(
                uri="test/MockDocument:email_1@1",
                content="Meeting about AI project from John",
            ),
            MockDocument(
                uri="test/MockDocument:email_2@1",
                content="Budget discussion from Sarah",
            ),
        ]

        # Register email-specific tools
        self.register_tool(method=self.search_emails)

    async def search_emails(self, query: str) -> List[Page]:
        """Search through emails."""
        if not query:
            return []
        return [doc for doc in self.emails if query.lower() in doc.content.lower()]

    @property
    def name(self) -> str:
        return "MockEmailToolkit"


class MockCalendarToolkit(RetrieverToolkit):
    """Mock calendar toolkit for testing multiple toolkits."""

    def __init__(self):
        super().__init__()

        # Mock calendar documents
        self.events = [
            MockDocument(
                uri="test/MockDocument:cal_1@1", content="Daily standup meeting"
            ),
            MockDocument(
                uri="test/MockDocument:cal_2@1", content="Team planning session"
            ),
        ]

        # Register calendar-specific tools
        self.register_tool(method=self.search_events, name="search_events")

    async def search_events(self, query: str) -> List[Page]:
        """Search through calendar events."""
        if not query:
            return []
        return [doc for doc in self.events if query.lower() in doc.content.lower()]

    @property
    def name(self) -> str:
        return "MockCalendarToolkit"


class TestReactAgentBasic:
    """Test basic ReactAgent functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_client = MockOpenAIClient()
        self.toolkit = MockRetrieverToolkit()
        self.agent = ReactAgent(
            toolkits=[self.toolkit], openai_client=self.mock_client, max_iterations=3
        )

    async def test_search_basic(self):
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
                        {
                            "uri": "test/MockDocument:1@1",
                            "explanation": "Contains AI research",
                        },
                        {"uri": "test/MockDocument:4@1", "explanation": "Contains AI"},
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        # Execute search
        references = await self.agent.search("Find documents about AI")

        # Verify results
        assert len(references) == 2
        assert references[0].uri.id == "1"
        assert references[1].uri.id == "4"

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
                        {
                            "uri": "test/MockDocument:1@1",
                            "explanation": "John works in AI research",
                        },
                        {
                            "uri": "test/MockDocument:4@1",
                            "explanation": "John likes AI",
                        },
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find where John talks about AI")

        assert len(references) == 2
        assert references[0].uri.id == "1"
        assert references[1].uri.id == "4"

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
                    {"uri": "test/MockDocument:1@1", "explanation": "Found in markdown"}
                ],
                "error_message": ""
            }
        }
        ```
        """

        self.mock_client.add_response(markdown_response)

        references = self.agent.search("Test markdown parsing")
        assert len(references) == 1
        assert references[0].uri.id == "1"

    def test_fix_invalid_json_escapes(self):
        """Test that invalid JSON escapes are properly fixed."""
        # Test the fix_json_escapes function directly
        from praga_core.agents.response import fix_json_escapes

        test_cases = [
            # Single quote escape
            ('{"text": "can\'t do this"}', '{"text": "can\'t do this"}'),
            # Multiple invalid escapes
            (
                '{"text": "email cc\'d to user\\@ domain"}',
                '{"text": "email cc\'d to user@ domain"}',
            ),
            # Valid escapes should remain unchanged
            (
                '{"text": "quote \\"here\\" and slash \\\\"}',
                '{"text": "quote \\"here\\" and slash \\\\"}',
            ),
        ]

        for input_json, expected_output in test_cases:
            result = fix_json_escapes(input_json)
            assert result == expected_output, f"Failed for input: {input_json}"

    def test_parse_llm_output_with_invalid_escapes(self):
        """Test parsing LLM output that contains invalid JSON escapes."""
        # This simulates the exact error the user encountered
        llm_output_with_invalid_escapes = """
        {
            "question": "Find all unread emails for John Doe",
            "thought": "Filtering unread emails where John Doe is recipient",
            "action": "Final Answer",
            "action_input": {
                "response_code": "success",
                "references": [
                    {
                        "uri": "google/email:197848012048cbc3@1",
                        "explanation": "email cc\'d to Tapan Chugh <tapanc@cs.washington.edu> (Re: MLLM Serving Sync)"
                    }
                ],
                "error_message": null
            }
        }
        """

        parsed_output = self.agent._parse_llm_output(llm_output_with_invalid_escapes)

        # Should successfully parse without error
        assert parsed_output is not None
        # Import AgentFinish from the react_agent module
        from praga_core.agents.react_agent import AgentFinish

        assert isinstance(parsed_output, AgentFinish)

        # Verify the content was parsed correctly
        return_values = parsed_output.return_values
        assert return_values["response_code"] == "success"
        assert len(return_values["references"]) == 1
        assert (
            "email cc'd to Tapan Chugh" in return_values["references"][0]["explanation"]
        )

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
                        {
                            "uri": "test/MockDocument:1@1",
                            "explanation": "Contains AI research",
                        },
                        {"uri": "test/MockDocument:4@1", "explanation": "Contains AI"},
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
        assert references[0].uri.id == "1"

        # Check second document
        assert references[1].uri.id == "4"

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
                        {
                            "uri": "test/MockDocument:999@1",
                            "explanation": "Non-existent document",
                        },
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
        assert references[0].uri.id == "999"


class TestReactAgentMultipleToolkits:
    """Test ReactAgent with multiple toolkits."""

    def setup_method(self):
        """Set up test fixtures with multiple toolkits."""
        self.mock_client = MockOpenAIClient()
        self.email_toolkit = MockEmailToolkit()
        self.calendar_toolkit = MockCalendarToolkit()

        # Test with multiple toolkits
        self.agent = ReactAgent(
            toolkits=[self.email_toolkit, self.calendar_toolkit],
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
                        {
                            "uri": "test/MockDocument:email_1@1",
                            "explanation": "Meeting about AI project",
                        }
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find emails about meetings")
        assert len(references) == 1
        assert references[0].uri.id == "email_1"

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
                        {
                            "uri": "test/MockDocument:cal_1@1",
                            "explanation": "Daily standup meeting",
                        }
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find standup meetings")
        assert len(references) == 1
        assert references[0].uri.id == "cal_1"

    def test_tool_name_conflict_warning(self, caplog):
        """Test that tool name conflicts generate warnings."""
        # Create toolkits with conflicting tool names
        toolkit1 = MockRetrieverToolkit()
        toolkit2 = MockRetrieverToolkit()

        # Both have 'search_documents' tool
        with caplog.at_level("WARNING"):
            _ = ReactAgent(
                toolkits=[toolkit1, toolkit2], openai_client=self.mock_client
            )

        # Should have logged a warning about tool name conflict
        assert "Tool name conflict" in caplog.text
        assert "search_documents" in caplog.text

    def test_single_toolkit_compatibility(self):
        """Test that single toolkit still works (backwards compatibility)."""
        single_toolkit = MockRetrieverToolkit()
        agent = ReactAgent(
            toolkits=[single_toolkit],  # Pass single toolkit as list
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
                        {
                            "uri": "test/MockDocument:email_1@1",
                            "explanation": "Meeting about AI project",
                        }
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find emails about meetings")

        assert len(references) == 1
        assert references[0].uri.id == "email_1"

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
                        {
                            "uri": "test/MockDocument:cal_1@1",
                            "explanation": "Daily standup meeting",
                        }
                    ],
                    "error_message": "",
                },
            }
        )

        self.mock_client.add_response(mock_response_1)
        self.mock_client.add_response(mock_response_2)

        references = self.agent.search("Find standup meetings")

        assert len(references) == 1
        assert references[0].uri.id == "cal_1"


if __name__ == "__main__":
    pytest.main([__file__])
