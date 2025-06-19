import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from praga_core.types import PageReference

logger = logging.getLogger(__name__)


def fix_json_escapes(json_str: str) -> str:
    """Fix invalid JSON escape sequences that LLMs sometimes generate.

    The JSON standard only allows specific escape sequences:
    \\", \\\\, \\/, \\b, \\f, \\n, \\r, \\t, and \\uXXXX

    LLMs sometimes generate invalid escapes like \\' which need to be fixed.
    """
    # Fix invalid single quote escapes - replace \' with just '
    # This is the most common issue with LLM-generated JSON
    json_str = json_str.replace("\\'", "'")

    # Fix other common invalid escapes that might appear
    # Replace invalid escapes with their intended characters
    invalid_escapes = {
        "\\`": "`",  # backtick
        "\\&": "&",  # ampersand
        "\\%": "%",  # percent
        "\\#": "#",  # hash
        "\\@": "@",  # at symbol
        "\\$": "$",  # dollar
    }

    for invalid, replacement in invalid_escapes.items():
        json_str = json_str.replace(invalid, replacement)

    return json_str


class ResponseCode(str, Enum):
    """Response codes for retrieval operations."""

    SUCCESS = "success"
    NOT_FOUND = "error_no_documents_found"
    MISSING_CAPABILITY = "error_missing_capability"
    INTERNAL_ERROR = "error_internal"


class AgentResponse(BaseModel):
    """Structured output for agent responses."""

    response_code: ResponseCode = Field(
        description="Response code indicating success or specific error type"
    )
    references: List[PageReference] = Field(
        default_factory=list,
        description="List of document references with explanations",
    )
    error_message: Optional[str] = Field(
        None, description="Error message if response_code indicates error"
    )

    @classmethod
    def error(
        cls, code: ResponseCode, message: Optional[str] = None
    ) -> "AgentResponse":
        """Create an error response."""
        if message is None:
            # Set default error messages based on response code
            default_messages = {
                ResponseCode.NOT_FOUND: "No matching documents found",
                ResponseCode.MISSING_CAPABILITY: "Required capability not available",
                ResponseCode.INTERNAL_ERROR: "An internal error occurred",
            }
            message = default_messages.get(code, "Unknown error occurred")
        return cls(response_code=code, error_message=message)


def parse_agent_response(text: str | Dict[str, Any]) -> AgentResponse:
    """Parse the agent's response into a structured format."""
    try:
        # Handle dictionary input
        if isinstance(text, dict):
            parsed = text
        else:
            # Handle string input
            # Try to extract JSON from the text if it's wrapped in other content
            json_match = text.strip()
            if "```json" in json_match:
                json_match = json_match.split("```json")[1].split("```")[0].strip()
            elif "```" in json_match:
                json_match = json_match.split("```")[1].strip()

            # Parse the JSON string
            try:
                # Fix invalid JSON escapes before parsing
                json_match = fix_json_escapes(json_match)
                parsed = json.loads(json_match)
            except json.JSONDecodeError as e:
                logger.error("JSON decode error: %s", str(e))
                return AgentResponse.error(
                    ResponseCode.INTERNAL_ERROR,
                    f"Failed to parse JSON response: {str(e)}",
                )

        # If it's an action/action_input format, extract the action_input
        if (
            "action" in parsed
            and parsed["action"] == "Final Answer"
            and "action_input" in parsed
        ):
            parsed = parsed["action_input"]

        # Ensure response_code is present and valid
        if "response_code" not in parsed:
            logger.error("Missing response_code in parsed output")
            return AgentResponse.error(
                ResponseCode.INTERNAL_ERROR,
                "Missing response code in output",
            )

        # Parse with pydantic
        return AgentResponse(**parsed)

    except Exception as e:
        logger.error("Parser error: %s", str(e))
        return AgentResponse.error(
            ResponseCode.INTERNAL_ERROR,
            f"Failed to parse response: {str(e)}",
        )
