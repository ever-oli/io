"""Core types for the IO AI runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


ThinkingLevel = Literal["off", "low", "medium", "high", "xhigh"]
AssistantEventType = Literal[
    "message_start",
    "message_delta",
    "message_end",
    "tool_call",
    "usage",
    "error",
]


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
            + self.reasoning_tokens
        )


@dataclass(slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelRef:
    id: str
    provider: str
    api: str
    remote_id: str
    label: str = ""
    base_url: str | None = None
    supports_tools: bool = True
    supports_streaming: bool = True
    reasoning_levels: tuple[ThinkingLevel, ...] = ("off", "low", "medium", "high", "xhigh")
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompletionRequest:
    model: ModelRef
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AssistantResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AssistantEvent:
    type: AssistantEventType
    text: str = ""
    response: AssistantResponse | None = None
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    error: str | None = None

