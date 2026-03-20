"""Tests for io_cli.acp_adapter.tools."""

from acp.schema import ContentToolCallContent, FileEditToolCallContent, ToolCallLocation, ToolCallProgress, ToolCallStart

from io_cli.acp_adapter.tools import (
    TOOL_KIND_MAP,
    build_tool_complete,
    build_tool_start,
    build_tool_title,
    extract_locations,
    get_tool_kind,
    make_tool_call_id,
)


COMMON_TOOLS = ["read_file", "search_files", "terminal", "patch", "write_file", "process"]


class TestToolKindMap:
    def test_all_common_tools_have_kind(self):
        for tool in COMMON_TOOLS:
            assert tool in TOOL_KIND_MAP

    def test_unknown_tool_returns_other_kind(self):
        assert get_tool_kind("nonexistent_tool_xyz") == "other"


class TestMakeToolCallId:
    def test_prefix_and_uniqueness(self):
        ids = {make_tool_call_id() for _ in range(100)}
        assert len(ids) == 100
        assert all(item.startswith("tc-") for item in ids)


class TestBuildToolTitle:
    def test_terminal_title_truncates(self):
        title = build_tool_title("terminal", {"command": "x" * 200})
        assert len(title) < 120
        assert "..." in title

    def test_unknown_tool_uses_name(self):
        assert build_tool_title("some_tool", {"foo": "bar"}) == "some_tool"


class TestBuildToolStart:
    def test_build_tool_start_for_patch(self):
        result = build_tool_start(
            "tc-1",
            "patch",
            {"path": "src/main.py", "old_string": "print('hello')", "new_string": "print('world')"},
        )
        assert isinstance(result, ToolCallStart)
        assert result.kind == "edit"
        assert isinstance(result.content[0], FileEditToolCallContent)

    def test_build_tool_start_for_terminal(self):
        result = build_tool_start("tc-2", "terminal", {"command": "ls -la /tmp"})
        assert isinstance(result, ToolCallStart)
        assert result.kind == "execute"
        assert isinstance(result.content[0], ContentToolCallContent)
        assert "ls -la /tmp" in result.content[0].content.text

    def test_build_tool_start_generic_fallback(self):
        result = build_tool_start("tc-5", "some_tool", {"foo": "bar", "baz": 42})
        assert isinstance(result, ToolCallStart)
        assert result.kind == "other"


class TestBuildToolComplete:
    def test_build_tool_complete_for_terminal(self):
        result = build_tool_complete("tc-2", "terminal", "total 42")
        assert isinstance(result, ToolCallProgress)
        assert result.status == "completed"
        assert "total 42" in result.content[0].content.text

    def test_build_tool_complete_truncates_large_output(self):
        big_output = "x" * 10000
        result = build_tool_complete("tc-6", "read_file", big_output)
        assert "truncated" in result.content[0].content.text


class TestExtractLocations:
    def test_extract_locations_with_path(self):
        locations = extract_locations({"path": "src/app.py", "offset": 42})
        assert len(locations) == 1
        assert isinstance(locations[0], ToolCallLocation)
        assert locations[0].path == "src/app.py"
        assert locations[0].line == 42

    def test_extract_locations_without_path(self):
        assert extract_locations({"command": "echo hi"}) == []
