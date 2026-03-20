"""Tests for io_cli.acp_adapter.events."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from unittest.mock import AsyncMock, MagicMock, patch

import acp

from io_cli.acp_adapter.events import make_message_cb, make_step_cb, make_thinking_cb, make_tool_progress_cb


def _mock_future():
    future = MagicMock(spec=Future)
    future.result.return_value = None
    return future


def _threadsafe_stub():
    def _run(coro, loop):
        del loop
        coro.close()
        return _mock_future()

    return _run


class TestToolProgressCallback:
    def test_emits_tool_call_start(self):
        conn = MagicMock(spec=acp.Client)
        conn.session_update = AsyncMock()
        tool_call_ids = {}
        loop = asyncio.new_event_loop()
        try:
            callback = make_tool_progress_cb(conn, "session-1", loop, tool_call_ids)
            with patch("io_cli.acp_adapter.events.asyncio.run_coroutine_threadsafe", side_effect=_threadsafe_stub()) as mock_rcts:
                callback("terminal", "$ ls -la", {"command": "ls -la"})
            assert "terminal" in tool_call_ids
            mock_rcts.assert_called_once()
        finally:
            loop.close()

    def test_duplicate_same_name_tool_calls_use_fifo_ids(self):
        conn = MagicMock(spec=acp.Client)
        conn.session_update = AsyncMock()
        tool_call_ids = {}
        loop = asyncio.new_event_loop()
        try:
            progress_cb = make_tool_progress_cb(conn, "session-1", loop, tool_call_ids)
            step_cb = make_step_cb(conn, "session-1", loop, tool_call_ids)
            with patch("io_cli.acp_adapter.events.asyncio.run_coroutine_threadsafe", side_effect=_threadsafe_stub()):
                progress_cb("terminal", "$ ls", {"command": "ls"})
                progress_cb("terminal", "$ pwd", {"command": "pwd"})
                assert len(tool_call_ids["terminal"]) == 2
                step_cb(1, [{"name": "terminal", "result": "ok-1"}])
                assert len(tool_call_ids["terminal"]) == 1
                step_cb(2, [{"name": "terminal", "result": "ok-2"}])
                assert "terminal" not in tool_call_ids
        finally:
            loop.close()


class TestThinkingCallback:
    def test_ignores_empty_text(self):
        conn = MagicMock(spec=acp.Client)
        loop = asyncio.new_event_loop()
        try:
            callback = make_thinking_cb(conn, "session-1", loop)
            with patch("io_cli.acp_adapter.events.asyncio.run_coroutine_threadsafe") as mock_rcts:
                callback("")
            mock_rcts.assert_not_called()
        finally:
            loop.close()


class TestMessageCallback:
    def test_emits_agent_message_chunk(self):
        conn = MagicMock(spec=acp.Client)
        conn.session_update = AsyncMock()
        loop = asyncio.new_event_loop()
        try:
            callback = make_message_cb(conn, "session-1", loop)
            with patch("io_cli.acp_adapter.events.asyncio.run_coroutine_threadsafe", side_effect=_threadsafe_stub()) as mock_rcts:
                callback("Here is your answer.")
            mock_rcts.assert_called_once()
        finally:
            loop.close()
