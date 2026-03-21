"""Honcho HTTP tools — Honcho API v3 by default (see https://docs.honcho.dev). Legacy GET mode optional."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import load_config


def _honcho_section(home: Path) -> dict[str, Any]:
    cfg = load_config(home)
    raw = cfg.get("honcho")
    return raw if isinstance(raw, dict) else {}


def _honcho_headers(sec: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {"Accept": "application/json", "Content-Type": "application/json"}
    key = str(sec.get("api_key") or os.environ.get("HONCHO_API_KEY") or "").strip()
    if key:
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _workspace_id(sec: dict[str, Any]) -> str:
    return str(sec.get("workspace_id") or os.environ.get("HONCHO_WORKSPACE_ID") or "default").strip()


def _session_id(context: ToolContext, sec: dict[str, Any]) -> str:
    sid = str(
        sec.get("session_id")
        or context.env.get("HONCHO_SESSION_ID")
        or context.env.get("IO_SESSION_ID")
        or ""
    ).strip()
    return sid


async def _honcho_session(
    sec: dict[str, Any],
) -> tuple[httpx.AsyncClient | None, str | None]:
    if not sec.get("enabled"):
        return None, "Honcho is disabled. Set honcho.enabled: true in ~/.io/config.yaml"
    base = str(sec.get("base_url") or os.environ.get("HONCHO_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return None, "honcho.base_url is not configured"
    timeout = float(sec.get("timeout", 30.0) or 30.0)
    client = httpx.AsyncClient(base_url=base, headers=_honcho_headers(sec), timeout=timeout)
    return client, None


def _is_legacy(sec: dict[str, Any]) -> bool:
    ver = str(sec.get("api_version", "v3") or "v3").lower()
    if ver in {"v3", "3"}:
        return False
    if ver in {"legacy", "v1", "v2", "custom"}:
        return True
    paths = sec.get("paths")
    if isinstance(paths, dict) and paths.get("context"):
        ctx = str(paths.get("context", ""))
        if ctx.startswith("/api/") and "{workspace_id}" not in ctx:
            return True
    return False


def _legacy_paths(sec: dict[str, Any]) -> dict[str, str]:
    p = sec.get("paths")
    if isinstance(p, dict):
        return {str(k): str(v) for k, v in p.items()}
    return {
        "context": "/api/context",
        "profile": "/api/profile",
        "search": "/api/search",
        "conclude": "/api/conclude",
    }


class HonchoContextTool(Tool):
    name = "honcho_context"
    description = (
        "Fetch Honcho session context (messages + optional summary + peer representation). "
        "Uses Honcho API v3 by default. Requires honcho.enabled, workspace_id, and a session id "
        "(honcho.session_id or HONCHO_SESSION_ID or IO_SESSION_ID)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "tokens": {"type": "integer", "description": "Max tokens for context budget (v3)"},
            "search_query": {"type": "string", "description": "v3: semantic search over conclusions"},
            "summary": {"type": "boolean", "description": "Include session summary if available (v3)"},
            "peer_target": {"type": "string"},
            "peer_perspective": {"type": "string"},
            "session_id": {"type": "string", "description": "Override Honcho session id"},
        },
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        sec = _honcho_section(context.home)
        client, err = await _honcho_session(sec)
        if err or client is None:
            return ToolResult(content=json.dumps({"error": err}), is_error=True)
        try:
            if _is_legacy(sec):
                paths = _legacy_paths(sec)
                sk = str(arguments.get("session_id") or _session_id(context, sec)).strip()
                r = await client.get(paths["context"], params={"session": sk} if sk else None)
                r.raise_for_status()
                data = r.json() if r.content else {"raw": r.text}
            else:
                ws = _workspace_id(sec)
                sid = str(arguments.get("session_id") or _session_id(context, sec)).strip()
                if not sid:
                    return ToolResult(
                        content=json.dumps(
                            {
                                "error": "No Honcho session id. Set honcho.session_id, HONCHO_SESSION_ID, or IO_SESSION_ID."
                            }
                        ),
                        is_error=True,
                    )
                path = f"/v3/workspaces/{ws}/sessions/{sid}/context"
                params: dict[str, Any] = {}
                if arguments.get("tokens") is not None:
                    params["tokens"] = int(arguments["tokens"])
                if arguments.get("search_query"):
                    params["search_query"] = str(arguments["search_query"])
                if arguments.get("summary") is not None:
                    params["summary"] = bool(arguments["summary"])
                if arguments.get("peer_target"):
                    params["peer_target"] = str(arguments["peer_target"])
                if arguments.get("peer_perspective"):
                    params["peer_perspective"] = str(arguments["peer_perspective"])
                r = await client.get(path, params=params or None)
                r.raise_for_status()
                data = r.json() if r.content else {"raw": r.text}
        except Exception as exc:
            return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
        finally:
            await client.aclose()
        return ToolResult(content=json.dumps(data, ensure_ascii=False))


class HonchoProfileTool(Tool):
    name = "honcho_profile"
    description = (
        "Fetch Honcho peer card (v3: GET .../peers/{peer_id}/card). "
        "peer_id defaults to honcho.default_peer_id or 'user'."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "peer_id": {"type": "string", "description": "Observer peer id"},
            "target": {"type": "string", "description": "Optional target peer (card from observer→target)"},
        },
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        sec = _honcho_section(context.home)
        client, err = await _honcho_session(sec)
        if err or client is None:
            return ToolResult(content=json.dumps({"error": err}), is_error=True)
        try:
            if _is_legacy(sec):
                paths = _legacy_paths(sec)
                peer = str(arguments.get("peer_id", "") or "").strip()
                r = await client.get(paths["profile"], params={"peer": peer} if peer else None)
                r.raise_for_status()
                data = r.json() if r.content else {"raw": r.text}
            else:
                ws = _workspace_id(sec)
                peer = str(
                    arguments.get("peer_id")
                    or sec.get("default_peer_id")
                    or os.environ.get("HONCHO_DEFAULT_PEER_ID")
                    or "user"
                ).strip()
                path = f"/v3/workspaces/{ws}/peers/{peer}/card"
                tgt = str(arguments.get("target", "") or "").strip()
                r = await client.get(path, params={"target": tgt} if tgt else None)
                r.raise_for_status()
                data = r.json() if r.content else {"raw": r.text}
        except Exception as exc:
            return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
        finally:
            await client.aclose()
        return ToolResult(content=json.dumps(data, ensure_ascii=False))


class HonchoSearchTool(Tool):
    name = "honcho_search"
    description = "Search messages in a Honcho session (v3: POST .../search with JSON body)."
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            "session_id": {"type": "string"},
        },
        "required": ["query"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        sec = _honcho_section(context.home)
        client, err = await _honcho_session(sec)
        if err or client is None:
            return ToolResult(content=json.dumps({"error": err}), is_error=True)
        q = str(arguments.get("query", "")).strip()
        if not q:
            return ToolResult(content=json.dumps({"error": "query is required"}), is_error=True)
        limit = int(arguments.get("limit", 10) or 10)
        try:
            if _is_legacy(sec):
                paths = _legacy_paths(sec)
                r = await client.get(paths["search"], params={"q": q, "limit": limit})
                r.raise_for_status()
                data = r.json() if r.content else {"raw": r.text}
            else:
                ws = _workspace_id(sec)
                sid = str(arguments.get("session_id") or _session_id(context, sec)).strip()
                if not sid:
                    return ToolResult(
                        content=json.dumps({"error": "session_id required for v3 session search"}),
                        is_error=True,
                    )
                path = f"/v3/workspaces/{ws}/sessions/{sid}/search"
                body = {"query": q, "limit": limit}
                r = await client.post(path, json=body)
                r.raise_for_status()
                data = r.json() if r.content else {"raw": r.text}
        except Exception as exc:
            return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
        finally:
            await client.aclose()
        return ToolResult(content=json.dumps(data, ensure_ascii=False))


class HonchoConcludeTool(Tool):
    name = "honcho_conclude"
    description = (
        "Create Honcho conclusion(s) (v3: POST /v3/workspaces/{workspace}/conclusions). "
        "Requires observer_id and observed_id (defaults from honcho.conclusion_observer_peer / "
        "honcho.conclusion_observed_peer)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Conclusion content"},
            "observer_id": {"type": "string"},
            "observed_id": {"type": "string"},
            "session_id": {"type": "string", "description": "Optional session to attach conclusion"},
            "session_key": {"type": "string", "description": "Legacy alias for session_id"},
        },
        "required": ["text"],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        sec = _honcho_section(context.home)
        client, err = await _honcho_session(sec)
        if err or client is None:
            return ToolResult(content=json.dumps({"error": err}), is_error=True)
        text = str(arguments.get("text", "")).strip()
        if not text:
            return ToolResult(content=json.dumps({"error": "text is required"}), is_error=True)
        sk = str(arguments.get("session_id") or arguments.get("session_key") or "").strip() or None
        if not sk:
            sk_raw = _session_id(context, sec)
            sk = sk_raw or None
        try:
            if _is_legacy(sec):
                paths = _legacy_paths(sec)
                body = {"text": text, "session": sk or ""}
                r = await client.post(paths["conclude"], json=body)
                r.raise_for_status()
                data = r.json() if r.content else {"ok": True, "status": r.status_code}
            else:
                ws = _workspace_id(sec)
                obs = str(
                    arguments.get("observer_id")
                    or sec.get("conclusion_observer_peer")
                    or os.environ.get("HONCHO_OBSERVER_PEER")
                    or "io-agent"
                ).strip()
                obd = str(
                    arguments.get("observed_id")
                    or sec.get("conclusion_observed_peer")
                    or os.environ.get("HONCHO_OBSERVED_PEER")
                    or "user"
                ).strip()
                path = f"/v3/workspaces/{ws}/conclusions"
                conclusion: dict[str, Any] = {"content": text, "observer_id": obs, "observed_id": obd}
                if sk:
                    conclusion["session_id"] = sk
                batch = {"conclusions": [conclusion]}
                r = await client.post(path, json=batch)
                r.raise_for_status()
                data = r.json() if r.content else {"ok": True, "status": r.status_code}
        except Exception as exc:
            return ToolResult(content=json.dumps({"error": str(exc)}), is_error=True)
        finally:
            await client.aclose()
        return ToolResult(content=json.dumps(data, ensure_ascii=False))


GLOBAL_TOOL_REGISTRY.register(HonchoContextTool())
GLOBAL_TOOL_REGISTRY.register(HonchoProfileTool())
GLOBAL_TOOL_REGISTRY.register(HonchoSearchTool())
GLOBAL_TOOL_REGISTRY.register(HonchoConcludeTool())
