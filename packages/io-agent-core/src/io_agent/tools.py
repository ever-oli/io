"""Tool contracts, registry, and toolset resolution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .types import ApprovalCallback, ToolResult

# (tool_name, stream_name "stdout"|"stderr", text_chunk)
ToolOutputCallback = Callable[[str, str, str], None]


@dataclass(slots=True)
class ToolContext:
    cwd: Path
    home: Path
    env: dict[str, str] = field(default_factory=dict)
    session_db: Any = None
    session_store: Any = None
    approval_callback: ApprovalCallback | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_output_callback: ToolOutputCallback | None = None
    permission_context: Any | None = None  # PermissionContext for granular controls


class Tool:
    name = "tool"
    description = ""
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    never_parallel = False

    def to_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def approval_reason(self, arguments: dict[str, Any]) -> str | None:
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> Tool:
        self.tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool:
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        return self.tools[name]

    def names(self) -> list[str]:
        return sorted(self.tools)

    def schemas(self, selected: set[str] | None = None) -> list[dict[str, Any]]:
        if selected is None:
            selected = set(self.tools)
        return [self.tools[name].to_schema() for name in sorted(selected) if name in self.tools]


GLOBAL_TOOL_REGISTRY = ToolRegistry()


@dataclass
class ToolsetResolver:
    toolsets: dict[str, set[str]] = field(default_factory=dict)

    def resolve(
        self, requested: list[str] | None, *, registry: ToolRegistry | None = None
    ) -> set[str]:
        registry = registry or GLOBAL_TOOL_REGISTRY
        if not requested:
            return set(registry.tools)
        resolved: set[str] = set()
        for item in requested:
            if item in self.toolsets:
                resolved.update(self.toolsets[item])
            elif item in registry.tools:
                resolved.add(item)
        return resolved


async def execute_tool_batch(
    tool_calls: list[tuple[Tool, dict[str, Any], str]],
    *,
    context: ToolContext,
) -> list[tuple[str, ToolResult]]:
    async def _run(tool: Tool, arguments: dict[str, Any], call_id: str) -> tuple[str, ToolResult]:
        # Check granular permissions if available (Claudetenks fusion)
        if context.permission_context is not None:
            try:
                tool_reason = tool.approval_reason(arguments)
                action, reason = context.permission_context.check_permission(
                    tool.name, arguments, tool_reason
                )
                if action == "deny":
                    return call_id, ToolResult(
                        content=f"Permission denied: {reason or tool.name}", is_error=True
                    )
                if action == "prompt" and context.approval_callback:
                    if not context.approval_callback(
                        tool.name, arguments, reason or f"{tool.name} requires approval"
                    ):
                        return call_id, ToolResult(
                            content=f"Approval denied for {tool.name}", is_error=True
                        )
            except Exception:
                pass  # Fall back to standard approval

        # Standard approval flow
        reason = tool.approval_reason(arguments)
        if (
            reason
            and context.approval_callback
            and not context.approval_callback(tool.name, arguments, reason)
        ):
            return call_id, ToolResult(content=reason, is_error=True)
        return call_id, await tool.execute(context, arguments)

    if any(tool.never_parallel for tool, _, _ in tool_calls):
        results = []
        for tool, arguments, call_id in tool_calls:
            results.append(await _run(tool, arguments, call_id))
        return results
    return list(
        await asyncio.gather(
            *(_run(tool, arguments, call_id) for tool, arguments, call_id in tool_calls)
        )
    )
