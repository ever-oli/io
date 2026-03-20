"""Session search tool."""

from __future__ import annotations

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult


class SessionSearchTool(Tool):
    name = "session_search"
    description = "Search indexed session history."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer"},
        },
        "required": ["query"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        if context.session_db is None:
            return ToolResult(content="Session database is not configured.", is_error=True)
        rows = context.session_db.search(str(arguments["query"]), int(arguments.get("limit", 5)))
        lines = []
        for row in rows:
            lines.append(f"[{row.get('session_id')}] {row.get('role')}: {row.get('content')}")
        return ToolResult(content="\n".join(lines) or "No matching sessions.")


GLOBAL_TOOL_REGISTRY.register(SessionSearchTool())

