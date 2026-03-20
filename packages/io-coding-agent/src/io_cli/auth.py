"""Auth helpers for the CLI."""

from __future__ import annotations

from pathlib import Path

from io_ai import AuthStore

from .config import load_config


def auth_status(home: Path | None = None) -> dict[str, object]:
    config = load_config(home)
    store = AuthStore(home=home)
    active = store.active_provider()
    providers = {
        provider: store.provider_status(provider, config=config)
        for provider in store.list_known_providers()
        if provider != "custom"
    }
    custom_providers = config.get("custom_providers", [])
    if isinstance(custom_providers, list):
        for entry in custom_providers:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "") or "").strip()
            if not name:
                continue
            status = store.provider_status(f"custom:{name}", config=config)
            providers[status["provider"]] = status
    return {"active_provider": active, "providers": providers}
