"""Provider interfaces and helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from io_ai.types import AssistantEvent, AssistantResponse, CompletionRequest


class Provider(ABC):
    name = "provider"

    @abstractmethod
    async def complete(self, request: CompletionRequest) -> AssistantResponse:
        raise NotImplementedError

    async def stream(self, request: CompletionRequest):
        response = await self.complete(request)
        yield AssistantEvent(type="message_start")
        if response.content:
            yield AssistantEvent(type="message_delta", text=response.content)
        for tool_call in response.tool_calls:
            yield AssistantEvent(type="tool_call", tool_call=tool_call)
        yield AssistantEvent(type="usage", usage=response.usage)
        yield AssistantEvent(type="message_end", response=response)

    @staticmethod
    def last_user_text(messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                content = message.get("content", "")
                if isinstance(content, list):
                    fragments = [item.get("text", "") for item in content if item.get("type") == "text"]
                    return "\n".join(fragment for fragment in fragments if fragment)
                return str(content)
        return ""

