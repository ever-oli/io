"""Main orchestration for the IO CLI."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from io_agent import Agent, ContextCompressor, SessionDB, build_repo_map, resolve_runtime, semantic_search
from io_ai.types import Usage

from .config import ensure_io_home, load_config, load_env, load_soul, memory_snapshot
from .context_references import expand_at_references
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
    usage: Usage = field(default_factory=Usage)
    interrupted: bool = False


def _default_approval_callback(_tool_name: str, _arguments: dict[str, Any], _reason: str) -> bool:
    return os.getenv("IO_AUTO_APPROVE_DANGEROUS", "0") == "1"


def _build_compressor(config: dict[str, Any]) -> ContextCompressor:
    compression = dict(config.get("compression", {}))
    if "threshold" in compression and "threshold_messages" not in compression:
        threshold = compression.get("threshold")
        if isinstance(threshold, (int, float)) and threshold > 1:
            compression["threshold_messages"] = int(threshold)
        else:
            compression["threshold_messages"] = 20
    compression.pop("threshold", None)
    compression.pop("summary_model", None)
    compression.pop("summary_provider", None)
    compression.pop("summary_base_url", None)
    return ContextCompressor(**compression)


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
    system_prompt_suffix: str | None = None,
    env_overrides: dict[str, str] | None = None,
    session_source: str = "cli",
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
    interrupt_registry: dict[str, Any] | None = None,
) -> PromptResult:
    cwd = (cwd or Path.cwd()).resolve()
    home = ensure_io_home(home)
    config = load_config(home)
    session_manager = SessionManager.open(session_path) if session_path else SessionManager.continue_recent(cwd, home=home)
    env = {**load_env(home), **os.environ}
    if env_overrides:
        env.update({key: str(value) for key, value in env_overrides.items()})
    env["IO_SESSION_ID"] = str(session_manager.session_id)
    runtime = resolve_runtime(
        cli_model=model,
        cli_provider=provider,
        cli_base_url=base_url,
        config=config,
        env=env,
        home=home,
    )
    session_db = SessionDB(home / "state.db")
    session_db.start_session(
        session_manager.session_id,
        source=session_source,
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
    prompt = expand_at_references(prompt, cwd=cwd)

    system_prompt = load_soul(home, cwd=cwd, config=config)
    semantic_cfg = config.get("semantic") if isinstance(config.get("semantic"), dict) else {}
    semantic_enabled = bool(semantic_cfg.get("enabled", False) or env.get("IO_SEMANTIC_CONTEXT", "") in {"1", "true", "yes"})
    repo_map_enabled = bool(semantic_cfg.get("repo_map", False) or env.get("IO_REPO_MAP_CONTEXT", "") in {"1", "true", "yes"})
    semantic_block: str = ""
    if semantic_enabled:
        try:
            max_hits = int(semantic_cfg.get("max_hits", 5) or 5)
            hits = semantic_search(prompt, root=cwd, max_hits=max_hits)
            if hits:
                lines = ["## Semantic Context (best matching files)"]
                for hit in hits:
                    rel = str(hit.path.relative_to(cwd))
                    lines.append(f"- {rel} (score={hit.score:.2f}) :: {hit.preview}")
                semantic_block = "\n".join(lines)
        except Exception:
            semantic_block = ""
    repo_map_block: str = ""
    if repo_map_enabled:
        try:
            max_entries = int(semantic_cfg.get("repo_map_max_entries", 25) or 25)
            entries = build_repo_map(root=cwd, max_entries=max_entries)
            if entries:
                repo_map_block = "## Repo Map (top weighted files)\n" + "\n".join(f"- {item}" for item in entries)
        except Exception:
            repo_map_block = ""
    memories = memory_snapshot(home)
    if memories:
        system_prompt = f"{system_prompt.strip()}\n\n{memories}"
    if semantic_block:
        system_prompt = f"{system_prompt.strip()}\n\n{semantic_block}"
    if repo_map_block:
        system_prompt = f"{system_prompt.strip()}\n\n{repo_map_block}"
    if system_prompt_suffix:
        suffix = str(system_prompt_suffix).strip()
        if suffix:
            system_prompt = f"{system_prompt.strip()}\n\n{suffix}"
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
        compressor=_build_compressor(config),
        max_iterations=int(config.get("agent", {}).get("max_turns", 8)),
    )
    if interrupt_registry is not None:
        interrupt_registry["agent"] = agent
    display_cfg = config.get("display") if isinstance(config.get("display"), dict) else {}
    stream_tokens = bool(display_cfg.get("streaming", False))
    stream_tools = bool(display_cfg.get("stream_tool_output", True))

    def _tool_output_cb(tool_name: str, stream: str, chunk: str) -> None:
        if on_event:
            on_event("tool_output_delta", {"tool": tool_name, "stream": stream, "delta": chunk})

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
        on_event=on_event,
        stream_tokens=stream_tokens,
        tool_output_callback=_tool_output_cb if stream_tools else None,
        tool_context_metadata={
            "task_id": env.get("IO_SESSION_ID", ""),
            "runtime_model": runtime.model,
            "runtime_provider": runtime.provider,
            "runtime_base_url": runtime.base_url,
        },
    )

    new_messages = result.messages[baseline:]
    for message in new_messages:
        role = message.get("role")
        if role == "system":
            continue
        session_manager.append_message(message)
        session_db.index_message(
            session_manager.session_id,
            role=str(role or "assistant"),
            content=str(message.get("content", "")),
            tool_name=message.get("name"),
            tool_call_id=message.get("tool_call_id"),
            payload=message,
        )

    ncfg = config.get("nuggets") if isinstance(config.get("nuggets"), dict) else {}
    if ncfg.get("auto_promote", True):
        try:
            from .nuggets.promote import promote_facts
            from .nuggets.shelf import NuggetShelf

            sh = NuggetShelf(save_dir=home / "nuggets", auto_save=True)
            sh.load_all()
            promote_facts(sh, memories_dir=home / "memories")
        except ImportError:
            pass
        except OSError:
            pass

    return PromptResult(
        text=result.final_text,
        model=runtime.model,
        provider=runtime.provider,
        session_path=session_manager.session_path(),
        messages=new_messages,
        loaded_extensions=loaded_extensions,
        usage=result.usage,
        interrupted=result.interrupted,
    )


def format_prompt_result(result: PromptResult, *, as_json: bool = False) -> str:
    payload = {
        "text": result.text,
        "model": result.model,
        "provider": result.provider,
        "session_path": str(result.session_path),
        "messages": result.messages,
        "loaded_extensions": result.loaded_extensions,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cache_read_tokens": result.usage.cache_read_tokens,
            "cache_write_tokens": result.usage.cache_write_tokens,
            "reasoning_tokens": result.usage.reasoning_tokens,
            "cost_usd": result.usage.cost_usd,
        },
    }
    if as_json:
        return json.dumps(payload, indent=2, sort_keys=True)
    return result.text


def build_theme(home: Path | None = None):
    return SkinEngine(home=home).load()
