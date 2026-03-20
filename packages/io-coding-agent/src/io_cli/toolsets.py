"""Toolset definitions for the IO CLI."""

from __future__ import annotations

from io_agent import ToolsetResolver


TOOLSETS = {
    "core": {
        "bash",
        "read",
        "write",
        "edit",
        "find",
        "grep",
        "ls",
        "memory",
        "session_search",
    },
    "safe": {
        "read",
        "find",
        "grep",
        "ls",
        "memory",
        "session_search",
    },
}


def build_toolset_resolver() -> ToolsetResolver:
    return ToolsetResolver(toolsets={name: set(tools) for name, tools in TOOLSETS.items()})

