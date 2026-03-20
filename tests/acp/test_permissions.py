"""Tests for io_cli.acp_adapter.permissions."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

from acp.schema import AllowedOutcome, DeniedOutcome, RequestPermissionResponse

from io_cli.acp_adapter.permissions import make_approval_callback


def _response(outcome):
    return RequestPermissionResponse(outcome=outcome)


def _threadsafe_return(response=None, exc: Exception | None = None):
    def _run(coro, loop):
        del loop
        coro.close()
        future = MagicMock(spec=Future)
        if exc is not None:
            future.result.side_effect = exc
        else:
            future.result.return_value = response
        return future

    return _run


class TestApprovalMapping:
    def test_allow_once_maps_correctly(self):
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_request_permission = MagicMock(name="request_permission")
        with patch(
            "io_cli.acp_adapter.permissions.asyncio.run_coroutine_threadsafe",
            side_effect=_threadsafe_return(_response(AllowedOutcome(option_id="allow_once", outcome="selected"))),
        ):
            callback = make_approval_callback(mock_request_permission, loop, session_id="s1")
            assert callback("rm -rf /", "dangerous") == "once"

    def test_allow_always_maps_correctly(self):
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_request_permission = MagicMock(name="request_permission")
        with patch(
            "io_cli.acp_adapter.permissions.asyncio.run_coroutine_threadsafe",
            side_effect=_threadsafe_return(_response(AllowedOutcome(option_id="allow_always", outcome="selected"))),
        ):
            callback = make_approval_callback(mock_request_permission, loop, session_id="s1")
            assert callback("rm -rf /", "dangerous") == "always"

    def test_deny_maps_correctly(self):
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_request_permission = MagicMock(name="request_permission")
        with patch(
            "io_cli.acp_adapter.permissions.asyncio.run_coroutine_threadsafe",
            side_effect=_threadsafe_return(_response(DeniedOutcome(outcome="cancelled"))),
        ):
            callback = make_approval_callback(mock_request_permission, loop, session_id="s1")
            assert callback("rm -rf /", "dangerous") == "deny"

    def test_timeout_returns_deny(self):
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_request_permission = MagicMock(name="request_permission")
        with patch(
            "io_cli.acp_adapter.permissions.asyncio.run_coroutine_threadsafe",
            side_effect=_threadsafe_return(exc=TimeoutError("timed out")),
        ):
            callback = make_approval_callback(mock_request_permission, loop, session_id="s1", timeout=0.01)
            assert callback("rm -rf /", "dangerous") == "deny"
