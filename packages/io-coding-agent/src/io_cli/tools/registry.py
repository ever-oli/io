"""Built-in tool loading plus IO-style metadata helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from io_agent import GLOBAL_TOOL_REGISTRY, ToolRegistry

from . import compat, cronjob, filesystem, memory, session_search, shell, skills, web  # noqa: F401


@dataclass(frozen=True, slots=True)
class ToolMetadata:
    name: str
    toolset: str
    emoji: str = ""
    requires_env: tuple[str, ...] = ()


TOOL_METADATA: dict[str, ToolMetadata] = {
    "terminal": ToolMetadata("terminal", "terminal", "💻"),
    "process": ToolMetadata("process", "terminal", "ΦΦ️"),
    "bash": ToolMetadata("bash", "terminal", "💻"),
    "ls": ToolMetadata("ls", "terminal", "📂"),
    "read_file": ToolMetadata("read_file", "file", "📖"),
    "write_file": ToolMetadata("write_file", "file", "Φ️"),
    "patch": ToolMetadata("patch", "file", "🔧"),
    "search_files": ToolMetadata("search_files", "file", "🔎"),
    "read": ToolMetadata("read", "file", "📖"),
    "write": ToolMetadata("write", "file", "Φ️"),
    "edit": ToolMetadata("edit", "file", "🔧"),
    "find": ToolMetadata("find", "file", "📂"),
    "grep": ToolMetadata("grep", "file", "🔎"),
    "memory": ToolMetadata("memory", "memory", "🧠"),
    "session_search": ToolMetadata("session_search", "session_search", "🗂️"),
    "skills_list": ToolMetadata("skills_list", "skills", "Φ"),
    "skill_view": ToolMetadata("skill_view", "skills", "Φ"),
    "skill_manage": ToolMetadata("skill_manage", "skills", "📝"),
    "cronjob": ToolMetadata("cronjob", "cronjob", "Φ"),
    "web_search": ToolMetadata("web_search", "web", "🔍"),
    "web_extract": ToolMetadata("web_extract", "web", "📄"),
}


def get_tool_registry() -> ToolRegistry:
    return GLOBAL_TOOL_REGISTRY


def get_tool_to_toolset_map() -> dict[str, str]:
    return {
        name: meta.toolset
        for name, meta in TOOL_METADATA.items()
        if name in GLOBAL_TOOL_REGISTRY.tools
    }


def get_toolset_requirements() -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for name, meta in TOOL_METADATA.items():
        if name not in GLOBAL_TOOL_REGISTRY.tools:
            continue
        bucket = grouped.setdefault(
            meta.toolset,
            {
                "name": meta.toolset,
                "env_vars": [],
                "check_fn": None,
                "setup_url": None,
                "tools": [],
            },
        )
        bucket["tools"].append(name)
        for env_var in meta.requires_env:
            if env_var not in bucket["env_vars"]:
                bucket["env_vars"].append(env_var)
    return grouped


def get_definitions(tool_names: set[str], *, quiet: bool = False) -> list[dict[str, Any]]:
    del quiet
    definitions: list[dict[str, Any]] = []
    for name in sorted(tool_names):
        if name not in GLOBAL_TOOL_REGISTRY.tools:
            continue
        tool = GLOBAL_TOOL_REGISTRY.get(name)
        definitions.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
        )
    return definitions


def get_available_toolsets() -> dict[str, dict[str, Any]]:
    from ..toolsets import get_all_toolsets, resolve_toolset

    available_names = set(GLOBAL_TOOL_REGISTRY.names())
    rows: dict[str, dict[str, Any]] = {}
    for name, payload in get_all_toolsets().items():
        resolved = sorted(item for item in resolve_toolset(name) if item in available_names)
        rows[name] = {
            "available": bool(resolved),
            "tools": resolved,
            "description": str(payload.get("description", "")),
            "requirements": [],
        }
    return rows


def check_toolset_requirements() -> dict[str, bool]:
    return {name: payload["available"] for name, payload in get_available_toolsets().items()}


def check_tool_availability(quiet: bool = False) -> tuple[list[str], list[dict[str, Any]]]:
    del quiet
    available: list[str] = []
    unavailable: list[dict[str, Any]] = []
    for name, payload in get_available_toolsets().items():
        if payload["available"]:
            available.append(name)
        else:
            unavailable.append({"name": name, "env_vars": [], "tools": []})
    return available, unavailable
