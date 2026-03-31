"""AgentTool - Spawn specialized sub-agents for complex tasks.

This implements Claude Code's AgentTool pattern:
- Spawn specialized sub-agents with specific roles
- Built-in agent types (explorer, planner, verifier, etc.)
- Asynchronous sub-agent execution
- Result aggregation and synthesis
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult


class AgentType(Enum):
    """Built-in agent types matching Claude Code."""

    EXPLORER = "explorer"  # Explore codebase structure
    PLANNER = "planner"  # Create implementation plans
    VERIFIER = "verifier"  # Verify changes work correctly
    GENERAL = "general"  # General purpose delegation
    RESEARCHER = "researcher"  # Deep research on specific topics
    DEBUGGER = "debugger"  # Debug issues and find root causes
    REFACTOR = "refactor"  # Code refactoring specialist
    TESTER = "tester"  # Test generation specialist


AGENT_PROMPTS: dict[AgentType, str] = {
    AgentType.EXPLORER: """You are an expert code explorer. Your job is to understand codebase structure and find relevant files.
Focus on:
- Finding files related to specific features or functionality
- Understanding module dependencies
- Identifying entry points and key abstractions
- Mapping data flow through the system

Be thorough but concise. Report findings in a structured format.""",
    AgentType.PLANNER: """You are an expert software architect and planner. Your job is to create detailed implementation plans.
Focus on:
- Breaking down complex features into manageable steps
- Identifying dependencies and prerequisites
- Considering edge cases and error handling
- Suggesting testing strategies

Create clear, actionable plans that can be executed step by step.""",
    AgentType.VERIFIER: """You are a quality assurance expert. Your job is to verify that changes work correctly.
Focus on:
- Testing the specific changes that were made
- Checking for regressions
- Verifying edge cases
- Ensuring documentation is accurate

Report what you checked, what worked, and any issues found.""",
    AgentType.GENERAL: """You are a capable software engineering assistant. Help accomplish the given task efficiently.
Focus on:
- Understanding the requirements clearly
- Implementing solutions that are maintainable
- Following existing code patterns and conventions
- Writing clear code with appropriate comments""",
    AgentType.RESEARCHER: """You are a deep research specialist. Your job is to thoroughly investigate topics.
Focus on:
- Finding all relevant information
- Understanding trade-offs and alternatives
- Providing comprehensive context
- Citing sources and references

Be thorough and methodical in your research.""",
    AgentType.DEBUGGER: """You are a debugging expert. Your job is to find and fix bugs efficiently.
Focus on:
- Reproducing the issue consistently
- Isolating the root cause
- Understanding why the bug exists
- Creating minimal fixes that address the root cause

Provide clear explanations of what you found and why the fix works.""",
    AgentType.REFACTOR: """You are a refactoring specialist. Your job is to improve code quality without changing behavior.
Focus on:
- Identifying code smells and anti-patterns
- Improving naming and clarity
- Reducing duplication
- Improving testability

Make conservative changes that preserve functionality while improving maintainability.""",
    AgentType.TESTER: """You are a testing expert. Your job is to create comprehensive test coverage.
Focus on:
- Identifying test cases for happy paths
- Finding edge cases and error conditions
- Creating maintainable test code
- Ensuring tests are deterministic

Generate tests that provide confidence in the implementation.""",
}


@dataclass
class SubAgentResult:
    """Result from a sub-agent execution."""

    agent_id: str
    agent_type: AgentType
    task: str
    result: str
    status: str  # "success", "error", "timeout"
    started_at: datetime
    completed_at: datetime | None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SubAgent:
    """A spawned sub-agent."""

    id: str
    agent_type: AgentType
    task: str
    system_prompt: str
    created_at: datetime
    max_iterations: int = 5
    status: str = "pending"  # pending, running, completed, failed
    result: SubAgentResult | None = None


class AgentTool(Tool):
    """Spawn a specialized sub-agent to accomplish a task.

    This is Claude Code's flagship feature - the ability to delegate
    to specialized agents for complex tasks.
    """

    name = "agent"
    description = """Spawn a specialized sub-agent to accomplish a specific task.

Use this tool when:
1. The task is complex and can be broken into sub-tasks
2. You need specialized expertise (exploration, planning, verification, etc.)
3. You want to parallelize work across multiple agents
4. The task requires deep focus on a specific area

Available agent types:
- explorer: Explore codebase structure and find relevant files
- planner: Create detailed implementation plans
- verifier: Verify changes work correctly
- researcher: Deep research on specific topics
- debugger: Find and fix bugs
- refacto: Improve code quality
- tester: Create comprehensive tests
- general: General purpose delegation
"""

    input_schema = {
        "type": "object",
        "properties": {
            "agent_type": {
                "type": "string",
                "enum": [
                    "explorer",
                    "planner",
                    "verifier",
                    "general",
                    "researcher",
                    "debugger",
                    "refactor",
                    "tester",
                ],
                "description": "Type of specialized agent to spawn",
            },
            "task": {
                "type": "string",
                "description": "Clear description of what the agent should accomplish",
            },
            "context": {
                "type": "string",
                "description": "Additional context the agent needs (file paths, requirements, etc.)",
            },
            "max_iterations": {
                "type": "integer",
                "description": "Maximum iterations for the sub-agent (default: 5)",
                "default": 5,
            },
        },
        "required": ["agent_type", "task"],
    }

    never_parallel = False  # Can run in parallel with other tools

    def __init__(self):
        self._active_agents: dict[str, SubAgent] = {}
        self._results: dict[str, SubAgentResult] = {}

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        # Spawning agents is generally safe, but expensive
        agent_type = arguments.get("agent_type", "general")
        return f"Spawn {agent_type} sub-agent (may use significant tokens)"

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            agent_type_str = arguments["agent_type"]
            task = arguments["task"]
            extra_context = arguments.get("context", "")
            max_iterations = arguments.get("max_iterations", 5)

            # Map string to enum
            try:
                agent_type = AgentType(agent_type_str.lower())
            except ValueError:
                return ToolResult(
                    content=f"Unknown agent type: {agent_type_str}. Available: {[t.value for t in AgentType]}",
                    is_error=True,
                )

            # Create sub-agent
            agent_id = str(uuid.uuid4())[:8]
            sub_agent = SubAgent(
                id=agent_id,
                agent_type=agent_type,
                task=task,
                system_prompt=AGENT_PROMPTS[agent_type],
                created_at=datetime.now(),
                max_iterations=max_iterations,
            )

            self._active_agents[agent_id] = sub_agent
            sub_agent.status = "running"

            # Build the prompt for the sub-agent
            full_prompt = f"""Task: {task}

