"""Orchestrator agent implementation for planning and coordinating multi-step workflows."""

import logging
from enum import Enum
from typing import Any, Dict, List, Optional

from openai import OpenAI
from pydantic import BaseModel, Field

from praga_core.retriever import RetrieverAgentBase
from praga_core.types import PageReference

logger = logging.getLogger(__name__)


class StepType(str, Enum):
    """Types of steps in a workflow plan."""

    SEARCH = "search"
    AGGREGATE = "aggregate"
    FILTER = "filter"
    SYNTHESIZE = "synthesize"


class PlanStep(BaseModel):
    """A single step in the orchestration plan."""

    step_id: str = Field(description="Unique identifier for this step")
    step_type: StepType = Field(description="Type of operation to perform")
    service: str = Field(description="Service to execute this step")
    query: str = Field(description="Query or instruction for this step")
    depends_on: List[str] = Field(
        default=[], description="Step IDs this step depends on"
    )
    reasoning: str = Field(description="Why this step is needed")


class OrchestrationPlan(BaseModel):
    """Complete orchestration plan for handling a user query."""

    user_query: str = Field(description="Original user query")
    strategy: str = Field(description="Orchestration strategy being used")
    steps: List[PlanStep] = Field(description="Ordered list of steps to execute")
    expected_outcome: str = Field(description="What the plan should achieve")


