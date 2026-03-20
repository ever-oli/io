"""Filesystem tools."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult


def _resolve(context: ToolContext, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (context.cwd / path).resolve()


class ReadTool(Tool):
    name = "read"
    description = "Read a file from disk."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = _resolve(context, str(arguments["path"]))
        if not path.exists():
            return ToolResult(content=f"File not found: {path}", is_error=True)
        return ToolResult(content=path.read_text(encoding="utf-8"))


class WriteTool(Tool):
    name = "write"
    description = "Write a file to disk."
    input_schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
        "required": ["path", "content"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = _resolve(context, str(arguments["path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(arguments["content"]), encoding="utf-8")
        return ToolResult(content=f"Wrote {path}")


class EditTool(Tool):
    name = "edit"
    description = "Replace text in a file."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
        },
        "required": ["path", "old", "new"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        path = _resolve(context, str(arguments["path"]))
        if not path.exists():
            return ToolResult(content=f"File not found: {path}", is_error=True)
        old = str(arguments["old"])
        new = str(arguments["new"])
        text = path.read_text(encoding="utf-8")
        if old not in text:
            return ToolResult(content="Old text was not found in the file.", is_error=True)
        updated = text.replace(old, new, 1)
        path.write_text(updated, encoding="utf-8")
        return ToolResult(content=f"Edited {path}")


class FindTool(Tool):
    name = "find"
    description = "Find files by glob pattern."
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["pattern"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        root = _resolve(context, str(arguments.get("path", ".")))
        pattern = str(arguments["pattern"])
        matches = [str(path) for path in root.rglob("*") if fnmatch.fnmatch(path.name, pattern)]
        return ToolResult(content="\n".join(matches))


class GrepTool(Tool):
    name = "grep"
    description = "Search file contents recursively."
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["pattern"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        root = _resolve(context, str(arguments.get("path", ".")))
        needle = str(arguments["pattern"])
        matches = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for index, line in enumerate(text.splitlines(), start=1):
                if needle in line:
                    matches.append(f"{path}:{index}:{line}")
        return ToolResult(content="\n".join(matches))


GLOBAL_TOOL_REGISTRY.register(ReadTool())
GLOBAL_TOOL_REGISTRY.register(WriteTool())
GLOBAL_TOOL_REGISTRY.register(EditTool())
GLOBAL_TOOL_REGISTRY.register(FindTool())
GLOBAL_TOOL_REGISTRY.register(GrepTool())

