"""ACP permission bridging for IO."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import TimeoutError as FutureTimeout

import acp
from acp.schema import AllowedOutcome, PermissionOption


logger = logging.getLogger(__name__)


_KIND_TO_IO = {
    "allow_once": "once",
    "allow_always": "always",
    "reject_once": "deny",
    "reject_always": "deny",
}


def make_approval_callback(
    request_permission_fn,
    loop: asyncio.AbstractEventLoop,
    session_id: str,
    timeout: float = 60.0,
):
    def _callback(command: str, description: str) -> str:
        del description
        options = [
            PermissionOption(option_id="allow_once", kind="allow_once", name="Allow once"),
            PermissionOption(option_id="allow_always", kind="allow_always", name="Allow always"),
            PermissionOption(option_id="deny", kind="reject_once", name="Deny"),
        ]
        tool_call = acp.start_tool_call("perm-check", command, kind="execute")
        try:
            future = asyncio.run_coroutine_threadsafe(
                request_permission_fn(session_id=session_id, tool_call=tool_call, options=options),
                loop,
            )
            response = future.result(timeout=timeout)
        except (FutureTimeout, Exception) as exc:
            logger.warning("Permission request timed out or failed: %s", exc)
            return "deny"

        outcome = response.outcome
        if isinstance(outcome, AllowedOutcome):
            for option in options:
                if option.option_id == outcome.option_id:
                    return _KIND_TO_IO.get(option.kind, "deny")
            return "once"
        return "deny"

    return _callback
