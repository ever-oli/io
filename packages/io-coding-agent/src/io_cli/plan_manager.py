"""Plan Mode - Structured step-by-step planning system.

Fuses Claude Code's Plan Mode into IO:
- Create structured plans with explicit steps
- Step-by-step execution with user confirmation
- Plan editing and modification
- Persistence across sessions
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class PlanStepStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class PlanStep:
    """A single step in a plan."""

    id: str
    description: str
    status: PlanStepStatus = PlanStepStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: datetime | None = None
    result: str = ""  # Result/output from executing this step
    depends_on: list[str] = field(default_factory=list)  # Step IDs this depends on

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "depends_on": self.depends_on,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(
            id=data["id"],
            description=data["description"],
            status=PlanStepStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"])
            if data.get("completed_at")
            else None,
            result=data.get("result", ""),
            depends_on=data.get("depends_on", []),
        )


@dataclass
class Plan:
    """A structured plan with steps."""

    id: str
    title: str
    description: str
    steps: list[PlanStep]
    created_at: datetime
    updated_at: datetime
    status: str = "active"  # active, completed, cancelled, failed
    current_step_index: int = 0
    # Claw-code parity additions
    context: dict[str, Any] = field(default_factory=dict)  # Additional plan context
    mode: str = "normal"  # normal, review, auto
    auto_confirm: bool = False  # Auto-confirm steps without user intervention
    created_by: str = "user"  # user, agent, system
    tags: list[str] = field(default_factory=list)  # Plan tags for categorization

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "status": self.status,
            "current_step_index": self.current_step_index,
            "context": self.context,
            "mode": self.mode,
            "auto_confirm": self.auto_confirm,
            "created_by": self.created_by,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            steps=[PlanStep.from_dict(s) for s in data.get("steps", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            status=data.get("status", "active"),
            current_step_index=data.get("current_step_index", 0),
            context=data.get("context", {}),
            mode=data.get("mode", "normal"),
            auto_confirm=data.get("auto_confirm", False),
            created_by=data.get("created_by", "user"),
            tags=data.get("tags", []),
        )

    def get_current_step(self) -> PlanStep | None:
        """Get the current step to execute."""
        if self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None

    def get_pending_steps(self) -> list[PlanStep]:
        """Get all pending steps."""
        return [s for s in self.steps if s.status == PlanStepStatus.PENDING]

    def get_completed_steps(self) -> list[PlanStep]:
        """Get all completed steps."""
        return [s for s in self.steps if s.status == PlanStepStatus.COMPLETED]

    def progress_percentage(self) -> float:
        """Calculate completion percentage."""
        if not self.steps:
            return 100.0
        completed = len(self.get_completed_steps())
        return (completed / len(self.steps)) * 100

    def can_execute_step(self, step: PlanStep) -> bool:
        """Check if a step can be executed (dependencies satisfied)."""
        if step.status != PlanStepStatus.PENDING:
            return False
        for dep_id in step.depends_on:
            dep_step = next((s for s in self.steps if s.id == dep_id), None)
            if not dep_step or dep_step.status != PlanStepStatus.COMPLETED:
                return False
        return True


class PlanManager:
    """Manager for plans with persistence."""

    def __init__(self, home: Path):
        self.home = home
        self.plans_dir = home / "plans"
        self.plans_dir.mkdir(parents=True, exist_ok=True)
        self._active_plan: Plan | None = None

    def create_plan(self, title: str, description: str, steps: list[str]) -> Plan:
        """Create a new plan from step descriptions."""
        plan_steps = [
            PlanStep(id=str(uuid.uuid4())[:8], description=step_desc) for step_desc in steps
        ]

        plan = Plan(
            id=str(uuid.uuid4())[:12],
            title=title,
            description=description,
            steps=plan_steps,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self._save_plan(plan)
        self._active_plan = plan
        return plan

    def _save_plan(self, plan: Plan) -> None:
        """Save a plan to disk."""
        plan_path = self.plans_dir / f"{plan.id}.json"
        plan_path.write_text(json.dumps(plan.to_dict(), indent=2))

    def load_plan(self, plan_id: str) -> Plan | None:
        """Load a plan by ID."""
        plan_path = self.plans_dir / f"{plan_id}.json"
        if plan_path.exists():
            data = json.loads(plan_path.read_text())
            return Plan.from_dict(data)
        return None

    def list_plans(self) -> list[Plan]:
        """List all plans."""
        plans = []
        for plan_file in self.plans_dir.glob("*.json"):
            try:
                data = json.loads(plan_file.read_text())
                plans.append(Plan.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(plans, key=lambda p: p.created_at, reverse=True)

    def get_active_plan(self) -> Plan | None:
        """Get the currently active plan."""
        return self._active_plan

    def set_active_plan(self, plan: Plan | None) -> None:
        """Set the active plan."""
        self._active_plan = plan

    def update_step_status(
        self, plan_id: str, step_id: str, status: PlanStepStatus, result: str = ""
    ) -> Plan | None:
        """Update a step's status."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        for step in plan.steps:
            if step.id == step_id:
                step.status = status
                if status == PlanStepStatus.COMPLETED:
                    step.completed_at = datetime.now()
                if result:
                    step.result = result
                break

        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = plan

        return plan

    def advance_to_next_step(self, plan_id: str) -> Plan | None:
        """Advance plan to next step."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        # Mark current step as completed if in progress
        current = plan.get_current_step()
        if current and current.status == PlanStepStatus.IN_PROGRESS:
            current.status = PlanStepStatus.COMPLETED
            current.completed_at = datetime.now()

        # Find next executable step
        for i, step in enumerate(plan.steps):
            if step.status == PlanStepStatus.PENDING and plan.can_execute_step(step):
                plan.current_step_index = i
                step.status = PlanStepStatus.IN_PROGRESS
                break
        else:
            # No more pending steps
            plan.status = "completed"

        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = plan

        return plan

    def edit_step(self, plan_id: str, step_id: str, new_description: str) -> Plan | None:
        """Edit a step's description."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        for step in plan.steps:
            if step.id == step_id:
                step.description = new_description
                break

        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = plan

        return plan

    def add_step(
        self, plan_id: str, description: str, after_step_id: str | None = None
    ) -> Plan | None:
        """Add a new step to a plan."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        new_step = PlanStep(id=str(uuid.uuid4())[:8], description=description)

        if after_step_id:
            # Insert after specific step
            for i, step in enumerate(plan.steps):
                if step.id == after_step_id:
                    plan.steps.insert(i + 1, new_step)
                    break
            else:
                plan.steps.append(new_step)
        else:
            plan.steps.append(new_step)

        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = plan

        return plan

    def delete_step(self, plan_id: str, step_id: str) -> Plan | None:
        """Delete a step from a plan."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        plan.steps = [s for s in plan.steps if s.id != step_id]

        # Adjust current index if needed
        if plan.current_step_index >= len(plan.steps):
            plan.current_step_index = max(0, len(plan.steps) - 1)

        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = plan

        return plan

    def cancel_plan(self, plan_id: str) -> Plan | None:
        """Cancel a plan."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        plan.status = "cancelled"
        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = None

        return plan

    def delete_plan(self, plan_id: str) -> bool:
        """Delete a plan permanently."""
        plan_path = self.plans_dir / f"{plan_id}.json"
        if plan_path.exists():
            plan_path.unlink()
            if self._active_plan and self._active_plan.id == plan_id:
                self._active_plan = None
            return True
        return False

    def reorder_steps(self, plan_id: str, step_order: list[str]) -> Plan | None:
        """Reorder steps in a plan by their IDs."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        # Create mapping of id to step
        step_map = {s.id: s for s in plan.steps}

        # Rebuild steps list in new order
        new_steps = []
        for step_id in step_order:
            if step_id in step_map:
                new_steps.append(step_map[step_id])

        # Add any missing steps at the end
        for step in plan.steps:
            if step.id not in step_order:
                new_steps.append(step)

        plan.steps = new_steps
        plan.updated_at = datetime.now()
        self._save_plan(plan)

        if self._active_plan and self._active_plan.id == plan_id:
            self._active_plan = plan

        return plan

    def duplicate_plan(self, plan_id: str, new_title: str | None = None) -> Plan | None:
        """Duplicate an existing plan."""
        plan = self.load_plan(plan_id)
        if not plan:
            return None

        # Create new plan with copied steps
        steps = [s.description for s in plan.steps]
        new_plan = self.create_plan(
            title=new_title or f"{plan.title} (Copy)", description=plan.description, steps=steps
        )

        # Copy additional metadata
        new_plan.context = plan.context.copy()
        new_plan.tags = plan.tags.copy()
        new_plan.mode = plan.mode
        self._save_plan(new_plan)

        return new_plan

    def search_plans(self, query: str) -> list[Plan]:
        """Search plans by title, description, or tags."""
        all_plans = self.list_plans()
        query_lower = query.lower()

        matching = []
        for plan in all_plans:
            if (
                query_lower in plan.title.lower()
                or query_lower in plan.description.lower()
                or any(query_lower in tag.lower() for tag in plan.tags)
            ):
                matching.append(plan)

        return matching

    def get_plan_stats(self) -> dict[str, Any]:
        """Get statistics about all plans."""
        plans = self.list_plans()

        total = len(plans)
        active = len([p for p in plans if p.status == "active"])
        completed = len([p for p in plans if p.status == "completed"])
        cancelled = len([p for p in plans if p.status == "cancelled"])

        total_steps = sum(len(p.steps) for p in plans)
        completed_steps = sum(
            len([s for s in p.steps if s.status == PlanStepStatus.COMPLETED]) for p in plans
        )

        return {
            "total_plans": total,
            "active_plans": active,
            "completed_plans": completed,
            "cancelled_plans": cancelled,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "completion_rate": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
        }

    def format_plan(self, plan: Plan, show_all_steps: bool = True) -> str:
        """Format a plan for display."""
        lines = [
            f"📋 Plan: {plan.title}",
            f"   ID: {plan.id}",
            f"   Status: {plan.status}",
            f"   Progress: {plan.progress_percentage():.0f}%",
            "",
            f"   {plan.description}",
            "",
            "   Steps:",
        ]

        for i, step in enumerate(plan.steps, 1):
            status_icon = {
                PlanStepStatus.PENDING: "○",
                PlanStepStatus.IN_PROGRESS: "◐",
                PlanStepStatus.COMPLETED: "✓",
                PlanStepStatus.SKIPPED: "⊘",
                PlanStepStatus.FAILED: "✗",
            }.get(step.status, "○")

            current_marker = " →" if i - 1 == plan.current_step_index else "  "
            lines.append(f"{current_marker} {status_icon} {i}. {step.description}")

            if step.result and show_all_steps:
                result_preview = step.result[:100].replace("\n", " ")
                if len(step.result) > 100:
                    result_preview += "..."
                lines.append(f"      Result: {result_preview}")

        return "\n".join(lines)
