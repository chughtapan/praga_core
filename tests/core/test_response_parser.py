"""Pytest tests for the response parser."""

import pytest

from praga_core.agents.response import AgentResponse, ResponseCode, parse_agent_response
from praga_core.types import PageURI, TextPage


class MockDocument(TextPage):
    """Mock document for testing."""

    def __init__(self, uri: PageURI, title: str = "", content: str = "Mock content"):
        super().__init__(uri=uri, content=content)
        # Add custom fields to metadata
        self.metadata.title = title  # type: ignore[attr-defined]


class TestResponseParser:
    """Test response parser functionality."""

    def test_parse_direct_dict_response(self):
        """Test parsing a direct dictionary response without action wrapper."""
        response_dict = {
            "response_code": "success",
            "references": [
                {
                    "uri": "test/TextPage:7@1",
                    "explanation": "document contains 'client feedback' in the subject",
                }
            ],
            "error_message": "",
        }

        result = parse_agent_response(response_dict)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].uri.id == "7"
        assert "client feedback" in result.references[0].explanation

    def test_parse_json_string_response(self):
        """Test parsing a JSON string response."""
        json_str = """
        {
            "response_code": "success",
            "references": [
                {
                    "uri": "test/TextPage:doc2@1",
                    "explanation": "contains requested terms"
                }
            ],
            "error_message": ""
        }
        """

        result = parse_agent_response(json_str)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].uri.id == "doc2"

    def test_parse_code_block_response(self):
        """Test parsing a response wrapped in code blocks."""
        code_block_response = """
        Here's the result:
        ```json
        {
            "response_code": "success",
            "references": [
                {
                    "uri": "test/TextPage:doc3@1",
                    "explanation": "matches criteria"
                }
            ],
            "error_message": ""
        }
        ```
        """

        result = parse_agent_response(code_block_response)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].uri.id == "doc3"

    def test_parse_markdown_json_block(self):
        """Test parsing a response wrapped in markdown JSON blocks."""
        markdown_response = """
        ```json
        {
            "response_code": "success",
            "references": [
                {
                    "uri": "test/TextPage:doc4@1",
                    "explanation": "found in markdown"
                }
            ],
            "error_message": ""
        }
        ```
        """

        result = parse_agent_response(markdown_response)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].uri.id == "doc4"

    def test_parse_error_response(self):
        """Test parsing an error response."""
        error_response = {
            "response_code": "error_no_documents_found",
            "references": [],
            "error_message": "No matching documents found",
        }

        result = parse_agent_response(error_response)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.NOT_FOUND
        assert len(result.references) == 0
        assert result.error_message == "No matching documents found"

    def test_parse_invalid_json(self):
        """Test handling of invalid JSON input."""
        invalid_json = "This is not JSON"

        result = parse_agent_response(invalid_json)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.INTERNAL_ERROR
        assert "Failed to parse" in result.error_message

    def test_parse_missing_response_code(self):
        """Test handling of response missing response_code."""
        missing_code = {
            "references": [{"uri": "test/TextPage:doc1@1", "explanation": "test"}],
            "error_message": "",
        }

        result = parse_agent_response(missing_code)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.INTERNAL_ERROR
        assert "Missing response code" in result.error_message

    def test_parse_action_wrapper_format(self):
        """Test parsing response in action/action_input wrapper format."""
        action_wrapper = {
            "thought": "Found relevant documents",
            "action": "Final Answer",
            "action_input": {
                "response_code": "success",
                "references": [
                    {
                        "uri": "test/TextPage:doc5@1",
                        "explanation": "wrapped in action format",
                    }
                ],
                "error_message": "",
            },
        }

        result = parse_agent_response(action_wrapper)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].uri.id == "doc5"

    def test_numeric_id_coercion(self):
        """Test that numeric IDs are coerced to strings."""
        response = AgentResponse(
            response_code=ResponseCode.SUCCESS,
            references=[
                {"uri": "test/TextPage:42@1", "type": "Email", "explanation": "test"},
                {"uri": "test/TextPage:7@1", "type": "Email", "explanation": "test"},
            ],
            error_message="",
        )

        assert len(response.references) == 2
        assert response.references[0].uri.id == "42"
        assert response.references[1].uri.id == "7"

    def test_response_code_mapping(self):
        """Test that various response codes are properly mapped."""
        test_cases = [
            ("success", ResponseCode.SUCCESS),
            ("error_no_documents_found", ResponseCode.NOT_FOUND),
            ("error_missing_capability", ResponseCode.MISSING_CAPABILITY),
            ("error_internal", ResponseCode.INTERNAL_ERROR),
        ]

        for code_str, expected_code in test_cases:
            response_dict = {
                "response_code": code_str,
                "references": [],
                "error_message": "",
            }

            result = parse_agent_response(response_dict)
            assert result.response_code == expected_code

    def test_parse_json_with_invalid_escapes(self):
        """Test parsing JSON with invalid escape sequences like \' generated by LLMs."""
        # This is the exact format that was failing in the user's example
        json_with_invalid_escapes = """
        {
            "response_code": "success",
            "references": [
                {
                    "uri": "test/TextPage:197848012048cbc3@1",
                    "explanation": "email cc\'d to John Doe <john.doe@example.com>"
                },
                {
                    "uri": "test/TextPage:197847ef871211d5@1", 
                    "explanation": "email with \' apostrophe and other invalid escapes like \\@ and \\#"
                }
            ],
            "error_message": null
        }
        """

        result = parse_agent_response(json_with_invalid_escapes)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 2
        assert result.references[0].uri.id == "197848012048cbc3"
        assert "email cc'd to John Doe" in result.references[0].explanation
        assert result.references[1].uri.id == "197847ef871211d5"
        assert "email with ' apostrophe" in result.references[1].explanation


if __name__ == "__main__":
    pytest.main([__file__])
