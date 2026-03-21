"""Agent tool for holographic (HRR) memory — Nuggets-style."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..nuggets.promote import promote_facts
from ..nuggets.shelf import NuggetShelf


def _open_shelf(home: Path) -> NuggetShelf:
    d = home / "nuggets"
    shelf = NuggetShelf(save_dir=d, auto_save=True)
    shelf.load_all()
    return shelf


class NuggetsTool(Tool):
    name = "nuggets"
    description = (
        "Holographic memory (HRR): remember/recall key-value facts in named topic nuggets. "
        "Frequently recalled facts can be promoted into MEMORY.md. "
        "Ported from Nuggets (github.com/NeoVertex1/nuggets)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "remember",
                    "recall",
                    "forget",
                    "list",
                    "status",
                    "create_nugget",
                    "promote",
                ],
            },
            "nugget_name": {
                "type": "string",
                "description": "Topic bucket (e.g. learnings, preferences, project-x).",
            },
            "key": {"type": "string"},
            "value": {"type": "string"},
            "query": {"type": "string", "description": "For recall: natural language or key."},
        },
        "required": ["action"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        action = str(arguments["action"])
        home = context.home
        shelf = _open_shelf(home)
        session_id = str(context.env.get("IO_SESSION_ID", ""))

        try:
            if action == "create_nugget":
                name = str(arguments.get("nugget_name") or "").strip() or "default"
                shelf.get_or_create(name)
                return ToolResult(content=json.dumps({"ok": True, "nugget": name}))

            if action == "remember":
                nn = str(arguments.get("nugget_name") or "default").strip() or "default"
                key = str(arguments.get("key") or "").strip()
                value = str(arguments.get("value") or "").strip()
                if not key or not value:
                    return ToolResult(content="remember requires key and value", is_error=True)
                shelf.get_or_create(nn).remember(key, value)
                return ToolResult(
                    content=json.dumps({"ok": True, "nugget": nn, "key": key}, ensure_ascii=False)
                )

            if action == "recall":
                q = str(arguments.get("query") or "").strip()
                if not q:
                    return ToolResult(content="recall requires query", is_error=True)
                nn = str(arguments.get("nugget_name") or "").strip() or None
                r = shelf.recall(q, nugget_name=nn, session_id=session_id)
                return ToolResult(content=json.dumps(r, ensure_ascii=False))

            if action == "forget":
                nn = str(arguments.get("nugget_name") or "default").strip() or "default"
                key = str(arguments.get("key") or "").strip()
                if not key:
                    return ToolResult(content="forget requires key", is_error=True)
                ok = shelf.forget(nn, key)
                return ToolResult(content=json.dumps({"ok": ok, "nugget": nn, "key": key}))

            if action == "list":
                out: list[dict[str, Any]] = []
                for info in shelf.list():
                    name = str(info["name"])
                    try:
                        facts = shelf.get(name).facts()
                    except ValueError:
                        facts = []
                    out.append({**info, "facts": facts})
                return ToolResult(content=json.dumps(out, ensure_ascii=False, indent=2))

            if action == "status":
                return ToolResult(
                    content=json.dumps(shelf.list(), ensure_ascii=False, indent=2)
                )

            if action == "promote":
                n = promote_facts(shelf, memories_dir=home / "memories")
                return ToolResult(
                    content=json.dumps(
                        {"promoted_new_keys": n, "memories_path": str(home / "memories" / "MEMORY.md")},
                        ensure_ascii=False,
                    )
                )

        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        return ToolResult(content=f"Unknown action: {action}", is_error=True)


GLOBAL_TOOL_REGISTRY.register(NuggetsTool())
