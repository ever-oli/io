"""Callback factories for bridging IO events to ACP notifications."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any

import acp

from .tools import build_tool_complete, build_tool_start, make_tool_call_id


logger = logging.getLogger(__name__)


def _send_update(
    conn: acp.Client,
    session_id: str,
    loop: asyncio.AbstractEventLoop,
    update: Any,
) -> None:
    try:
        future = asyncio.run_coroutine_threadsafe(conn.session_update(session_id, update), loop)
        future.result(timeout=5)
    except Exception:
        logger.debug("Failed to send ACP update", exc_info=True)


def make_tool_progress_cb(
    conn: acp.Client,
    session_id: str,
    loop: asyncio.AbstractEventLoop,
    tool_call_ids: dict[str, deque[str]],
):
    def _tool_progress(name: str, preview: str, args: Any = None) -> None:
        del preview
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, TypeError):
                args = {"raw": args}
        if not isinstance(args, dict):
            args = {}

        tool_call_id = make_tool_call_id()
        queue = tool_call_ids.get(name)
        if queue is None:
            queue = deque()
            tool_call_ids[name] = queue
        elif isinstance(queue, str):
            queue = deque([queue])
            tool_call_ids[name] = queue
        queue.append(tool_call_id)
        _send_update(conn, session_id, loop, build_tool_start(tool_call_id, name, args))

    return _tool_progress


def make_thinking_cb(conn: acp.Client, session_id: str, loop: asyncio.AbstractEventLoop):
    def _thinking(text: str) -> None:
        if text:
            _send_update(conn, session_id, loop, acp.update_agent_thought_text(text))

    return _thinking


def make_step_cb(
    conn: acp.Client,
    session_id: str,
    loop: asyncio.AbstractEventLoop,
    tool_call_ids: dict[str, deque[str]],
):
    def _step(api_call_count: int, prev_tools: Any = None) -> None:
        del api_call_count
        if not prev_tools or not isinstance(prev_tools, list):
            return
        for tool_info in prev_tools:
            tool_name = None
            result = None
            if isinstance(tool_info, dict):
                tool_name = tool_info.get("name") or tool_info.get("function_name")
                result = tool_info.get("result") or tool_info.get("output")
            elif isinstance(tool_info, str):
                tool_name = tool_info
            queue = tool_call_ids.get(tool_name or "")
            if isinstance(queue, str):
                queue = deque([queue])
                tool_call_ids[tool_name] = queue
            if tool_name and queue:
                tool_call_id = queue.popleft()
                _send_update(
                    conn,
                    session_id,
                    loop,
                    build_tool_complete(tool_call_id, tool_name, result=str(result) if result is not None else None),
                )
                if not queue:
                    tool_call_ids.pop(tool_name, None)

    return _step


def make_message_cb(conn: acp.Client, session_id: str, loop: asyncio.AbstractEventLoop):
    def _message(text: str) -> None:
        if text:
            _send_update(conn, session_id, loop, acp.update_agent_message_text(text))

    return _message
