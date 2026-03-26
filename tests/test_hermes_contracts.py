from __future__ import annotations

import asyncio
from pathlib import Path

from io_ai.hermes_contracts import list_providers_contract, resolve_runtime_contract
from io_cli.hermes_contracts import (
    auth_command_status_contract,
    build_gateway_session_contract,
    delivery_router_contract,
    expand_context_references,
    mcp_login_contract,
    mcp_logout_contract,
    mcp_status_contract,
    normalize_tool_call_contract,
    provider_auth_status,
    tool_contracts,
    tool_registry,
)


def test_io_cli_contracts_surface(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    out = expand_context_references("read @a.txt", cwd=tmp_path)
    assert "BEGIN @a.txt" in out
    status = provider_auth_status(home=tmp_path / "home")
    assert "providers" in status
    assert "providers" in auth_command_status_contract(home=tmp_path / "home")
    assert tool_registry().get("bash").name == "bash"
    bundle = tool_contracts()
    assert "definitions" in bundle
    assert "aliases" in bundle
    assert any(item["function"]["name"] == "bash" for item in bundle["definitions"])
    normalized = normalize_tool_call_contract("run_terminal_cmd", {"command": "echo hi"})
    assert normalized["name"] == "terminal"
    mcp_login_contract(home=tmp_path / "home", server="cursor-ide-browser", token="abc")
    assert mcp_status_contract(home=tmp_path / "home")["servers"]["cursor-ide-browser"]["configured"] is True
    mcp_logout_contract(home=tmp_path / "home", server="cursor-ide-browser")


def test_gateway_session_and_delivery_contracts(tmp_path: Path) -> None:
    home = tmp_path / "home"
    payload = build_gateway_session_contract(
        home=home,
        platform="telegram",
        chat_id="123",
        chat_type="dm",
    )
    assert "session_context" in payload
    assert "session_prompt" in payload
    delivered = asyncio.run(delivery_router_contract(home=home, content="hi", deliver="local"))
    assert "local" in delivered["result"]


def test_io_ai_contracts_surface(tmp_path: Path) -> None:
    providers = list_providers_contract(home=tmp_path / "home", env={})
    assert isinstance(providers, list)
    runtime = resolve_runtime_contract(home=tmp_path / "home", env={}, config={"model": {"provider": "auto"}})
    assert "provider" in runtime