class OrchestratorAgent(RetrieverAgentBase):
    """
    Orchestrator agent that plans and coordinates multi-step workflows across services.

    Uses advanced reasoning models for planning and execution models for synthesis.
    Inspired by Amazon Bedrock's custom orchestrator and fast-agent patterns.
    """

    def __init__(
        self,
        agents: Dict[str, RetrieverAgentBase],
        reasoning_model: str = "o1-mini",
        execution_model: str = "gpt-4o-mini",
        openai_client: Optional[OpenAI] = None,
        **openai_kwargs: Any,
    ):
        """
        Initialize the OrchestratorAgent.

        Args:
            agents: Dictionary mapping service names to their respective agents
            reasoning_model: Model for complex planning and reasoning (e.g., o1-mini)
            execution_model: Model for execution and synthesis tasks
            openai_client: OpenAI client instance. If None, creates a new client
            **openai_kwargs: Additional arguments for OpenAI client creation
        """
        self.agents = agents
        self.reasoning_model = reasoning_model
        self.execution_model = execution_model
        self.client = openai_client or OpenAI(**openai_kwargs)

        # Create planning prompt
        self._planning_prompt = self._create_planning_prompt()

        logger.info(
            f"OrchestratorAgent initialized with {len(agents)} service agents: {list(agents.keys())}"
        )

    def search(self, query: str) -> List[PageReference]:
        """
        Plan and execute a multi-step workflow to handle the query.

        Args:
            query: The search query

        Returns:
            List of PageReference objects from orchestrated execution
        """
        logger.info("🚀 OrchestratorAgent received query: '%s'", query)

        try:
            # Step 1: Plan the workflow using reasoning model
            logger.info(
                "🧠 Planning workflow with reasoning model: %s", self.reasoning_model
            )
            plan = self._create_plan(query)

            logger.info(
                "📋 Created orchestration plan: strategy='%s', steps=%d, expected_outcome='%s'",
                plan.strategy,
                len(plan.steps),
                plan.expected_outcome,
            )

            # Log each step details for visibility
            for i, step in enumerate(plan.steps, 1):
                deps_str = f", depends_on={step.depends_on}" if step.depends_on else ""
                logger.info(
                    "   Step %d: id='%s', type='%s', service='%s', query='%s'%s",
                    i,
                    step.step_id,
                    step.step_type,
                    step.service,
                    step.query,
                    deps_str,
                )

            # Step 2: Execute the plan
            logger.info("⚡ Executing orchestration plan...")
            results = self._execute_plan(plan)

            logger.info(
                "✅ OrchestratorAgent completed successfully: executed %d steps, returned %d results",
                len(plan.steps),
                len(results),
            )

            return results

        except Exception as e:
            logger.error("❌ OrchestratorAgent failed: %s", str(e))
            raise

    def _create_planning_prompt(self) -> str:
        """Create the planning prompt template for orchestration."""
        service_descriptions = self._get_service_descriptions()
        available_services = list(self.agents.keys())

        return f"""You are an AI orchestrator that creates detailed execution plans for complex queries.

IMPORTANT: You must ONLY use these exact service names in your plans:
{', '.join(available_services)}

Available services:
{service_descriptions}

Your task is to analyze user queries and create a strategic execution plan:

1. **Determine Strategy**: Choose between:
   - "simple": Single service can handle the query directly
   - "parallel": Multiple services needed, can run simultaneously  
   - "sequential": Multiple services needed, must run in order
   - "synthesis": Multiple services + final aggregation/synthesis step

2. **Plan Steps**: Create specific steps with:
   - Unique step_id (step_1, step_2, etc.)
   - step_type: search, aggregate, filter, or synthesize
   - service: MUST be one of: {available_services}
   - query: specific instruction for that service
   - depends_on: list of prerequisite step IDs (empty for parallel)
   - reasoning: why this step is needed

3. **Expected Outcome**: Describe what the complete plan will achieve

CRITICAL RULES:
- Never use "orchestrator", "router", or any service name not in the available list
- Only use these exact services: {available_services}
- Each step.service MUST be from the available services list

Examples:
- "Show me recent emails from Alice" → simple strategy, service: "gmail"
- "What's on my calendar today and any related emails?" → parallel strategy, services: "calendar" and "gmail"
- "Find John's contact info" → simple strategy, service: "people"
- "Show me documents about project X" → simple strategy, service: "docs"

Query: {{query}}"""

    def _get_service_descriptions(self) -> str:
        """Generate descriptions for available services."""
        service_list = []
        for service_name in self.agents.keys():
            # Try to get description from the agent's toolkit if available
            agent = self.agents[service_name]
            desc = f"{service_name.replace('_', ' ').title()} operations"

            if hasattr(agent, "toolkits") and agent.toolkits:
                toolkit = agent.toolkits[0]
                if hasattr(toolkit, "name"):
                    desc = f"{toolkit.name} operations"

            service_list.append(f"- {service_name}: {desc}")

        return "\n".join(service_list)

    def _create_plan(self, query: str) -> OrchestrationPlan:
        """Use reasoning model to create execution plan."""
        try:
            # Build parameters - reasoning models don't support temperature
            params = {
                "model": self.reasoning_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert orchestration planner. Create detailed, executable plans. Follow the service constraints exactly.",
                    },
                    {
                        "role": "user",
                        "content": self._planning_prompt.format(query=query),
                    },
                ],
                "response_format": OrchestrationPlan,
            }

            # Only add temperature for non-reasoning models
            if not self.reasoning_model.startswith(("o1", "o3", "o4")):
                params["temperature"] = 0.0

            response = self.client.beta.chat.completions.parse(**params)

            plan = response.choices[0].message.parsed
            if not plan:
                raise ValueError("Failed to parse orchestration plan")

            # Validate plan
            self._validate_plan(plan)

            return plan

        except Exception as e:
            logger.error("Planning failed: %s", str(e))
            raise ValueError(f"Planning failed: {str(e)}")

    def _validate_plan(self, plan: OrchestrationPlan) -> None:
        """Validate that the plan is executable."""
        # Check all services exist
        for step in plan.steps:
            if step.service not in self.agents:
                available = list(self.agents.keys())
                raise ValueError(
                    f"Plan uses unavailable service '{step.service}'. Available: {available}"
                )

        # Check dependency references are valid
        step_ids = {step.step_id for step in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    raise ValueError(
                        f"Step '{step.step_id}' depends on non-existent step '{dep}'"
                    )

    def _execute_plan(self, plan: OrchestrationPlan) -> List[PageReference]:
        """Execute the orchestration plan and return combined results."""
        logger.info("🔄 Executing plan with strategy: '%s'", plan.strategy)

        # Track step results
        step_results: Dict[str, List[PageReference]] = {}
        executed_steps = set()

        # Execute steps based on dependencies
        total_steps = len(plan.steps)
        while len(executed_steps) < total_steps:
            ready_steps = [
                step
                for step in plan.steps
                if step.step_id not in executed_steps
                and all(dep in executed_steps for dep in step.depends_on)
            ]

            if not ready_steps:
                remaining = [
                    s.step_id for s in plan.steps if s.step_id not in executed_steps
                ]
                logger.error(
                    "🔄 Circular dependency detected in remaining steps: %s", remaining
                )
                raise ValueError(f"Circular dependency detected in steps: {remaining}")

            logger.info(
                "🔄 Ready to execute %d steps: %s",
                len(ready_steps),
                [s.step_id for s in ready_steps],
            )

            # Execute ready steps (can be parallel)
            for step in ready_steps:
                logger.info(
                    "▶️  Executing step '%s': %s('%s') on service '%s'",
                    step.step_id,
                    step.step_type,
                    step.query,
                    step.service,
                )

                step_results[step.step_id] = self._execute_step(step, step_results)
                executed_steps.add(step.step_id)

                logger.info(
                    "✅ Step '%s' completed: %d results",
                    step.step_id,
                    len(step_results[step.step_id]),
                )

        logger.info(
            "🔄 All steps executed (%d/%d), combining results...",
            len(executed_steps),
            total_steps,
        )

        # Combine results based on strategy
        if plan.strategy == "simple":
            # Return results from the single step
            final_results = list(step_results.values())[0] if step_results else []
            logger.info(
                "📊 Simple strategy: returning %d results from single step",
                len(final_results),
            )
            return final_results

        elif plan.strategy in ["parallel", "sequential"]:
            # Combine all search results
            all_results = []
            search_steps = [s for s in plan.steps if s.step_type == StepType.SEARCH]
            for step in search_steps:
                step_count = len(step_results[step.step_id])
                all_results.extend(step_results[step.step_id])
                logger.info(
                    "📊 Added %d results from search step '%s'",
                    step_count,
                    step.step_id,
                )

            logger.info(
                "📊 %s strategy: combined %d total results from %d search steps",
                plan.strategy.title(),
                len(all_results),
                len(search_steps),
            )
            return all_results

        elif plan.strategy == "synthesis":
            # Look for final synthesis step, otherwise combine all
            synthesis_steps = [
                s for s in plan.steps if s.step_type == StepType.SYNTHESIZE
            ]
            if synthesis_steps:
                # Return results from the last synthesis step
                final_step = synthesis_steps[-1]
                final_results = step_results[final_step.step_id]
                logger.info(
                    "📊 Synthesis strategy: returning %d results from final synthesis step '%s'",
                    len(final_results),
                    final_step.step_id,
                )
                return final_results
            else:
                # Fallback: combine all search results
                all_results = []
                search_steps = [s for s in plan.steps if s.step_type == StepType.SEARCH]
                for step in search_steps:
                    all_results.extend(step_results[step.step_id])
                logger.info(
                    "📊 Synthesis strategy (no synthesis step): combined %d results from %d search steps",
                    len(all_results),
                    len(search_steps),
                )
                return all_results

        else:
            # Default: combine all results
            all_results = []
            for step_id, results in step_results.items():
                all_results.extend(results)
                logger.info("📊 Added %d results from step '%s'", len(results), step_id)
            logger.info(
                "📊 Default strategy: combined %d total results from all steps",
                len(all_results),
            )
            return all_results

    def _execute_step(
        self, step: PlanStep, previous_results: Dict[str, List[PageReference]]
    ) -> List[PageReference]:
        """Execute a single step in the plan."""
        if step.step_type == StepType.SEARCH:
            # Direct search with the specified service
            logger.info("🔍 Searching with %s service: '%s'", step.service, step.query)
            agent = self.agents[step.service]
            results = agent.search(step.query)
            logger.info(
                "🔍 Search completed: %d results from %s", len(results), step.service
            )
            return results

        elif step.step_type == StepType.SYNTHESIZE:
            # Use execution model to synthesize results from previous steps
            context_results = []
            logger.info(
                "🔬 Synthesizing results from dependencies: %s", step.depends_on
            )

            for dep_id in step.depends_on:
                dep_results = previous_results.get(dep_id, [])
                context_results.extend(dep_results)
                logger.info(
                    "🔬 Added %d results from dependency '%s'", len(dep_results), dep_id
                )

            # For now, just return the context results
            # TODO: Implement actual synthesis using execution_model
            logger.info(
                "🔬 Synthesis step returning %d context results (TODO: implement actual synthesis)",
                len(context_results),
            )
            return context_results

        elif step.step_type in [StepType.AGGREGATE, StepType.FILTER]:
            # Combine/filter results from dependencies
            combined_results = []
            logger.info(
                "📋 %s results from dependencies: %s",
                step.step_type.title(),
                step.depends_on,
            )

            for dep_id in step.depends_on:
                dep_results = previous_results.get(dep_id, [])
                combined_results.extend(dep_results)
                logger.info(
                    "📋 Added %d results from dependency '%s'", len(dep_results), dep_id
                )

            # TODO: Implement actual filtering/aggregation logic
            logger.info(
                "📋 %s step returning %d combined results (TODO: implement actual %s logic)",
                step.step_type.title(),
                len(combined_results),
                step.step_type.lower(),
            )
            return combined_results

        else:
            logger.error("❌ Unknown step type: %s", step.step_type)
            raise ValueError(f"Unknown step type: {step.step_type}")
