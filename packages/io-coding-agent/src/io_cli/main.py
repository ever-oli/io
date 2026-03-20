"""Main orchestration for the IO CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from io_agent import Agent, ContextCompressor, SessionDB, resolve_runtime

from .config import ensure_io_home, load_config, load_env, load_soul, memory_snapshot
from .extensions import ExtensionRunner
from .session import SessionManager
from .skin_engine import SkinEngine
from .toolsets import build_toolset_resolver
from .tools import get_tool_registry


@dataclass(slots=True)
class PromptResult:
    text: str
    model: str
    provider: str | None
    session_path: Path
    messages: list[dict[str, Any]]
    loaded_extensions: list[str]


def _default_approval_callback(_tool_name: str, _arguments: dict[str, Any], _reason: str) -> bool:
    return os.getenv("IO_AUTO_APPROVE_DANGEROUS", "0") == "1"


async def run_prompt(
    prompt: str,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    toolsets: list[str] | None = None,
    session_path: Path | None = None,
    load_extensions: bool = True,
) -> PromptResult:
    cwd = (cwd or Path.cwd()).resolve()
    home = ensure_io_home(home)
    config = load_config(home)
    env = {**load_env(home), **os.environ}
    runtime = resolve_runtime(
        cli_model=model,
        cli_provider=provider,
        cli_base_url=base_url,
        config=config,
        env=env,
        home=home,
    )

    session_manager = SessionManager.open(session_path) if session_path else SessionManager.continue_recent(cwd, home=home)
    session_db = SessionDB(home / "state.db")
    session_db.start_session(
        session_manager.session_id,
        source="cli",
        cwd=str(cwd),
        model=runtime.model,
        title=session_manager.get_session_name() or prompt[:72],
    )

    extension_runner = ExtensionRunner(search_paths=ExtensionRunner.default_paths(home=home, cwd=cwd))
    loaded_extensions = extension_runner.load_all() if load_extensions else []

    input_payload = {"text": prompt, "cwd": str(cwd)}
    for result in await extension_runner.emit("input", input_payload):
        if isinstance(result, dict) and result.get("text"):
            prompt = str(result["text"])

    system_prompt = load_soul(home)
    memories = memory_snapshot(home)
    if memories:
        system_prompt = f"{system_prompt.strip()}\n\n{memories}"
    before_start = await extension_runner.emit_before_agent_start(
        {"prompt": prompt, "cwd": str(cwd), "system_prompt": system_prompt, "messages": []}
    )
    system_prompt = str(before_start.get("system_prompt", system_prompt))
    injected_messages = list(before_start.get("messages", []))

    history = session_manager.build_session_context()
    initial_messages = [{"role": "system", "content": system_prompt}, *injected_messages, *history]
    baseline = len(initial_messages)

    async def before_model_call(messages: list[dict[str, Any]]):
        payload = await extension_runner.emit_context({"messages": messages})
        return payload.get("messages", messages)

    async def before_tool_call(tool_name: str, arguments: dict[str, Any]):
        result = await extension_runner.emit_tool_call({"tool_name": tool_name, "arguments": arguments})
        if "arguments" not in result:
            result["arguments"] = arguments
        return result

    async def after_tool_result(tool_name: str, payload: dict[str, Any]):
        patched = await extension_runner.emit_tool_result({"tool_name": tool_name, **payload})
        return {
            "role": patched.get("role", "tool"),
            "name": patched.get("name", payload.get("name")),
            "tool_call_id": patched.get("tool_call_id", payload.get("tool_call_id")),
            "content": patched.get("content", payload.get("content", "")),
        }

    for _ in await extension_runner.emit(
        "model_select",
        {"model": runtime.model, "provider": runtime.provider, "base_url": runtime.base_url},
    ):
        pass

    agent = Agent(
        tool_registry=get_tool_registry(),
        toolset_resolver=build_toolset_resolver(),
        compressor=ContextCompressor(**config.get("compression", {})),
        max_iterations=int(config.get("agent", {}).get("max_turns", 8)),
    )
    result = await agent.run(
        prompt,
        model=runtime.model,
        provider=runtime.provider,
        base_url=runtime.base_url,
        cwd=cwd,
        home=home,
        toolsets=toolsets or config.get("toolsets", ["core"]),
        before_model_call=before_model_call,
        before_tool_call=before_tool_call,
        after_tool_result=after_tool_result,
        approval_callback=_default_approval_callback,
        session_db=session_db,
        history=initial_messages,
        env=env,
    )

    new_messages = result.messages[baseline:]
    for message in new_messages:
        role = message.get("role")
        if role == "system":
            continue
        session_manager.append_message(message)
        session_db.index_message(
            session_manager.session_id,
            role=role,
            content=str(message.get("content", "")),
            tool_name=message.get("name"),
            tool_call_id=message.get("tool_call_id"),
        )

    return PromptResult(
        text=result.final_text,
        model=runtime.model,
        provider=runtime.provider,
        session_path=session_manager.session_path(),
        messages=new_messages,
        loaded_extensions=loaded_extensions,
    )


def format_prompt_result(result: PromptResult, *, as_json: bool = False) -> str:
    payload = {
        "text": result.text,
        "model": result.model,
        "provider": result.provider,
        "session_path": str(result.session_path),
        "messages": result.messages,
        "loaded_extensions": result.loaded_extensions,
    }
    if as_json:
        return json.dumps(payload, indent=2, sort_keys=True)
    return result.text


def build_theme(home: Path | None = None):
    return SkinEngine(home=home).load()

