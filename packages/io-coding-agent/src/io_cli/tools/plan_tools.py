"""PlanTool - Agent-accessible tool for creating and managing plans.

This tool allows the AI agent to:
1. Create structured plans with steps
2. Get current plan status
3. Mark steps as complete
4. Query plan progress

Integrates with the PlanManager for persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult

from .plan_manager import PlanManager, PlanStepStatus


class PlanCreateTool(Tool):
    """Create a new structured plan."""

    name = "plan_create"
    description = "Create a structured plan with steps to accomplish a task"
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title for the plan"},
            "description": {
                "type": "string",
                "description": "Detailed description of what the plan accomplishes",
            },
            "steps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of step descriptions in order",
            },
        },
        "required": ["title", "steps"],
    }

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None  # Creating plans is always safe

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            title = arguments["title"]
            description = arguments.get("description", "")
            steps = arguments["steps"]

            if not steps:
                return ToolResult(content="Error: At least one step is required", is_error=True)

            plan_mgr = PlanManager(home=context.home)
            plan = plan_mgr.create_plan(title, description, steps)
            plan_mgr.set_active_plan(plan)

            content = f"""Created plan: {plan.title}
ID: {plan.id}
Steps: {len(plan.steps)}

Plan steps:
"""
            for i, step in enumerate(plan.steps, 1):
                content += f"{i}. {step.description}\n"

            content += f"\nUse plan_get_current_step to check progress or plan_mark_step_complete after finishing each step."

            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error creating plan: {e}", is_error=True)


class PlanGetCurrentStepTool(Tool):
    """Get the current step of the active plan."""

    name = "plan_get_current_step"
    description = "Get information about the current step to execute in the active plan"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            plan_mgr = PlanManager(home=context.home)
            plan = plan_mgr.get_active_plan()

            if not plan:
                return ToolResult(
                    content="No active plan. Create one with plan_create first.", is_error=True
                )

            step = plan.get_current_step()
            if not step:
                return ToolResult(
                    content=f"Plan '{plan.title}' is complete! All {len(plan.steps)} steps finished."
                )

            content = f"""Plan: {plan.title}
Progress: {plan.progress_percentage():.0f}% ({len(plan.get_completed_steps())}/{len(plan.steps)} steps)

Current step ({plan.current_step_index + 1}/{len(plan.steps)}):
{step.description}

Execute this step, then use plan_mark_step_complete to mark it done and move to the next step."""

            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error getting current step: {e}", is_error=True)


class PlanMarkStepCompleteTool(Tool):
    """Mark the current step as complete and advance to next."""

    name = "plan_mark_step_complete"
    description = "Mark the current plan step as completed and advance to the next step"
    input_schema = {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": "Summary of what was accomplished in this step",
            }
        },
        "required": [],
    }

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            plan_mgr = PlanManager(home=context.home)
            plan = plan_mgr.get_active_plan()

            if not plan:
                return ToolResult(content="No active plan.", is_error=True)

            current = plan.get_current_step()
            if not current:
                return ToolResult(content=f"Plan '{plan.title}' is already complete!")

            result = arguments.get("result", "Step completed successfully")

            # Update current step
            plan_mgr.update_step_status(plan.id, current.id, PlanStepStatus.COMPLETED, result)

            # Advance to next
            plan = plan_mgr.advance_to_next_step(plan.id)

            content = f"✓ Marked step {plan.current_step_index} as complete: {current.description[:50]}...\n"

            if plan and plan.get_current_step():
                next_step = plan.get_current_step()
                content += f"\nNext step ({plan.current_step_index + 1}/{len(plan.steps)}):\n{next_step.description}"
            else:
                content += f"\n🎉 Plan '{plan.title}' is now complete!"

            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error marking step complete: {e}", is_error=True)


class PlanGetStatusTool(Tool):
    """Get overall status of the active plan."""

    name = "plan_get_status"
    description = "Get the overall status and progress of the active plan"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            plan_mgr = PlanManager(home=context.home)
            plan = plan_mgr.get_active_plan()

            if not plan:
                return ToolResult(content="No active plan.", is_error=True)

            content = plan_mgr.format_plan(plan, show_all_steps=True)
            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error getting plan status: {e}", is_error=True)


class PlanListTool(Tool):
    """List all plans."""

    name = "plan_list"
    description = "List all available plans"
    input_schema = {"type": "object", "properties": {}, "required": []}

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        try:
            plan_mgr = PlanManager(home=context.home)
            plans = plan_mgr.list_plans()

            if not plans:
                return ToolResult(content="No plans found. Create one with plan_create.")

            content = "Available plans:\n\n"
            for p in plans:
                status_icon = (
                    "✓" if p.status == "completed" else "◐" if p.status == "active" else "✗"
                )
                content += f"{status_icon} {p.title} ({p.progress_percentage():.0f}%) - {p.id}\n"
                content += f"   {p.description[:80]}...\n\n"

            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(content=f"Error listing plans: {e}", is_error=True)


# Export all plan tools
PLAN_TOOLS = [
    PlanCreateTool(),
    PlanGetCurrentStepTool(),
    PlanMarkStepCompleteTool(),
    PlanGetStatusTool(),
    PlanListTool(),
]
