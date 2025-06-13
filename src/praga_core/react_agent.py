"""ReAct agent implementation for praga_core."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from .format_instructions import get_agent_format_instructions
from .response import AgentResponse, ResponseCode, parse_agent_response
from .retriever_toolkit import RetrieverToolkitMeta
from .tool import Tool

# Configure logger with a professional format
logger = logging.getLogger(__name__)


def _format_message_content(
    role: str, content: str, include_markers: bool = True
) -> str:
    """Format a message with clear role markers and proper indentation."""
    # Clean and indent the content
    cleaned_content = content.strip().replace("\n", "\n    ")

    if include_markers:
        return f"[{role}]\n    {cleaned_content}"
    return cleaned_content


def _log_conversation_turn(
    role: str, content: str, iteration: Optional[int] = None
) -> None:
    """Log a single conversation turn with professional formatting."""
    # Format the message
    formatted_msg = _format_message_content(role, content)

    # Log with consistent formatting
    logger.info("─" * 80)
    logger.info(formatted_msg)
    logger.info("─" * 80)


@dataclass(frozen=True)
class AgentAction:
    """Represents an action the agent wants to take."""

    thought: str
    action: str
    action_input: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps(
            {
                "thought": self.thought,
                "action": self.action,
                "action_input": self.action_input,
            },
            indent=2,
        )


@dataclass(frozen=True)
class AgentFinish:
    """Represents the agent's final answer."""

    thought: str
    return_values: Dict[str, Any]


@dataclass(frozen=True)
class Observation:
    """Result of executing a tool."""

    action: str
    result: Dict[str, Any]

    def to_json(self) -> str:
        return json.dumps({"observation": self.result}, indent=2)


class DocumentReference:
    """Document reference for agent results."""

    def __init__(
        self,
        id: str,
        document_type: str = "Document",
        score: float = 0.0,
        explanation: str = "",
    ):
        self.id = id
        self.document_type = document_type
        self.score = score
        self.explanation = explanation


def process_agent_response(response: AgentResponse) -> List[DocumentReference]:
    """Convert an AgentResponse to a list of DocumentReference objects."""
    if response.response_code == ResponseCode.SUCCESS:
        return [
            DocumentReference(
                id=ref.id,
                document_type=ref.document_type,
                score=0.0,
                explanation=ref.explanation,
            )
            for ref in response.references
        ]
    return []


