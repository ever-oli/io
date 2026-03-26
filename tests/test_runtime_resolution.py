from __future__ import annotations

import json
from pathlib import Path

import pytest

from io_agent import resolve_runtime
from io_cli.config import ensure_io_home, load_config, set_config_value


def test_runtime_prefers_custom_provider_config(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    config = load_config(home)
    config["custom_providers"] = [
        {
            "name": "local",
            "base_url": "http://localhost:4000/v1",
            "api_key": "local-key",
            "api_mode": "chat_completions",
        }
    ]
    config = set_config_value(config, "model.provider", "custom:local")
    config = set_config_value(config, "model.default", "gpt-4.1-mini")
    runtime = resolve_runtime(config=config, home=home, env={})
    assert runtime.provider == "custom"
    assert runtime.base_url == "http://localhost:4000/v1"
    assert runtime.model == "custom/gpt-4.1-mini"


def test_runtime_falls_back_to_mock_on_fresh_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Isolate from developer machines: Copilot resolution can use `gh auth token`, which
    # would make _has_any_auth True and skip the no-keys → mock fallback.
    monkeypatch.setattr("io_ai.copilot_auth._try_gh_cli_token", lambda: None)
    home = ensure_io_home(tmp_path / "home")
    runtime = resolve_runtime(config=load_config(home), home=home, env={})
    assert runtime.provider == "mock"
    assert runtime.model == "mock/io-test"


def test_runtime_uses_active_provider_when_available(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    (home / "auth.json").write_text(
        json.dumps({"active_provider": "openrouter", "openrouter": {"api_key": "test-key"}}),
        encoding="utf-8",
    )
    runtime = resolve_runtime(config=load_config(home), home=home, env={})
    assert runtime.provider == "openrouter"
    assert runtime.model.startswith("openrouter/")
