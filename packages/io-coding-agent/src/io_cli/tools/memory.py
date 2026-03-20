"""Persistent memory tools."""

from __future__ import annotations

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult


LIMITS = {
    "MEMORY.md": 2200,
    "USER.md": 1375,
}


class MemoryTool(Tool):
    name = "memory"
    description = "View and update persistent memory files."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["view", "save_note", "save_user"]},
            "content": {"type": "string"},
        },
        "required": ["action"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        action = str(arguments["action"])
        memory_dir = context.home / "memories"
        memory_dir.mkdir(parents=True, exist_ok=True)
        if action == "view":
            notes = []
            for name in ("MEMORY.md", "USER.md"):
                path = memory_dir / name
                if path.exists():
                    notes.append(f"# {name}\n{path.read_text(encoding='utf-8').strip()}")
            return ToolResult(content="\n\n".join(notes).strip() or "No memories saved yet.")

        if action not in {"save_note", "save_user"}:
            return ToolResult(content=f"Unsupported memory action: {action}", is_error=True)

        filename = "MEMORY.md" if action == "save_note" else "USER.md"
        path = memory_dir / filename
        current = path.read_text(encoding="utf-8") if path.exists() else ""
        addition = str(arguments.get("content", "")).strip()
        updated = "\n".join(part for part in (current.strip(), addition) if part).strip()
        limit = LIMITS[filename]
        if len(updated) > limit:
            updated = updated[:limit].rstrip()
        path.write_text(updated + ("\n" if updated else ""), encoding="utf-8")
        return ToolResult(content=f"Updated {filename}")


GLOBAL_TOOL_REGISTRY.register(MemoryTool())
