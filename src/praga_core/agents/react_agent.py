"""Document retrieval agent implementation using ReAct methodology."""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Union

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import Page, PageReference

from .format_instructions import get_agent_format_instructions
from .response import (
    AgentResponse,
    ResponseCode,
    fix_json_escapes,
    parse_agent_response,
)
from .templates.react_template import REACT_TEMPLATE
from .tool import Tool
from .toolkit import RetrieverToolkit

# Configure logger
logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class AgentAction:
    """Represents an action the agent wants to take."""

    thought: str
    action: str
    action_input: Dict[str, Any]

    def to_json(self) -> str:
        """Convert action to JSON string."""
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
        """Convert observation to JSON string."""
        return json.dumps({"observation": self.result}, indent=2)


# ============================================================================
# Helper Functions
# ============================================================================


def _format_message_content(
    role: str, content: str, include_markers: bool = True
) -> str:
    """Format a message with clear role markers and proper indentation."""
    cleaned_content = content.strip().replace("\n", "\n    ")

    if include_markers:
        return f"[{role}]\n    {cleaned_content}"
    return cleaned_content


def _log_conversation_turn(
    role: str, content: str, iteration: Optional[int] = None
) -> None:
    """Log a single conversation turn with professional formatting."""
    formatted_msg = _format_message_content(role, content)
    logger.info("─" * 80)
    logger.info(formatted_msg)
    logger.info("─" * 80)


# ============================================================================
# Main Agent Class
# ============================================================================


