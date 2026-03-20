"""Shared agent-core types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from io_ai.types import ToolCall, Usage


@dataclass(slots=True)
class AgentMessage:
    role: str
    content: Any
    tool_calls: list[ToolCall] = field(default_factory=list)
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [
                {"id": call.id, "name": call.name, "arguments": call.arguments} for call in self.tool_calls
            ]
        if self.name:
            payload["name"] = self.name
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        payload.update(self.metadata)
        return payload


@dataclass(slots=True)
class ToolResult:
    content: str
    is_error: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


ApprovalCallback = Callable[[str, dict[str, Any], str], bool]


@dataclass(slots=True)
class SessionConfig:
    cwd: Path
    home: Path
    model: str
    provider: str | None = None
    max_iterations: int = 8


@dataclass(slots=True)
class AgentRunResult:
    final_text: str
    messages: list[dict[str, Any]]
    usage: Usage = field(default_factory=Usage)
    iterations: int = 0

