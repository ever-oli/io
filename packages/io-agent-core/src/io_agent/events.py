"""Agent event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from io_ai.types import Usage

from .types import ToolResult


@dataclass(slots=True)
class AgentEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentStartEvent(AgentEvent):
    type: str = "agent_start"


@dataclass(slots=True)
class TurnStartEvent(AgentEvent):
    type: str = "turn_start"


@dataclass(slots=True)
class ToolCallStartEvent(AgentEvent):
    type: str = "tool_call_start"


@dataclass(slots=True)
class ToolCallEndEvent(AgentEvent):
    result: ToolResult | None = None
    type: str = "tool_call_end"


@dataclass(slots=True)
class MessageEvent(AgentEvent):
    type: str = "message"


@dataclass(slots=True)
class MessageDeltaEvent(AgentEvent):
    type: str = "message_delta"


@dataclass(slots=True)
class ToolOutputDeltaEvent(AgentEvent):
    type: str = "tool_output_delta"


@dataclass(slots=True)
class CompactionEvent(AgentEvent):
    type: str = "context_compacted"


@dataclass(slots=True)
class AgentEndEvent(AgentEvent):
    usage: Usage = field(default_factory=Usage)
    type: str = "agent_end"

