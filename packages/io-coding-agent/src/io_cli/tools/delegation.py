"""Subagent delegation and sandboxed async tool execution (Hermes-style)."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from io_agent import Agent, ContextCompressor, GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..toolsets import build_toolset_resolver


def _safe_builtins() -> dict[str, Any]:
    import builtins

    names = (
        "print",
        "abs",
        "all",
        "any",
        "bin",
        "bool",
        "chr",
        "dict",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "oct",
        "ord",
        "pow",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
    )
    out = {n: getattr(builtins, n) for n in names}
    out.update({"True": True, "False": False, "None": None})
    return out


class DelegateTaskTool(Tool):
    name = "delegate_task"
    description = (
        "Run a focused sub-task with a separate agent turn budget and optional narrower toolsets. "
        "Returns a JSON summary (final text, iterations, interrupted)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Instructions for the subagent."},
            "max_turns": {"type": "integer", "minimum": 1, "maximum": 32, "default": 4},
            "toolsets": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Toolset names (e.g. safe, file). Defaults to safe.",
            },
        },
        "required": ["task"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        task = str(arguments.get("task", "")).strip()
        if not task:
            return ToolResult(content=json.dumps({"error": "task is required"}), is_error=True)
        depth = int(context.metadata.get("delegation_depth", 0) or 0)
        if depth >= 4:
            return ToolResult(
                content=json.dumps({"error": "delegation_depth limit reached (max 4 nested delegate_task calls)"}),
                is_error=True,
            )
        max_turns = int(arguments.get("max_turns", 4) or 4)
        max_turns = max(1, min(32, max_turns))
        raw_ts = arguments.get("toolsets")
        if isinstance(raw_ts, list) and raw_ts:
            toolsets = [str(x).strip() for x in raw_ts if str(x).strip()]
        else:
            toolsets = ["safe"]

        model = str(context.metadata.get("runtime_model", "mock/io-test"))
        provider = context.metadata.get("runtime_provider")
        base_url = context.metadata.get("runtime_base_url")

        sub_meta = {
            **context.metadata,
            "delegation_depth": depth + 1,
        }
        sub = Agent(
            tool_registry=GLOBAL_TOOL_REGISTRY,
            toolset_resolver=build_toolset_resolver(),
            compressor=ContextCompressor(),
            max_iterations=max_turns,
        )
        sub_result = await sub.run(
            task,
            model=model,
            provider=str(provider) if provider is not None else None,
            base_url=str(base_url) if base_url is not None else None,
            cwd=context.cwd,
            home=context.home,
            toolsets=toolsets,
            approval_callback=context.approval_callback,
            session_db=context.session_db,
            session_store=context.session_store,
            env=context.env,
            tool_context_metadata=sub_meta,
        )
        payload = {
            "summary": sub_result.final_text,
            "iterations": sub_result.iterations,
            "interrupted": sub_result.interrupted,
        }
        return ToolResult(content=json.dumps(payload, ensure_ascii=False))


class ExecuteCodeTool(Tool):
    name = "execute_code"
    description = (
        "Execute async Python that may await call_tool(name, args_dict) for allowed tools only. "
        "The code body is wrapped in async def __io_user_main(): ... — use top-level await inside that implied block "
        "(provide only the function body lines)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Async Python statements (function body). Example: result = await call_tool('read', {'path': 'README.md'}); print(result[:200])",
            },
            "allowed_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names permitted for call_tool. Defaults to read-only file/search tools.",
            },
        },
        "required": ["code"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        code = str(arguments.get("code", "")).rstrip()
        if not code.strip():
            return ToolResult(content=json.dumps({"error": "code is required"}), is_error=True)
        default_allowed = (
            "read_file",
            "read",
            "search_files",
            "find",
            "grep",
            "ls",
            "session_search",
            "memory",
            "skills_list",
            "skill_view",
        )
        raw = arguments.get("allowed_tools")
        if isinstance(raw, list) and raw:
            allowed = {str(x).strip() for x in raw if str(x).strip()}
        else:
            allowed = set(default_allowed)

        depth = int(context.metadata.get("execute_code_depth", 0) or 0)
        if depth >= 3:
            return ToolResult(
                content=json.dumps({"error": "execute_code nesting limit reached"}),
                is_error=True,
            )

        async def call_tool(name: str, args: dict[str, Any]) -> str:
            if name not in allowed:
                raise PermissionError(f"Tool {name!r} is not in allowed_tools")
            tool = GLOBAL_TOOL_REGISTRY.get(name)
            inner = ToolContext(
                cwd=context.cwd,
                home=context.home,
                env=context.env,
                session_db=context.session_db,
                session_store=context.session_store,
                approval_callback=context.approval_callback,
                metadata={**context.metadata, "execute_code_depth": depth + 1},
            )
            result = await tool.execute(inner, args)
            return result.content

        global_ns: dict[str, Any] = {**_safe_builtins(), "call_tool": call_tool, "json": json}
        indented = textwrap.indent(code, "    ")
        wrapped = f"async def __io_user_main():\n{indented}"
        local_ns: dict[str, Any] = {}
        try:
            exec(wrapped, global_ns, local_ns)  # noqa: S102 — intentional sandboxed agent tool
            runner = local_ns.get("__io_user_main")
            if runner is None or not callable(runner):
                return ToolResult(content=json.dumps({"error": "failed to define __io_user_main"}), is_error=True)
            await runner()
        except Exception as exc:
            return ToolResult(
                content=json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False),
                is_error=True,
            )
        return ToolResult(content=json.dumps({"ok": True, "note": "completed without return value"}, ensure_ascii=False))


GLOBAL_TOOL_REGISTRY.register(DelegateTaskTool())
GLOBAL_TOOL_REGISTRY.register(ExecuteCodeTool())
