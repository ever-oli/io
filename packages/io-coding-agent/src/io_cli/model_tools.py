"""IO-compatible orchestration layer over IO's tool registry."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from io_agent import SessionDB, ToolContext

from .config import ensure_io_home, load_env
from .tools.registry import (
    check_tool_availability as _check_tool_availability,
    check_toolset_requirements as _check_toolset_requirements,
    get_available_toolsets as _get_available_toolsets,
    get_definitions as _get_definitions,
    get_tool_registry,
    get_tool_to_toolset_map,
    get_toolset_requirements,
)
from .toolsets import get_all_toolsets, resolve_toolset, validate_toolset


def _run_async(coro: Any) -> Any:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result(timeout=300)
    return asyncio.run(coro)


TOOL_TO_TOOLSET_MAP: dict[str, str] = get_tool_to_toolset_map()
TOOLSET_REQUIREMENTS: dict[str, dict[str, Any]] = get_toolset_requirements()
_last_resolved_tool_names: list[str] = []

_LEGACY_TOOLSET_MAP = {
    "web_tools": ["web_search", "web_extract"],
    "terminal_tools": ["terminal", "process"],
    "file_tools": ["read_file", "write_file", "patch", "search_files"],
}


def get_tool_definitions(
    enabled_toolsets: list[str] | None = None,
    disabled_toolsets: list[str] | None = None,
    quiet_mode: bool = False,
) -> list[dict[str, Any]]:
    del quiet_mode
    tools_to_include: set[str] = set()

    if enabled_toolsets:
        for toolset_name in enabled_toolsets:
            if validate_toolset(toolset_name):
                tools_to_include.update(resolve_toolset(toolset_name))
            elif toolset_name in _LEGACY_TOOLSET_MAP:
                tools_to_include.update(_LEGACY_TOOLSET_MAP[toolset_name])
            elif toolset_name in get_tool_registry().tools:
                tools_to_include.add(toolset_name)
    elif disabled_toolsets:
        for toolset_name in get_all_toolsets():
            tools_to_include.update(resolve_toolset(toolset_name))
        for toolset_name in disabled_toolsets:
            if validate_toolset(toolset_name):
                tools_to_include.difference_update(resolve_toolset(toolset_name))
            elif toolset_name in _LEGACY_TOOLSET_MAP:
                tools_to_include.difference_update(_LEGACY_TOOLSET_MAP[toolset_name])
    else:
        for toolset_name in get_all_toolsets():
            tools_to_include.update(resolve_toolset(toolset_name))

    filtered_tools = _get_definitions(tools_to_include)

    global _last_resolved_tool_names
    _last_resolved_tool_names = [tool["function"]["name"] for tool in filtered_tools]
    return filtered_tools


def handle_function_call(
    function_name: str,
    function_args: dict[str, Any],
    task_id: str | None = None,
    user_task: str | None = None,
    enabled_tools: list[str] | None = None,
    honcho_manager: Any | None = None,
    honcho_session_key: str | None = None,
) -> str:
    del enabled_tools, honcho_manager, honcho_session_key
    registry = get_tool_registry()
    try:
        tool = registry.get(function_name)
    except KeyError:
        return json.dumps({"error": f"Unknown tool: {function_name}"}, ensure_ascii=False)

    home = ensure_io_home(None)
    context = ToolContext(
        cwd=Path.cwd(),
        home=home,
        env={**load_env(home), **os.environ},
        session_db=SessionDB(home / "state.db"),
        metadata={"task_id": task_id or "default", "user_task": user_task or ""},
    )

    try:
        result = _run_async(tool.execute(context, function_args))
    except Exception as exc:
        return json.dumps({"error": f"Error executing {function_name}: {exc}"}, ensure_ascii=False)

    payload = result.content
    try:
        json.loads(payload)
        return payload
    except Exception:
        if result.is_error:
            return json.dumps({"error": payload, **result.metadata}, ensure_ascii=False)
        return json.dumps({"output": payload, **result.metadata}, ensure_ascii=False)


def get_all_tool_names() -> list[str]:
    return get_tool_registry().names()


def get_toolset_for_tool(tool_name: str) -> str | None:
    return TOOL_TO_TOOLSET_MAP.get(tool_name)


def get_available_toolsets() -> dict[str, dict[str, Any]]:
    return _get_available_toolsets()


def check_toolset_requirements() -> dict[str, bool]:
    return _check_toolset_requirements()


def check_tool_availability(quiet: bool = False) -> tuple[list[str], list[dict[str, Any]]]:
    return _check_tool_availability(quiet=quiet)

