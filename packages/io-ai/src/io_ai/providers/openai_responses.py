"""Minimal OpenAI Responses API provider."""

from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

import httpx

from io_ai.types import AssistantResponse, CompletionRequest, ToolCall, Usage

from .base import Provider

_DEBUG_LOG_PATH = "/Users/ever/Documents/GitHub/io/.cursor/debug-83bc2f.log"
_DEBUG_SESSION_ID = "83bc2f"


def _debug_log(*, run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    try:
        payload = {
            "sessionId": _DEBUG_SESSION_ID,
            "id": f"log_{uuid4().hex}",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


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


def _openrouter_input(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role", "user") or "user").strip()
        content = message.get("content", "")
        if isinstance(content, list):
            text = "\n".join(str(item.get("text", "")) for item in content if item.get("type") == "text")
        else:
            text = str(content)
        text = text.strip()
        if not text:
            continue
        parts.append(f"{role}: {text}")
    return "\n\n".join(parts).strip()


class OpenAIResponsesProvider(Provider):
    name = "openai"

    async def complete(self, request: CompletionRequest) -> AssistantResponse:
        run_id = str((request.settings or {}).get("io_debug_run_id") or f"provider-{uuid4().hex[:10]}")
        base_url = request.model.base_url or request.settings.get("base_url") or "https://api.openai.com/v1"
        headers = {"Content-Type": "application/json", **request.headers}
        body: dict[str, Any] = {
            "model": request.model.remote_id,
            "input": _message_input(request.messages),
        }
        if "openrouter.ai" in base_url.lower():
            body["input"] = _openrouter_input(request.messages)
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
                raw_arguments = item.get("arguments", {})
                normalized_arguments: dict[str, Any]
                if isinstance(raw_arguments, dict):
                    normalized_arguments = raw_arguments
                elif isinstance(raw_arguments, str):
                    try:
                        decoded = json.loads(raw_arguments)
                        normalized_arguments = decoded if isinstance(decoded, dict) else {}
                    except json.JSONDecodeError:
                        normalized_arguments = {}
                else:
                    normalized_arguments = {}
                _debug_log(
                    run_id=run_id,
                    hypothesis_id="H6",
                    location="io_ai/providers/openai_responses.py:tool_call_parse",
                    message="Parsed function_call arguments payload",
                    data={
                        "name": str(item.get("name", "")),
                        "arguments_type": type(raw_arguments).__name__,
                        "arguments_preview": str(raw_arguments)[:220],
                    },
                )
                tool_calls.append(
                    ToolCall(
                        id=item.get("call_id", item.get("id", "call")),
                        name=item.get("name", ""),
                        arguments=normalized_arguments,
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

