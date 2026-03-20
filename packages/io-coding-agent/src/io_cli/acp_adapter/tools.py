"""ACP tool helpers for mapping IO tools to ACP tool kinds."""

from __future__ import annotations

import json
import uuid
from typing import Any

import acp
from acp.schema import ToolCallLocation, ToolCallProgress, ToolCallStart, ToolKind


TOOL_KIND_MAP: dict[str, ToolKind] = {
    "read_file": "read",
    "write_file": "edit",
    "patch": "edit",
    "search_files": "search",
    "terminal": "execute",
    "process": "execute",
    "execute_code": "execute",
    "web_search": "fetch",
    "web_extract": "fetch",
    "browser_navigate": "fetch",
    "browser_click": "execute",
    "browser_type": "execute",
    "browser_snapshot": "read",
    "browser_vision": "read",
    "browser_scroll": "execute",
    "browser_press": "execute",
    "browser_back": "execute",
    "browser_close": "execute",
    "browser_get_images": "read",
    "delegate_task": "execute",
    "vision_analyze": "read",
    "image_generate": "execute",
    "text_to_speech": "execute",
    "_thinking": "think",
}


def get_tool_kind(tool_name: str) -> ToolKind:
    return TOOL_KIND_MAP.get(tool_name, "other")


def make_tool_call_id() -> str:
    return f"tc-{uuid.uuid4().hex[:12]}"


def build_tool_title(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "terminal":
        command = str(args.get("command", ""))
        if len(command) > 80:
            command = f"{command[:77]}..."
        return f"terminal: {command}"
    if tool_name == "read_file":
        return f"read: {args.get('path', '?')}"
    if tool_name == "write_file":
        return f"write: {args.get('path', '?')}"
    if tool_name == "patch":
        return f"patch ({args.get('mode', 'replace')}): {args.get('path', '?')}"
    if tool_name == "search_files":
        return f"search: {args.get('pattern', '?')}"
    if tool_name == "web_search":
        return f"web search: {args.get('query', '?')}"
    if tool_name == "web_extract":
        urls = args.get("urls", [])
        if urls:
            suffix = f" (+{len(urls) - 1})" if len(urls) > 1 else ""
            return f"extract: {urls[0]}{suffix}"
        return "web extract"
    if tool_name == "delegate_task":
        goal = str(args.get("goal", ""))
        if goal and len(goal) > 60:
            goal = f"{goal[:57]}..."
        return f"delegate: {goal}" if goal else "delegate task"
    if tool_name == "execute_code":
        return "execute code"
    if tool_name == "vision_analyze":
        return f"analyze image: {str(args.get('question', '?'))[:50]}"
    return tool_name


def build_tool_start(tool_call_id: str, tool_name: str, arguments: dict[str, Any]) -> ToolCallStart:
    kind = get_tool_kind(tool_name)
    title = build_tool_title(tool_name, arguments)
    locations = extract_locations(arguments)

    if tool_name == "patch":
        mode = arguments.get("mode", "replace")
        if mode == "replace":
            content = [
                acp.tool_diff_content(
                    path=arguments.get("path", ""),
                    new_text=arguments.get("new_string", ""),
                    old_text=arguments.get("old_string", ""),
                )
            ]
        else:
            content = [acp.tool_content(acp.text_block(str(arguments.get("patch", ""))))]
        return acp.start_tool_call(
            tool_call_id,
            title,
            kind=kind,
            content=content,
            locations=locations,
            raw_input=arguments,
        )

    if tool_name == "write_file":
        content = [
            acp.tool_diff_content(
                path=arguments.get("path", ""),
                new_text=arguments.get("content", ""),
            )
        ]
        return acp.start_tool_call(
            tool_call_id,
            title,
            kind=kind,
            content=content,
            locations=locations,
            raw_input=arguments,
        )

    if tool_name == "terminal":
        content = [acp.tool_content(acp.text_block(f"$ {arguments.get('command', '')}"))]
        return acp.start_tool_call(
            tool_call_id,
            title,
            kind=kind,
            content=content,
            locations=locations,
            raw_input=arguments,
        )

    if tool_name == "read_file":
        content = [acp.tool_content(acp.text_block(f"Reading {arguments.get('path', '')}"))]
        return acp.start_tool_call(
            tool_call_id,
            title,
            kind=kind,
            content=content,
            locations=locations,
            raw_input=arguments,
        )

    if tool_name == "search_files":
        pattern = arguments.get("pattern", "")
        target = arguments.get("target", "content")
        content = [acp.tool_content(acp.text_block(f"Searching for '{pattern}' ({target})"))]
        return acp.start_tool_call(
            tool_call_id,
            title,
            kind=kind,
            content=content,
            locations=locations,
            raw_input=arguments,
        )

    return acp.start_tool_call(
        tool_call_id,
        title,
        kind=kind,
        content=[acp.tool_content(acp.text_block(json.dumps(arguments, indent=2, default=str)))],
        locations=locations,
        raw_input=arguments,
    )


def build_tool_complete(tool_call_id: str, tool_name: str, result: str | None = None) -> ToolCallProgress:
    display_result = result or ""
    if len(display_result) > 5000:
        display_result = f"{display_result[:4900]}\n... ({len(result or '')} chars total, truncated)"
    return acp.update_tool_call(
        tool_call_id,
        kind=get_tool_kind(tool_name),
        status="completed",
        content=[acp.tool_content(acp.text_block(display_result))],
        raw_output=result,
    )


def extract_locations(arguments: dict[str, Any]) -> list[ToolCallLocation]:
    path = arguments.get("path")
    if not path:
        return []
    return [
        ToolCallLocation(
            path=str(path),
            line=arguments.get("offset") or arguments.get("line"),
        )
    ]
