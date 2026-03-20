"""Minimal OpenAI Responses API provider."""

from __future__ import annotations

from typing import Any

import httpx

from io_ai.types import AssistantResponse, CompletionRequest, ToolCall, Usage

from .base import Provider


def _message_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if isinstance(content, list):
            text = "\n".join(item.get("text", "") for item in content if item.get("type") == "text")
        else:
            text = str(content)
        payload.append({"role": role, "content": text})
    return payload


class OpenAIResponsesProvider(Provider):
    name = "openai"

    async def complete(self, request: CompletionRequest) -> AssistantResponse:
        base_url = request.model.base_url or request.settings.get("base_url") or "https://api.openai.com/v1"
        headers = {"Content-Type": "application/json", **request.headers}
        body: dict[str, Any] = {
            "model": request.model.remote_id,
            "input": _message_input(request.messages),
        }
        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
                }
                for tool in request.tools
            ]
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{base_url.rstrip('/')}/responses", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()

        usage_payload = payload.get("usage", {})
        usage = Usage(
            input_tokens=int(usage_payload.get("input_tokens", 0)),
            output_tokens=int(usage_payload.get("output_tokens", 0)),
            reasoning_tokens=int(usage_payload.get("reasoning_tokens", 0)),
        )

        text_fragments: list[str] = []
        tool_calls: list[ToolCall] = []
        for item in payload.get("output", []):
            item_type = item.get("type")
            if item_type == "message":
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        text_fragments.append(content.get("text", ""))
            elif item_type == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=item.get("call_id", item.get("id", "call")),
                        name=item.get("name", ""),
                        arguments=item.get("arguments", {}),
                    )
                )
        if not text_fragments and payload.get("output_text"):
            text_fragments.append(str(payload["output_text"]))
        return AssistantResponse(
            content="\n".join(fragment for fragment in text_fragments if fragment).strip(),
            tool_calls=tool_calls,
            usage=usage,
            provider=request.model.provider,
            model=request.model.id,
            raw=payload,
        )

