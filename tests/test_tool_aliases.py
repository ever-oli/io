from __future__ import annotations

from io_cli.tools.registry import resolve_tool_name


def test_resolve_tool_aliases() -> None:
    assert resolve_tool_name("shell") == "bash"
    assert resolve_tool_name("run_terminal_cmd") == "terminal"
    assert resolve_tool_name("grep") == "search_files"


def test_resolve_tool_name_passthrough_for_canonical() -> None:
    assert resolve_tool_name("bash") == "bash"

