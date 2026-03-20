"""Agent loop implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any, Awaitable, Callable
from uuid import uuid4

from io_ai import ModelRegistry, stream_simple
from io_ai.types import Usage

from .compressor import ContextCompressor
from .events import AgentEndEvent, AgentStartEvent, CompactionEvent, MessageEvent, ToolCallEndEvent, ToolCallStartEvent, TurnStartEvent
from .tools import GLOBAL_TOOL_REGISTRY, ToolContext, ToolRegistry, ToolsetResolver, execute_tool_batch
from .types import AgentRunResult


BeforeModelCall = Callable[[list[dict[str, Any]]], Awaitable[list[dict[str, Any]]] | list[dict[str, Any]]]
BeforeToolCall = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]
AfterToolResult = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]] | dict[str, Any]]

_DEBUG_LOG_PATH = Path("/Users/ever/Documents/GitHub/io/.cursor/debug-83bc2f.log")
_DEBUG_SESSION_ID = "83bc2f"


def _debug_log(*, run_id: str, hypothesis_id: str, location: str, message: str, data: dict[str, object]) -> None:
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
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


@dataclass
class Agent:
    model_registry: ModelRegistry = field(default_factory=ModelRegistry)
    tool_registry: ToolRegistry = field(default_factory=lambda: GLOBAL_TOOL_REGISTRY)
    toolset_resolver: ToolsetResolver = field(default_factory=ToolsetResolver)
    compressor: ContextCompressor = field(default_factory=ContextCompressor)
    max_iterations: int = 8
    interrupt_requested: bool = False

    async def run(
        self,
        prompt: str,
        *,
        model: str,
        provider: str | None = None,
        base_url: str | None = None,
        cwd: Path | None = None,
        home: Path | None = None,
        toolsets: list[str] | None = None,
        before_model_call: BeforeModelCall | None = None,
        before_tool_call: BeforeToolCall | None = None,
        after_tool_result: AfterToolResult | None = None,
        approval_callback=None,
        session_db=None,
        session_store=None,
        history: list[dict[str, Any]] | None = None,
        env: dict[str, str] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> AgentRunResult:
        final_text = ""
        messages: list[dict[str, Any]] = []
        usage = Usage()
        iterations = 0
        event_counts: dict[str, int] = {}
        async for event in self.run_stream(
            prompt,
            model=model,
            provider=provider,
            base_url=base_url,
            cwd=cwd,
            home=home,
            toolsets=toolsets,
            before_model_call=before_model_call,
            before_tool_call=before_tool_call,
            after_tool_result=after_tool_result,
            approval_callback=approval_callback,
            session_db=session_db,
            session_store=session_store,
            history=history,
            env=env,
        ):
            event_counts[event.type] = event_counts.get(event.type, 0) + 1
            if on_event:
                on_event(event.type, dict(event.payload or {}))
            if event.type in {"turn_start", "tool_call_start", "tool_call_end", "message"}:
                # region agent log
                _debug_log(
                    run_id=str((env or {}).get("IO_DEBUG_RUN_ID") or f"agent-{uuid4().hex[:10]}"),
                    hypothesis_id="H5",
                    location="io_agent/agent.py:run:event",
                    message="Observed agent stream event in run()",
                    data={"event_type": event.type, "count": event_counts[event.type]},
                )
                # endregion
            if event.type == "message":
                final_text = event.payload.get("content", final_text)
            elif event.type == "agent_end":
                usage = event.usage
                messages = event.payload.get("messages", messages)
                iterations = int(event.payload.get("iterations", 0))
        # region agent log
        _debug_log(
            run_id=str((env or {}).get("IO_DEBUG_RUN_ID") or f"agent-{uuid4().hex[:10]}"),
            hypothesis_id="H5",
            location="io_agent/agent.py:run:summary",
            message="Agent run() event summary",
            data={"event_counts": event_counts, "iterations": iterations},
        )
        # endregion
        return AgentRunResult(final_text=final_text, messages=messages, usage=usage, iterations=iterations)

    async def run_stream(
        self,
        prompt: str,
        *,
        model: str,
        provider: str | None = None,
        base_url: str | None = None,
        cwd: Path | None = None,
        home: Path | None = None,
        toolsets: list[str] | None = None,
        before_model_call: BeforeModelCall | None = None,
        before_tool_call: BeforeToolCall | None = None,
        after_tool_result: AfterToolResult | None = None,
        approval_callback=None,
        session_db=None,
        session_store=None,
        history: list[dict[str, Any]] | None = None,
        env: dict[str, str] | None = None,
    ):
        run_id = str((env or {}).get("IO_DEBUG_RUN_ID") or f"agent-{uuid4().hex[:10]}")
        cwd = cwd or Path.cwd()
        home = home or Path.home()
        env = env or {}
        messages = list(history or [])
        messages.append({"role": "user", "content": prompt})
        yield AgentStartEvent(payload={"prompt": prompt, "model": model})

        selected_tool_names = self.toolset_resolver.resolve(toolsets, registry=self.tool_registry)
        tool_schemas = self.tool_registry.schemas(selected_tool_names)
        usage = Usage()

        for iteration in range(1, self.max_iterations + 1):
            if self.interrupt_requested:
                break
            if self.compressor.should_compress(messages):
                compressed = self.compressor.compress(messages)
                if compressed:
                    messages, summary = compressed
                    yield CompactionEvent(payload={"summary": summary})

            prepared_messages = messages
            if before_model_call:
                maybe_messages = before_model_call(list(messages))
                prepared_messages = await maybe_messages if hasattr(maybe_messages, "__await__") else maybe_messages

            yield TurnStartEvent(payload={"iteration": iteration})
            # region agent log
            _debug_log(
                run_id=run_id,
                hypothesis_id="H3",
                location="io_agent/agent.py:run_stream:turn_start",
                message="Agent turn started, awaiting model response",
                data={"iteration": iteration, "messages_len": len(prepared_messages)},
            )
            # endregion
            response = await stream_simple(
                prepared_messages,
                model=model,
                provider=provider,
                base_url=base_url,
                tools=tool_schemas,
                registry=self.model_registry,
            )
            usage = response.usage
            assistant_message = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in response.tool_calls
                ],
            }
            messages.append(assistant_message)
            if response.content:
                yield MessageEvent(payload={"content": response.content, "iteration": iteration})

            if not response.tool_calls:
                break

            batch = []
            for tool_call in response.tool_calls:
                # region agent log
                _debug_log(
                    run_id=run_id,
                    hypothesis_id="H7",
                    location="io_agent/agent.py:run_stream:tool_call_arguments_before_dict",
                    message="Normalizing tool_call.arguments",
                    data={
                        "tool_name": tool_call.name,
                        "arguments_type": type(tool_call.arguments).__name__,
                        "arguments_preview": str(tool_call.arguments)[:220],
                    },
                )
                # endregion
                arguments = dict(tool_call.arguments)
                if before_tool_call:
                    decision = before_tool_call(tool_call.name, arguments)
                    resolved = await decision if hasattr(decision, "__await__") else decision
                    if resolved.get("block"):
                        tool_result = {"role": "tool", "name": tool_call.name, "tool_call_id": tool_call.id, "content": resolved.get("reason", "blocked")}
                        messages.append(tool_result)
                        yield ToolCallEndEvent(
                            payload={"tool": tool_call.name, "blocked": True},
                            result=type("Result", (), {"content": tool_result["content"], "is_error": True, "metadata": {}})(),
                        )
                        continue
                    arguments = resolved.get("arguments", arguments)
                yield ToolCallStartEvent(payload={"tool": tool_call.name, "arguments": arguments})
                batch.append((self.tool_registry.get(tool_call.name), arguments, tool_call.id))

            if not batch:
                continue

            context = ToolContext(
                cwd=cwd,
                home=home,
                env=env,
                session_db=session_db,
                session_store=session_store,
                approval_callback=approval_callback,
            )
            results = await execute_tool_batch(batch, context=context)
            for call_id, result in results:
                tool_name = next(item[0].name for item in batch if item[2] == call_id)
                payload = {
                    "role": "tool",
                    "name": tool_name,
                    "tool_call_id": call_id,
                    "content": result.content,
                }
                if after_tool_result:
                    patch = after_tool_result(tool_name, payload)
                    payload = await patch if hasattr(patch, "__await__") else patch
                messages.append(payload)
                yield ToolCallEndEvent(payload={"tool": tool_name, "content": payload["content"]}, result=result)

        yield AgentEndEvent(payload={"messages": messages, "iterations": iteration}, usage=usage)

