"""Lightweight MCP auth/runtime registry for CLI + ACP integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import atomic_write_json, ensure_io_home


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MCPAuthStore:
    home: Path | None = None

    def __post_init__(self) -> None:
        self.home = ensure_io_home(self.home)

    @property
    def auth_path(self) -> Path:
        assert self.home is not None
        return self.home / "mcp_auth.json"

    def load(self) -> dict[str, Any]:
        if not self.auth_path.exists():
            return {"servers": {}, "updated_at": None}
        try:
            data = json.loads(self.auth_path.read_text(encoding="utf-8"))
        except Exception:
            return {"servers": {}, "updated_at": None}
        if not isinstance(data, dict):
            return {"servers": {}, "updated_at": None}
        servers = data.get("servers", {})
        if not isinstance(servers, dict):
            servers = {}
        return {"servers": servers, "updated_at": data.get("updated_at")}

    def save(self, payload: dict[str, Any]) -> None:
        normalized = {
            "servers": payload.get("servers", {}) if isinstance(payload.get("servers"), dict) else {},
            "updated_at": _utc_now().isoformat(),
        }
        atomic_write_json(self.auth_path, normalized, indent=2, sort_keys=True, chmod=0o600)

    def set_token(self, server: str, token: str, *, expires_at: str | None = None) -> None:
        payload = self.load()
        servers = dict(payload.get("servers") or {})
        servers[str(server)] = {
            "token": str(token).strip(),
            "expires_at": str(expires_at).strip() if expires_at else None,
        }
        payload["servers"] = servers
        self.save(payload)

    def clear_token(self, server: str) -> bool:
        payload = self.load()
        servers = dict(payload.get("servers") or {})
        if server not in servers:
            return False
        servers.pop(server, None)
        payload["servers"] = servers
        self.save(payload)
        return True


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        dt = datetime.fromisoformat(expires_at)
    except Exception:
        return False
    return dt <= _utc_now()


def mcp_auth_status(home: Path | None = None) -> dict[str, Any]:
    store = MCPAuthStore(home=home)
    payload = store.load()
    out: dict[str, Any] = {"servers": {}, "updated_at": payload.get("updated_at")}
    for server, row in (payload.get("servers") or {}).items():
        if not isinstance(row, dict):
            continue
        token = str(row.get("token") or "")
        expires_at = row.get("expires_at")
        out["servers"][server] = {
            "configured": bool(token.strip()),
            "expired": _is_expired(str(expires_at) if expires_at else None),
            "expires_at": expires_at,
        }
    return out