class ReactAgent(RetrieverAgentBase):
    """
    A document retrieval agent using ReAct (Reasoning and Acting) methodology.

    This agent uses large language models to intelligently search through documents
    by reasoning about which tools to use and how to interpret the results.
    """

    def __init__(
        self,
        toolkits: Sequence[RetrieverToolkit],
        openai_client: Optional[OpenAI] = None,
        model: str = "gpt-4o-mini",
        max_iterations: int = 10,
        debug: bool = False,
        **openai_kwargs: Any,
    ):
        """
        Initialize the RetrieverAgent.

        Args:
            toolkit: The retriever toolkit(s) containing available tools.
                    Can be a single toolkit or a list of toolkits.
            openai_client: OpenAI client instance. If None, creates a new client
                          with openai_kwargs
            model: OpenAI model to use (default: gpt-4o-mini)
            max_iterations: Maximum number of reasoning iterations
            debug: Enable debug logging (default: False)
            **openai_kwargs: Additional arguments for OpenAI client creation (api_key, etc.)
        """
        # Initialize toolkits
        self.toolkits = toolkits

        # Create tool registry for easy lookup
        self._tool_registry, self._toolkit_for_tool = self._build_tool_registry()

        # Initialize OpenAI client
        self.client = openai_client or OpenAI(**openai_kwargs)
        self.model = model
        self.max_iterations = max_iterations
        self.debug = debug

        # Create system prompt
        self._system_prompt = self._create_system_prompt()

        # Configure logging
        self._configure_logging()

        # Track pages accessed during search
        self._accessed_pages: Dict[str, Page] = {}

    async def search(self, query: str) -> List[PageReference]:
        """
        Execute a search using the ReAct agent's approach.

        Args:
            query: The search query

        Returns:
            List of DocumentReference objects containing document IDs,
            explanations, and full document objects (if available)
        """
        logger.info("Starting RetrieverAgent search")
        logger.info("Query: %s", query)

        # Clear accessed pages for new search
        self._accessed_pages.clear()

        try:
            return await self._run_agent(query)
        except Exception as e:
            logger.error("Search failed: %s", str(e))
            return []

    # ========================================================================
    # Private Initialization Methods
    # ========================================================================

    def _build_tool_registry(
        self,
    ) -> tuple[Dict[str, Tool], Dict[str, RetrieverToolkit]]:
        """Build tool registry and toolkit mapping."""
        tool_registry: Dict[str, Tool] = {}
        toolkit_for_tool: Dict[str, RetrieverToolkit] = {}

        for tk in self.toolkits:
            for name, tool in tk.tools.items():
                if name in tool_registry:
                    logger.warning(
                        f"Tool name conflict: '{name}' exists in multiple toolkits. "
                        f"Using first occurrence."
                    )
                    continue
                tool_registry[name] = tool
                toolkit_for_tool[name] = tk

        return tool_registry, toolkit_for_tool

    def _create_system_prompt(self) -> str:
        """Create the system prompt for the ReAct agent."""
        format_instructions = get_agent_format_instructions()

        # Get tool descriptions from all toolkits
        tool_descriptions = []
        tool_names = []
        for name, tool in self._tool_registry.items():
            tool_descriptions.append(tool.formatted_description)
            tool_names.append(f'"{name}"')

        return REACT_TEMPLATE.format(
            tools="\n".join(tool_descriptions),
            tool_names=", ".join(tool_names),
            format_instructions=format_instructions,
        )

    def _configure_logging(self) -> None:
        """Configure logging based on debug flag."""
        if self.debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

    # ========================================================================
    # Private Agent Execution Methods
    # ========================================================================

    async def _run_agent(self, query: str) -> List[PageReference]:
        """Run the ReAct agent's search process."""
        messages: List[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": query},
        ]

        self._log_session_start(query)

        for iteration in range(self.max_iterations):
            # Generate LLM response
            response = self._generate_llm_response(messages)
            if response is None:
                break

            # Parse the LLM output
            parsed_output = self._parse_llm_output(response)
            if parsed_output is None:
                break

            # Handle final answer
            if isinstance(parsed_output, AgentFinish):
                return self._handle_agent_finish(parsed_output)

            # Handle agent action
            if isinstance(parsed_output, AgentAction):
                messages = await self._handle_agent_action(
                    parsed_output, messages, iteration
                )
            else:
                logger.error("Unknown parsed output type: %s", type(parsed_output))
                break

        # Max iterations reached
        logger.warning(
            "Maximum iterations (%d) reached without finding a final answer",
            self.max_iterations,
        )
        return []

    def _generate_llm_response(
        self, messages: List[ChatCompletionMessageParam]
    ) -> Optional[str]:
        """Generate response from LLM."""
        try:
            response = self.client.chat.completions.create(
                model=self.model, messages=messages
            )
            output = response.choices[0].message.content

            if output is not None:
                _log_conversation_turn("ASSISTANT", output)
                return output
            else:
                logger.error("LLM returned None output")
                return None
        except Exception as e:
            logger.error("Failed to generate LLM response: %s", str(e))
            return None

    def _handle_agent_finish(self, agent_finish: AgentFinish) -> List[PageReference]:
        """Handle agent finish state."""
        agent_response = AgentResponse(**agent_finish.return_values)
        if agent_response.response_code != ResponseCode.SUCCESS:
            logger.error("Agent response code: %s", agent_response.response_code)
            return []

        # Resolve references using tracked pages
        resolved_references = self._resolve_references_internally(
            agent_response.references
        )

        logger.info("=" * 80)
        logger.info(
            f"Search completed: Found {len(resolved_references)} document references"
        )
        logger.info("=" * 80)

        return resolved_references

    def _resolve_references_internally(
        self, references: List[PageReference]
    ) -> List[PageReference]:
        """Resolve PageReference objects using tracked pages."""
        resolved_references = []

        for ref in references:
            uri_str = str(ref.uri)

            # Try to find the page in our tracked pages
            if uri_str in self._accessed_pages:
                # Create a new reference with the resolved page
                resolved_ref = PageReference(
                    uri=ref.uri, score=ref.score, explanation=ref.explanation
                )
                resolved_ref.page = self._accessed_pages[uri_str]
                resolved_references.append(resolved_ref)
                logger.debug(f"Resolved reference: {uri_str}")
            else:
                # Keep the original reference if we can't resolve it
                resolved_references.append(ref)
                logger.debug(f"Could not resolve reference: {uri_str}")

        return resolved_references

    async def _handle_agent_action(
        self,
        action: AgentAction,
        messages: List[ChatCompletionMessageParam],
        iteration: int,
    ) -> List[ChatCompletionMessageParam]:
        """Handle agent action execution."""
        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": action.to_json()})

        # Execute the tool
        observation_content = await self._execute_tool(action, iteration)

        # Add observation to conversation
        messages.append({"role": "user", "content": observation_content})

        return messages

    async def _execute_tool(self, action: AgentAction, iteration: int) -> str:
        """Execute a tool and return observation."""
        try:
            toolkit = self._toolkit_for_tool.get(action.action)
            if toolkit is None:
                raise ValueError(f"Tool '{action.action}' not found in any toolkit")

            # Execute tool with page tracking
            result = await toolkit.invoke_tool(
                action.action, action.action_input, callbacks=[self._track_pages]
            )

            observation = Observation(action=action.action, result=result)
            observation_content = observation.to_json()

            # Log tool execution result
            _log_conversation_turn(
                "SYSTEM", f"Tool '{action.action}' executed", iteration + 1
            )
            _log_conversation_turn("USER", observation_content, iteration + 1)

            return observation_content

        except Exception as e:
            # Tool execution failed - provide error feedback
            error_msg = f"Tool execution failed: {str(e)}"
            logger.error(error_msg)

            observation = Observation(action=action.action, result={"error": error_msg})
            error_content = observation.to_json()

            # Log error observation
            _log_conversation_turn("SYSTEM", "Tool execution failed", iteration + 1)
            _log_conversation_turn("USER", error_content, iteration + 1)

            return error_content

    def _log_session_start(self, query: str) -> None:
        """Log the start of a search session."""
        logger.info("=" * 80)
        logger.info("RetrieverAgent Search Session Started")
        logger.info("=" * 80)

        _log_conversation_turn("SYSTEM", self._system_prompt)
        _log_conversation_turn("USER", query)

    # ========================================================================
    # Private Parsing Methods
    # ========================================================================

    def _parse_llm_output(
        self, output: Union[str, Dict[str, Any]]
    ) -> Union[AgentAction, AgentFinish, None]:
        """Parse the LLM output into an action or finish state."""
        try:
            if isinstance(output, str):
                # Handle markdown-wrapped JSON
                json_str = self._extract_json_from_markdown(output)
                # Fix invalid JSON escapes before parsing
                json_str = fix_json_escapes(json_str)
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

    def _track_pages(self, tool_name: str, pages: Sequence[Page]) -> None:
        """Track pages from tool results."""
        for page in pages:
            uri_str = str(page.uri)
            self._accessed_pages[uri_str] = page
            logger.debug(f"Tracked page from {tool_name}: {uri_str}")

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks."""
        text = text.strip()

        # Handle ```json ... ``` blocks
        if text.startswith("```json"):
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

        # Handle ``` ... ``` blocks (without json specifier)
        if text.startswith("```"):
            start = text.find("```") + 3
            end = text.find("```", start)
            if end != -1:
                return text[start:end].strip()

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
                return text[start:end].strip()

        # If all else fails, return the original text
        return text
