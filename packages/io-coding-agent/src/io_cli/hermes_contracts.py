"""Hermes-style compatibility facade for IO CLI internals.

This module keeps IO's package boundaries intact while exposing stable
contract-style entry points that mirror common Hermes integration seams.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from io_agent import build_repo_map, semantic_search

from .auth import auth_status
from .context_references import expand_at_references
from .mcp_runtime import MCPAuthStore, mcp_auth_status
from .gateway_delivery import DeliveryRouter
from .gateway import GatewayManager
from .gateway_models import Platform
from .gateway_runner import run_gateway
from .gateway_session import SessionSource, build_session_context_prompt
from .tools import get_tool_registry
from .tools.registry import (
    get_available_toolsets,
    get_definitions,
    get_hermes_alias_map,
    get_tool_to_toolset_map,
    resolve_tool_name,
)


def gateway_manager(*, home: Path | None = None) -> GatewayManager:
    """Return a configured gateway manager."""
    return GatewayManager(home=home)


def gateway_run(
    *,
    home: Path | None = None,
    once: bool = False,
    poll_interval: float = 2.0,
    max_loops: int | None = None,
) -> dict[str, Any]:
    """Run gateway loop through a stable facade."""
    return run_gateway(home=home, once=once, poll_interval=poll_interval, max_loops=max_loops)


def provider_auth_status(*, home: Path | None = None) -> dict[str, object]:
    """Return auth status payload for providers."""
    return auth_status(home)


def tool_registry():
    """Return global tool registry via compatibility facade."""
    return get_tool_registry()


def expand_context_references(text: str, *, cwd: Path) -> str:
    """Expand ``@path`` references under ``cwd``."""
    return expand_at_references(text, cwd=cwd)


def build_gateway_session_contract(
    *,
    home: Path | None,
    platform: str,
    chat_id: str,
    chat_type: str = "dm",
    user_id: str | None = None,
    user_name: str | None = None,
    thread_id: str | None = None,
    chat_name: str | None = None,
) -> dict[str, Any]:
    """Build normalized session context payload + prompt text."""
    src = SessionSource(
        platform=Platform(platform),
        chat_id=chat_id,
        chat_type=chat_type,
        user_id=user_id,
        user_name=user_name,
        thread_id=thread_id,
        chat_name=chat_name,
    )
    mgr = GatewayManager(home=home)
    ctx = mgr.build_session_context(src)
    return {
        "session_context": ctx.to_dict(),
        "session_prompt": build_session_context_prompt(ctx),
    }


async def delivery_router_contract(
    *,
    home: Path | None,
    content: str,
    deliver: str | list[str] = "local",
    platform: str | None = None,
    chat_id: str | None = None,
    thread_id: str | None = None,
) -> dict[str, Any]:
    """Resolve/deliver output using gateway delivery conventions."""
    mgr = GatewayManager(home=home)
    cfg = mgr.load_config()
    router = DeliveryRouter(home=mgr.home, config=cfg, adapters={})
    origin = None
    if platform and chat_id:
        origin = SessionSource(platform=Platform(platform), chat_id=chat_id, thread_id=thread_id)
    targets = router.resolve_targets(deliver, origin=origin)
    result = await router.deliver(content, targets)
    return {"targets": [t.to_string() for t in targets], "result": result}


def tool_contracts(*, tool_names: set[str] | None = None) -> dict[str, Any]:
    """Return Hermes-style tool metadata bundle from IO registry."""
    names = tool_names or set(get_tool_registry().names())
    resolved_names = {resolve_tool_name(name) for name in names}
    return {
        "tool_to_toolset": get_tool_to_toolset_map(),
        "available_toolsets": get_available_toolsets(),
        "aliases": get_hermes_alias_map(),
        "definitions": get_definitions(resolved_names),
    }


def normalize_tool_call_contract(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize Hermes-style helper name -> IO canonical tool call payload."""
    return {
        "name": resolve_tool_name(name),
        "arguments": dict(arguments or {}),
    }


def auth_command_status_contract(*, home: Path | None = None) -> dict[str, object]:
    """CLI-facing auth status contract."""
    return auth_status(home)


def auth_command_copilot_login_contract(*, home: Path | None = None) -> bool:
    """CLI-facing auth login contract for Copilot device flow."""
    from io_ai.hermes_contracts import copilot_login_contract

    return copilot_login_contract(home=home)


def mcp_status_contract(*, home: Path | None = None) -> dict[str, Any]:
    """Return MCP auth/runtime status payload."""
    return mcp_auth_status(home)


def mcp_login_contract(
    *,
    home: Path | None = None,
    server: str,
    token: str,
    expires_at: str | None = None,
) -> dict[str, Any]:
    """Persist MCP server token and return status."""
    MCPAuthStore(home=home).set_token(server, token, expires_at=expires_at)
    return mcp_auth_status(home)


def mcp_logout_contract(*, home: Path | None = None, server: str) -> dict[str, Any]:
    """Remove MCP token for server and return status."""
    MCPAuthStore(home=home).clear_token(server)
    return mcp_auth_status(home)


def semantic_search_contract(*, query: str, cwd: Path, max_hits: int = 5) -> list[dict[str, Any]]:
    """Semantic search facade used by parity adapters."""
    hits = semantic_search(query, root=cwd, max_hits=max_hits)
    out: list[dict[str, Any]] = []
    for hit in hits:
        out.append(
            {
                "path": str(hit.path),
                "score": hit.score,
                "preview": hit.preview,
            }
        )
    return out


def repo_map_contract(*, cwd: Path, max_entries: int = 25) -> list[str]:
    """Repo-map facade used by parity adapters."""
    return build_repo_map(root=cwd, max_entries=max_entries)

