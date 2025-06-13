"""Pytest tests for the response parser."""

import pytest

from praga_core.retriever import (
    AgentResponse,
    ResponseCode,
    parse_agent_response,
    process_agent_response,
)


class TestResponseParser:
    """Test response parser functionality."""

    def test_parse_direct_dict_response(self):
        """Test parsing a direct dictionary response without action wrapper."""
        response_dict = {
            "response_code": "success",
            "references": [
                {
                    "id": "7",
                    "explanation": "document contains 'client feedback' in the subject",
                }
            ],
            "error_message": "",
        }

        result = parse_agent_response(response_dict)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].id == "7"
        assert "client feedback" in result.references[0].explanation

    def test_parse_json_string_response(self):
        """Test parsing a JSON string response."""
        json_str = """
        {
            "response_code": "success",
            "references": [
                {
                    "id": "doc2",
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
        assert result.references[0].id == "doc2"

    def test_parse_code_block_response(self):
        """Test parsing a response wrapped in code blocks."""
        code_block_response = """
        Here's the result:
        ```json
        {
            "response_code": "success",
            "references": [
                {
                    "id": "doc3",
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
        assert result.references[0].id == "doc3"

    def test_parse_markdown_json_block(self):
        """Test parsing a response wrapped in markdown JSON blocks."""
        markdown_response = """
        ```json
        {
            "response_code": "success",
            "references": [
                {
                    "id": "doc4",
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
        assert result.references[0].id == "doc4"

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
            "references": [{"id": "doc1", "explanation": "test"}],
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
                    {"id": "doc5", "explanation": "wrapped in action format"}
                ],
                "error_message": "",
            },
        }

        result = parse_agent_response(action_wrapper)
        assert isinstance(result, AgentResponse)
        assert result.response_code == ResponseCode.SUCCESS
        assert len(result.references) == 1
        assert result.references[0].id == "doc5"

    def test_process_agent_response(self):
        """Test converting AgentResponse to DocumentReference list."""
        response = AgentResponse(
            response_code=ResponseCode.SUCCESS,
            references=[
                {"id": "doc1", "explanation": "matches criteria"},
                {"id": "doc2", "explanation": "also matches"},
            ],
            error_message="",
        )

        refs = process_agent_response(response)
        assert len(refs) == 2
        assert refs[0].id == "doc1"
        assert refs[0].score == 0.0
        assert refs[0].explanation == "matches criteria"
        assert refs[1].id == "doc2"

    def test_process_error_response_to_references(self):
        """Test converting error response to empty reference list."""
        response = AgentResponse(
            response_code=ResponseCode.NOT_FOUND,
            references=[],
            error_message="No documents found",
        )

        refs = process_agent_response(response)
        assert len(refs) == 0

    def test_numeric_id_coercion(self):
        """Test that numeric IDs are coerced to strings."""
        response = AgentResponse(
            response_code=ResponseCode.SUCCESS,
            references=[
                {"id": 42, "document_type": "Email", "explanation": "test"},
                {"id": 7.5, "document_type": "Email", "explanation": "test"},
            ],
            error_message="",
        )

        refs = process_agent_response(response)
        assert len(refs) == 2
        assert refs[0].id == "42"
        assert refs[1].id == "7.5"

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


if __name__ == "__main__":
    pytest.main([__file__])
