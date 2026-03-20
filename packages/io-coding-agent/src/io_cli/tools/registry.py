"""Built-in tool loading."""

from __future__ import annotations

from io_agent import GLOBAL_TOOL_REGISTRY, ToolRegistry

from . import filesystem, memory, session_search, shell  # noqa: F401


def get_tool_registry() -> ToolRegistry:
    return GLOBAL_TOOL_REGISTRY

