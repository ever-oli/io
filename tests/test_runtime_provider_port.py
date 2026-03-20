from __future__ import annotations

import json
from pathlib import Path

from io_ai.codex_models import get_codex_model_ids
from io_ai.models import copilot_model_api_mode
from io_ai.runtime_provider import OPENROUTER_BASE_URL, resolve_runtime_provider


def test_resolve_runtime_provider_openrouter_explicit() -> None:
    resolved = resolve_runtime_provider(
        requested="openrouter",
        explicit_api_key="test-key",
        explicit_base_url="https://example.com/v1/",
        config={},
        env={},
    )

    assert resolved["provider"] == "openrouter"
    assert resolved["api_mode"] == "chat_completions"
    assert resolved["api_key"] == "test-key"
    assert resolved["base_url"] == "https://example.com/v1"
    assert resolved["source"] == "explicit"


def test_resolve_runtime_provider_openrouter_ignores_codex_config_base_url() -> None:
    resolved = resolve_runtime_provider(
        requested="openrouter",
        config={
            "model": {
                "provider": "openai-codex",
                "base_url": "https://chatgpt.com/backend-api/codex",
            }
        },
        env={},
    )

    assert resolved["provider"] == "openrouter"
    assert resolved["base_url"] == OPENROUTER_BASE_URL


def test_resolve_runtime_provider_auto_uses_custom_config_base_url() -> None:
    resolved = resolve_runtime_provider(
        requested="auto",
        config={"model": {"provider": "auto", "base_url": "https://custom.example/v1/"}},
        env={},
    )

    assert resolved["provider"] == "openrouter"
    assert resolved["base_url"] == "https://custom.example/v1"


def test_named_custom_provider_uses_saved_credentials() -> None:
    resolved = resolve_runtime_provider(
        requested="custom:local",
        config={
            "custom_providers": [
                {
                    "name": "Local",
                    "base_url": "http://1.2.3.4:1234/v1",
                    "api_key": "local-provider-key",
                }
            ]
        },
        env={},
    )

    assert resolved["provider"] == "openrouter"
    assert resolved["base_url"] == "http://1.2.3.4:1234/v1"
    assert resolved["api_key"] == "local-provider-key"
    assert resolved["source"] == "custom_provider:Local"


def test_get_codex_model_ids_reads_config_and_cache(tmp_path: Path, monkeypatch) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text('model = "gpt-5.4"\n', encoding="utf-8")
    (codex_home / "models_cache.json").write_text(
        json.dumps(
            {
                "models": [
                    {"slug": "gpt-5.2-codex", "priority": 2},
                    {"slug": "gpt-5.1-codex-mini", "priority": 3},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    models = get_codex_model_ids()

    assert models[0] == "gpt-5.4"
    assert "gpt-5.2-codex" in models
    assert "gpt-5.3-codex" in models
    assert "gpt-5.3-codex-spark" in models


def test_copilot_model_api_mode_prefers_responses_for_gpt5() -> None:
    assert copilot_model_api_mode("gpt-5.4") == "codex_responses"
    assert copilot_model_api_mode("claude-sonnet-4.6") == "chat_completions"