class ReActAgent:
    """A ReAct agent that uses a toolkit to perform document retrieval."""

    REACT_TEMPLATE = """You are a helpful document retrieval assistant designed to find relevant document IDs. Your goal is to find and return references to documents that best match the user's query.

# Instructions

You have access to the following tools: 
{tools}

Your outputs should follow this JSON format:
```json
{{
    "question": "the input question to answer",
    "thought": "your reasoning about the current step",
    "action": "$TOOL_NAME",
    "action_input": $TOOL_ARGS
}}
```

Valid action values are: "Final Answer" or {tool_names}

The observation from the action will be provided to you in this format:
```json
{{
    "observation": "result from the action"
}}
```

You should continue this thought process until you reach a final answer:

# Tools

{tools}

Tool usage examples:

For single argument tools:
```json
{{
    "thought": "I need to search for documents",
    "action": "search_documents",
    "action_input": {{
        "query": "search terms"
    }}
}}
```

For multi-argument tools:
```json
{{
    "thought": "I'll search within a date range",
    "action": "get_documents_by_range",
    "action_input": {{
        "start_date": "2024-01-01",
        "end_date": "2024-03-01"
    }}
}}
```

IMPORTANT: When providing action_input values, always use direct values without any metadata or type information. For example:

CORRECT:
```json
{{
    "action_input": {{
        "arg1": "value1",
        "arg2": "value2"
    }}
}}
```

INCORRECT:
```json
{{
    "action_input": {{
        "arg1": {{
            "value": "value1",
            "type": "string"
        }},
        "arg2": {{
            "value": "value2",
            "type": "string"  
        }}
    }}
}}
```

Remember to:
- Always provide all required arguments for a tool
- Use proper JSON formatting with double quotes around keys and string values
- Keep the action and action_input structure consistent

# Paginated Tool Usage

When a tool returns a paginated response, it will include:
- documents: List of documents for the current page
- has_next_page: Boolean indicating if there are more pages
- page_number: Current page number (0-based)
- total_documents: Total number of available pages

To request paginated results, include this optional parameter in your action_input:
- page: Page number to retrieve (starting from 0, defaults to 0)

Example paginated tool call:
```json
{{
    "thought": "I need to get the second page of results",
    "action": "search_documents",
    "action_input": {{
        "query": "find emails about AI",
        "page": 1
    }}
}}
```

After each paginated response, you MUST:
1. Analyze the observation in your next thought
2. Consider:
   - The timestamp range of documents in the current page
   - If the oldest document is still within the query's date range
3. Only request the next page if:
   - has_next_page is true AND
   - the oldest document is still within the date range of the query AND
   - you need more documents to fully answer the query

# Output Instructions
{format_instructions}

Begin! Remember to:
1. Use the JSON format for all interactions
2. Follow the exact schema from the format instructions
3. Ensure all JSON is valid (no comments or trailing commas)
4. Use "document contains X" format for explanations
5. Use the correct response_code
6. Try alternative approaches before returning missing capability errors
"""

    def __init__(
        self,
        toolkit: Union[RetrieverToolkitMeta, List[RetrieverToolkitMeta]],
        openai_client: Optional[OpenAI] = None,
        model: str = "gpt-4o-mini",
        max_iterations: int = 10,
        debug: bool = False,
        **openai_kwargs: Any,
    ):
        """Initialize the ReAct agent.

        Args:
            toolkit: The retriever toolkit(s) containing available tools. Can be a single toolkit or a list of toolkits.
            openai_client: OpenAI client instance. If None, creates a new client with openai_kwargs
            model: OpenAI model to use (default: gpt-4o-mini)
            max_iterations: Maximum number of reasoning iterations
            debug: Enable debug logging (default: False)
            **openai_kwargs: Additional arguments for OpenAI client creation (api_key, etc.)
        """
        # Handle both single toolkit and list of toolkits
        if isinstance(toolkit, list):
            self.toolkits = toolkit
        else:
            self.toolkits = [toolkit]

        # Create a combined tool registry for easy lookup
        self._tool_registry: Dict[str, Tool] = {}
        self._toolkit_for_tool: Dict[str, RetrieverToolkitMeta] = {}

        for tk in self.toolkits:
            for name, tool in tk.tools.items():
                if name in self._tool_registry:
                    logger.warning(
                        f"Tool name conflict: '{name}' exists in multiple toolkits. Using first occurrence."
                    )
                    continue
                self._tool_registry[name] = tool
                self._toolkit_for_tool[name] = tk

        self.client = openai_client or OpenAI(**openai_kwargs)
        self.model = model
        self.max_iterations = max_iterations
        self.debug = debug
        self._system_prompt = self._create_system_prompt()

        # Set logging level based on debug flag
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    def _create_system_prompt(self) -> str:
        """Create the system prompt for the ReAct agent."""
        format_instructions = get_agent_format_instructions()

        # Get tool descriptions from all toolkits
        tool_descriptions = []
        tool_names = []
        for name, tool in self._tool_registry.items():
            tool_descriptions.append(tool.formatted_description)
            tool_names.append(f'"{name}"')

        return self.REACT_TEMPLATE.format(
            tools="\n".join(tool_descriptions),
            tool_names=", ".join(tool_names),
            format_instructions=format_instructions,
        )

    def search(self, query: str) -> List[DocumentReference]:
        """Execute a search using the ReAct agent's approach."""
        logger.info("Starting ReAct agent search")
        logger.info("Query: %s", query)

        try:
            return self._run_agent(query)
        except Exception as e:
            logger.error("Search failed: %s", str(e))
            return []

    def _run_agent(self, query: str) -> List[DocumentReference]:
        """Run the ReAct agent's search process."""
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": query},
        ]

        # Log initial system and user messages
        logger.info("=" * 80)
        logger.info("ReAct Agent Search Session Started")
        logger.info("=" * 80)

        _log_conversation_turn("SYSTEM", self._system_prompt)
        _log_conversation_turn("USER", query)

        for iteration in range(self.max_iterations):
            # Generate LLM response
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.1
            )
            output = response.choices[0].message.content

            # Log assistant response with null check
            if output is not None:
                _log_conversation_turn("ASSISTANT", output, iteration + 1)

                # Parse the LLM output
                parsed_output = self._parse_llm_output(output)
            else:
                logger.error("LLM returned None output")
                break

            if parsed_output is None:
                logger.error("Failed to parse LLM output")
                break

            if isinstance(parsed_output, AgentFinish):
                # Agent has finished - extract and return results
                agent_response = AgentResponse(**parsed_output.return_values)
                final_results = process_agent_response(agent_response)

                # Log completion
                logger.info("=" * 80)
                logger.info(
                    f"Search completed: Found {len(final_results)} document references"
                )
                logger.info("=" * 80)

                return final_results

            elif isinstance(parsed_output, AgentAction):
                # Add assistant message to conversation
                messages.append(
                    {"role": "assistant", "content": parsed_output.to_json()}
                )

                # Execute the tool - find the correct toolkit for this tool
                try:
                    toolkit = self._toolkit_for_tool.get(parsed_output.action)
                    if toolkit is None:
                        raise ValueError(
                            f"Tool '{parsed_output.action}' not found in any toolkit"
                        )

                    result = toolkit.invoke_tool(
                        parsed_output.action, parsed_output.action_input
                    )

                    observation = Observation(
                        action=parsed_output.action, result=result
                    )
                    observation_content = observation.to_json()

                    # Log tool execution result
                    _log_conversation_turn(
                        "SYSTEM",
                        f"Tool '{parsed_output.action}' executed",
                        iteration + 1,
                    )
                    _log_conversation_turn("USER", observation_content, iteration + 1)

                    messages.append({"role": "user", "content": observation_content})

                except Exception as e:
                    # Tool execution failed - provide error feedback
                    error_msg = f"Tool execution failed: {str(e)}"
                    logger.error(error_msg)

                    observation = Observation(
                        action=parsed_output.action, result={"error": error_msg}
                    )
                    error_content = observation.to_json()

                    # Log error observation
                    _log_conversation_turn(
                        "SYSTEM", "Tool execution failed", iteration + 1
                    )
                    _log_conversation_turn("USER", error_content, iteration + 1)

                    messages.append({"role": "user", "content": error_content})
            else:
                logger.error("Unknown parsed output type: %s", type(parsed_output))
                break

        # Max iterations reached without final answer
        logger.warning(
            "Maximum iterations (%d) reached without finding a final answer",
            self.max_iterations,
        )
        return []

    def _parse_llm_output(
        self, output: Union[str, Dict[str, Any]]
    ) -> Union[AgentAction, AgentFinish, None]:
        """Parse the LLM output into an action or finish state."""
        try:
            if isinstance(output, str):
                # Handle markdown-wrapped JSON
                json_str = self._extract_json_from_markdown(output)
                output_dict = json.loads(json_str)
            else:
                output_dict = output

            thought = output_dict.get("thought", "")
            action = output_dict.get("action", "")

            if action.lower() == "final answer":
                action_input = output_dict.get("action_input", {})
                agent_response = parse_agent_response(action_input)
                return AgentFinish(
                    thought=thought, return_values=agent_response.model_dump()
                )
            else:
                action_input = output_dict.get("action_input", {})
                return AgentAction(
                    thought=thought,
                    action=action,
                    action_input=action_input,
                )

        except Exception as e:
            logger.error(f"Failed to parse LLM output: {e}")
            logger.error(f"Raw output was: {output}")

            return AgentFinish(
                thought="Error parsing output",
                return_values=AgentResponse(
                    response_code=ResponseCode.INTERNAL_ERROR,
                    references=[],
                    error_message=f"Failed to parse agent output: {str(e)}",
                ).model_dump(),
            )

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks."""
        # Remove any markdown code block markers
        text = text.strip()

        # Handle ```json ... ``` blocks
        if text.startswith("```json"):
            # Find the closing ```
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                json_content = text[start:end].strip()
                return json_content

        # Handle ``` ... ``` blocks (without json specifier)
        if text.startswith("```"):
            # Find the closing ```
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                json_content = text[start:end].strip()
                return json_content

        # If no markdown blocks, try to find JSON-like content
        # Look for content between { and }
        if "{" in text and "}" in text:
            start = text.find("{")
            # Find the matching closing brace
            brace_count = 0
            end = -1
            for i in range(start, len(text)):
                if text[i] == "{":
                    brace_count += 1
                elif text[i] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        end = i + 1
                        break

            if end != -1:
                json_content = text[start:end].strip()
                return json_content

        # If all else fails, return the original text
        return text
