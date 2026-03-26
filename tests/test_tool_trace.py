from __future__ import annotations

from io_cli.tool_trace import format_tool_trace_lines, should_trace_tool


def test_tool_trace_formats_icon_name_and_args() -> None:
    lines = format_tool_trace_lines("search_files", {"pattern": "abc", "path": "/tmp"})
    assert lines
    assert lines[0].startswith("🔎 search_files(")
    assert '"pattern": "abc"' in lines[1]


def test_tool_trace_redacts_sensitive_values() -> None:
    lines = format_tool_trace_lines("bash", {"command": "echo hi", "api_key": "secret-key"})
    assert '"api_key": "***"' in lines[1]
    assert "secret-key" not in lines[1]


def test_tool_trace_verbose_mode_multiline() -> None:
    lines = format_tool_trace_lines("read_file", {"path": "/tmp/file.txt"}, mode="verbose")
    assert len(lines) == 2
    assert lines[1].startswith("{\n")
    assert '"path": "/tmp/file.txt"' in lines[1]


def test_tool_trace_suppress_filter() -> None:
    assert should_trace_tool("search_files", suppress_tools=["echo"]) is True
    assert should_trace_tool("echo", suppress_tools=["echo", "noop"]) is False


def test_tool_trace_uses_icon_preset_and_duration() -> None:
    lines = format_tool_trace_lines(
        "search_files",
        {"pattern": "x"},
        mode="compact",
        icon_preset="ascii",
        duration_seconds=0.42,
    )
    assert lines[0].startswith("S> search_files(")
    assert "(+0.42s)" in lines[0]

