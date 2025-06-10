import json
from typing import Any, Dict, List

from .response import ResponseCode


def _create_agent_example(
    question: str,
    thought: str,
    references: List[Dict[str, Any]] | None = None,
    error_message: str | None = None,
    response_code: ResponseCode = ResponseCode.SUCCESS,
) -> str:
    """Create a formatted example for agent responses."""
    action_input = {
        "response_code": response_code,
        "references": references or [],
        "error_message": error_message,
    }
    example = {
        "question": question,
        "thought": thought,
        "action": "Final Answer",
        "action_input": action_input,
    }
    return json.dumps(example, indent=4)


def get_agent_format_instructions(include_examples: bool = True) -> str:
    """Generate format instructions for agent-based retrievers."""
    base_example = _create_agent_example(
        question="example query",
        thought="I have found relevant documents",
        references=[
            {
                "id": "doc_id",
                "document_type": "DocumentClassName",
                "explanation": "explanation of why this document is relevant",
            }
        ],
    )

    instructions = f"""
Your final answer should follow this format:
{base_example}

Follow these guidelines:
1. Return document IDs, types, and explanations, not complete documents
2. Return all relevant document references, not just one
3. Always include the document type in the "document_type" field
4. Use "success" response_code when documents are found
5. Use "error_no_documents_found" when no matches exist
6. Use "error_internal" for any other errors
"""

    if include_examples:
        # Success example with multiple documents of different types
        success_example = _create_agent_example(
            question="Find documents about AI and machine learning",
            thought="I found documents containing the requested terms",
            references=[
                {
                    "id": "doc1",
                    "document_type": "Email",
                    "explanation": "email contains AI and machine learning",
                },
                {
                    "id": "doc2",
                    "document_type": "SlackMessage",
                    "explanation": "slack message contains machine learning examples",
                },
            ],
        )

        # Not found example
        not_found_example = _create_agent_example(
            question="Find documents about quantum computing",
            thought="No documents were found matching the query",
            response_code=ResponseCode.NOT_FOUND,
            error_message="No documents containing quantum computing were found",
        )

        # Internal error example
        error_example = _create_agent_example(
            question="Find documents about X",
            thought="The search operation failed",
            response_code=ResponseCode.INTERNAL_ERROR,
            error_message="Failed to execute search",
        )

        instructions += f"""
Example responses:

For successful retrieval with multiple document types:
{success_example}

For no documents found:
{not_found_example}

For internal errors:
{error_example}
"""

    return instructions
