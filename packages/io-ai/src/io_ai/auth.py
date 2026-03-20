"""Credential and token helpers for IO providers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


PROVIDER_ENV_KEYS = {
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


@dataclass
class AuthStore:
    home: Path | None = None
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def __post_init__(self) -> None:
        self.home = self.home or Path(os.getenv("IO_HOME", Path.home() / ".io"))

    @property
    def resolved_home(self) -> Path:
        assert self.home is not None
        return self.home

    @property
    def auth_path(self) -> Path:
        return self.resolved_home / "auth.json"

    @property
    def env_path(self) -> Path:
        return self.resolved_home / ".env"

    @property
    def config_path(self) -> Path:
        return self.resolved_home / "config.yaml"

    def load_auth(self) -> dict[str, Any]:
        if not self.auth_path.exists():
            return {}
        return json.loads(self.auth_path.read_text(encoding="utf-8"))

    def save_auth(self, payload: dict[str, Any]) -> None:
        self.resolved_home.mkdir(parents=True, exist_ok=True)
        self.auth_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def dotenv_values(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        return {key: value for key, value in dotenv_values(self.env_path).items() if value is not None}

    def get_api_key(self, provider: str) -> str | None:
        env_key = PROVIDER_ENV_KEYS.get(provider)
        if env_key and self.env.get(env_key):
            return self.env[env_key]

        dotenv_map = self.dotenv_values()
        if env_key and dotenv_map.get(env_key):
            return dotenv_map[env_key]

        auth_payload = self.load_auth()
        if provider in auth_payload and isinstance(auth_payload[provider], dict):
            token = auth_payload[provider].get("api_key") or auth_payload[provider].get("token")
            if token:
                return str(token)
        return None

    def headers_for(self, provider: str) -> dict[str, str]:
        token = self.get_api_key(provider)
        if not token:
            return {}
        if provider == "anthropic":
            return {"x-api-key": token, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {token}"}
