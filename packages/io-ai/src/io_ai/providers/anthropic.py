"""Minimal Anthropic Messages API provider."""

from __future__ import annotations

from typing import Any

import httpx

from io_ai.types import AssistantResponse, CompletionRequest, ToolCall, Usage

from .base import Provider


class AnthropicProvider(Provider):
    name = "anthropic"

    async def complete(self, request: CompletionRequest) -> AssistantResponse:
        base_url = request.model.base_url or request.settings.get("base_url") or "https://api.anthropic.com/v1"
        headers = {"Content-Type": "application/json", **request.headers}
        messages = []
        system_prompt = ""
        for message in request.messages:
            if message.get("role") in {"system", "developer"}:
                system_prompt += f"{message.get('content', '')}\n"
                continue
            messages.append({"role": message.get("role", "user"), "content": str(message.get("content", ""))})
        body: dict[str, Any] = {
            "model": request.model.remote_id,
            "max_tokens": int(request.settings.get("max_tokens", 1024)),
            "messages": messages,
        }
        if system_prompt.strip():
            body["system"] = system_prompt.strip()
        if request.tools:
            body["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
                }
                for tool in request.tools
            ]
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{base_url.rstrip('/')}/messages", headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()

        text_fragments: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in payload.get("content", []):
            block_type = block.get("type")
            if block_type == "text":
                text_fragments.append(block.get("text", ""))
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", "tool_call"),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )
        usage_payload = payload.get("usage", {})
        usage = Usage(
            input_tokens=int(usage_payload.get("input_tokens", 0)),
            output_tokens=int(usage_payload.get("output_tokens", 0)),
        )
        return AssistantResponse(
            content="\n".join(fragment for fragment in text_fragments if fragment).strip(),
            tool_calls=tool_calls,
            usage=usage,
            provider=request.model.provider,
            model=request.model.id,
            raw=payload,
        )

