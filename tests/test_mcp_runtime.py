from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from io_cli.mcp_runtime import MCPAuthStore, mcp_auth_status


def test_mcp_auth_store_set_and_status(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = MCPAuthStore(home=home)
    store.set_token("cursor-ide-browser", "tok_123")
    status = mcp_auth_status(home)
    assert status["servers"]["cursor-ide-browser"]["configured"] is True
    assert status["servers"]["cursor-ide-browser"]["expired"] is False


def test_mcp_auth_store_expiry(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = MCPAuthStore(home=home)
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    store.set_token("x", "tok", expires_at=past)
    status = mcp_auth_status(home)
    assert status["servers"]["x"]["expired"] is True


def test_mcp_auth_store_clear(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = MCPAuthStore(home=home)
    store.set_token("x", "tok")
    assert store.clear_token("x") is True
    status = mcp_auth_status(home)
    assert "x" not in status["servers"]

