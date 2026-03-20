"""Auth helpers for the CLI."""

from __future__ import annotations

from pathlib import Path

from io_ai import AuthStore


def auth_status(home: Path | None = None) -> dict[str, bool]:
    store = AuthStore(home=home)
    return {
        "openai": bool(store.get_api_key("openai")),
        "openrouter": bool(store.get_api_key("openrouter")),
        "anthropic": bool(store.get_api_key("anthropic")),
    }

