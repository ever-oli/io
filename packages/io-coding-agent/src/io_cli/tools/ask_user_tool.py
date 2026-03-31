"""AskUserQuestionTool - Interactive user prompts.

Allows the agent to ask clarifying questions and wait for user input.
"""

from __future__ import annotations

from typing import Any

from io_agent import Tool, ToolContext, ToolResult


class AskUserQuestionTool(Tool):
    """Ask the user a question and wait for their response.

    Use this when you need clarification, confirmation, or additional
    information from the user to proceed with a task.
    """

    name = "ask_user"
    description = "Ask the user a clarifying question and wait for their response. Use when you need more information or confirmation to proceed."

    async def execute(
        self,
        question: str,
        options: list[str] | None = None,
        default: str | None = None,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Ask the user a question.

        Args:
            question: The question to ask the user
            options: Optional list of choices for the user
            default: Default value if user provides no input
            context: Tool execution context
        """
        # Format the question
        lines = ["❓ Question from the agent:", "", question]

        if options:
            lines.append("")
            lines.append("Options:")
            for i, option in enumerate(options, 1):
                marker = " (default)" if option == default else ""
                lines.append(f"  {i}. {option}{marker}")

        if default and not options:
            lines.append(f"\n[Press Enter for default: {default}]")

        formatted_question = "\n".join(lines)

        # Return the question and expect the user to respond
        return ToolResult(
            content=formatted_question,
            data={
                "question": question,
                "options": options,
                "default": default,
                "requires_input": True,
            },
        )
