"""Deterministic provider for tests and offline development."""

from __future__ import annotations

import json
import re
from itertools import count

from io_ai.types import AssistantResponse, CompletionRequest, ToolCall, Usage

from .base import Provider


TOOL_DIRECTIVE = re.compile(r"TOOL\[(?P<name>[^\]]+)\](?:\s+(?P<args>\{.*\}))?$", re.DOTALL)


class MockProvider(Provider):
    name = "mock"

    def __init__(self) -> None:
        self._ids = count(1)

    async def complete(self, request: CompletionRequest) -> AssistantResponse:
        usage = Usage(input_tokens=sum(len(str(message.get("content", ""))) for message in request.messages))
        if request.messages and request.messages[-1].get("role") == "tool":
            tool_name = request.messages[-1].get("name", "tool")
            content = request.messages[-1].get("content", "")
            response = AssistantResponse(
                content=f"{tool_name} completed successfully.\n{content}".strip(),
                usage=usage,
                provider=self.name,
                model=request.model.id,
            )
            response.usage.output_tokens = len(response.content)
            return response

        text = self.last_user_text(request.messages).strip()
        available_tools = {tool["name"] for tool in request.tools}
        directive = TOOL_DIRECTIVE.match(text)
        if directive and directive.group("name") in available_tools:
            raw_args = directive.group("args")
            arguments = json.loads(raw_args) if raw_args else {}
            return AssistantResponse(
                tool_calls=[
                    ToolCall(
                        id=f"call_{next(self._ids):04d}",
                        name=directive.group("name"),
                        arguments=arguments,
                    )
                ],
                usage=usage,
                provider=self.name,
                model=request.model.id,
            )

        heuristics = {
            "list files": ("ls", {"path": "."}),
            "remember ": ("memory", {"action": "save_note", "content": text.partition("remember ")[2]}),
            "search session ": (
                "session_search",
                {"query": text.partition("search session ")[2], "limit": 5},
            ),
        }
        lowered = text.lower()
        for snippet, (tool_name, arguments) in heuristics.items():
            if snippet in lowered and tool_name in available_tools:
                return AssistantResponse(
                    tool_calls=[ToolCall(id=f"call_{next(self._ids):04d}", name=tool_name, arguments=arguments)],
                    usage=usage,
                    provider=self.name,
                    model=request.model.id,
                )

        content = f"Mock response: {text}" if text else "Mock response."
        response = AssistantResponse(content=content, usage=usage, provider=self.name, model=request.model.id)
        response.usage.output_tokens = len(content)
        return response

