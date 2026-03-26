"""Hermes-style compatibility facade for provider/auth/runtime contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .auth import AuthStore
from .copilot_auth import copilot_device_code_login, save_copilot_token_to_auth
from .models import list_available_providers
from .runtime_provider import resolve_runtime_provider


def resolve_runtime_contract(
    *,
    requested: str | None = None,
    config: dict[str, Any] | None = None,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve runtime provider details through a stable facade."""
    return resolve_runtime_provider(requested=requested, config=config, home=home, env=env)


def list_providers_contract(
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """List provider capabilities/auth status through stable facade."""
    return list_available_providers(home=home, env=env, config=config)


def copilot_login_contract(*, home: Path | None = None) -> bool:
    """Run device-code login and persist token; return True on success."""
    token = copilot_device_code_login()
    if not token:
        return False
    save_copilot_token_to_auth(AuthStore(home=home), token)
    return True