{extra_context if extra_context else ""}

Work independently to accomplish this task. You have access to the same tools as the main agent.
Be thorough but efficient. Report your findings clearly when done.
"""

            # Execute sub-agent (simplified version - in production this would spawn a real agent)
            # For now, we'll return a structured response indicating what would happen
            result = await self._run_sub_agent(sub_agent, full_prompt, context)

            sub_agent.result = result
            sub_agent.status = result.status
            self._results[agent_id] = result

            # Format output
            duration = (
                (result.completed_at - result.started_at).total_seconds()
                if result.completed_at
                else 0
            )

            content = f"""Sub-agent ({agent_type.value}) completed in {duration:.1f}s
Status: {result.status}

Result:
{result.result}

Agent ID: {agent_id}
"""

            return ToolResult(content=content)

        except Exception as e:
            return ToolResult(content=f"Error spawning agent: {e}", is_error=True)

    async def _run_sub_agent(
        self, agent: SubAgent, prompt: str, context: ToolContext
    ) -> SubAgentResult:
        """Execute a sub-agent task.

        In a full implementation, this would:
        1. Create a new Agent instance
        2. Run it with the specialized system prompt
        3. Collect all events and results
        4. Return the synthesized result

        For now, we return a placeholder indicating the structure.
        """
        started_at = datetime.now()

        # This is where we'd actually run the sub-agent
        # For demonstration, we'll simulate a result
        # In production, this would call the actual Agent.run()

        # Simulate some work
        await asyncio.sleep(0.1)

        result_text = f"""[Sub-agent {agent.agent_type.value} would execute here]

Task: {agent.task}

In a full implementation, this would:
1. Create an Agent instance with the specialized system prompt
2. Run the task with max_iterations={agent.max_iterations}
3. Return the full conversation and results
4. The parent agent would synthesize the sub-agent's work

To implement fully, this tool needs access to:
- Agent class from io_agent
- Model configuration from context
- Tool registry
- Permission context
"""

        completed_at = datetime.now()

        return SubAgentResult(
            agent_id=agent.id,
            agent_type=agent.agent_type,
            task=agent.task,
            result=result_text,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            tool_calls=[],  # Would be populated from actual execution
        )


class MultiAgentTool(Tool):
    """Spawn multiple sub-agents in parallel and aggregate results.

    Useful for tasks that can be broken into independent sub-tasks.
    """

    name = "multi_agent"
    description = """Spawn multiple specialized agents in parallel and aggregate their results.

Use this tool when:
1. A task can be broken into independent sub-tasks
2. You want multiple perspectives on the same problem
3. Different parts of a problem need different expertise
4. You want to parallelize work for efficiency

Example: Refactoring a large module
- Sub-agent 1 (refactor): Refactor the main class
- Sub-agent 2 (tester): Create tests for the refactored code
- Sub-agent 3 (verifier): Verify the changes work

All agents run in parallel, then results are aggregated.
"""

    input_schema = {
        "type": "object",
        "properties": {
            "agents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "agent_type": {
                            "type": "string",
                            "enum": [
                                "explorer",
                                "planner",
                                "verifier",
                                "general",
                                "researcher",
                                "debugger",
                                "refactor",
                                "tester",
                            ],
                        },
                        "task": {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["agent_type", "task"],
                },
                "description": "List of agents to spawn in parallel",
            }
        },
        "required": ["agents"],
    }

    never_parallel = False

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        agents = arguments.get("agents", [])
        return f"Spawn {len(agents)} sub-agents in parallel (high token usage)"

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            agents_config = arguments["agents"]

            if not agents_config:
                return ToolResult(content="No agents specified", is_error=True)

            if len(agents_config) > 5:
                return ToolResult(
                    content="Too many agents (max 5). Spawn fewer agents or use sequential agent tool.",
                    is_error=True,
                )

            # Create AgentTool instances for parallel execution
            agent_tool = AgentTool()

            # Spawn all agents in parallel
            tasks = []
            for config in agents_config:
                task = agent_tool.execute(context, config)
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            content_lines = [f"Multi-agent execution complete ({len(agents_config)} agents)", ""]

            for i, (config, result) in enumerate(zip(agents_config, results), 1):
                content_lines.append(f"--- Agent {i}: {config['agent_type']} ---")
                if isinstance(result, Exception):
                    content_lines.append(f"Error: {result}")
                else:
                    content_lines.append(result.content)
                content_lines.append("")

            content_lines.append("--- Summary ---")
            content_lines.append("Review each agent's results and synthesize the findings.")

            return ToolResult(content="\n".join(content_lines))

        except Exception as e:
            return ToolResult(content=f"Error in multi-agent execution: {e}", is_error=True)


# Export all agent tools
AGENT_TOOLS = [
    AgentTool(),
    MultiAgentTool(),
]
