"""Configuration and home-directory management."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from .default_soul import DEFAULT_SOUL_MD


DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "mock",
        "default": "mock/io-test",
        "base_url": None,
    },
    "agent": {
        "max_turns": 8,
    },
    "toolsets": ["core"],
    "compression": {
        "enabled": True,
        "threshold_messages": 20,
        "keep_last": 8,
    },
}


def get_io_home() -> Path:
    return Path(os.getenv("IO_HOME", Path.home() / ".io"))


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def ensure_io_home(home: Path | None = None) -> Path:
    home = home or get_io_home()
    for path in (
        home,
        home / "cron",
        home / "logs",
        home / "memories",
        home / "skills",
        home / "skins",
        home / "agent",
        home / "agent" / "sessions",
        home / "agent" / "extensions",
    ):
        path.mkdir(parents=True, exist_ok=True)
    soul_path = home / "SOUL.md"
    if not soul_path.exists():
        soul_path.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
    config_path = home / "config.yaml"
    if not config_path.exists():
        config_path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
    env_path = home / ".env"
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
    return home


def load_config(home: Path | None = None) -> dict[str, Any]:
    home = ensure_io_home(home)
    config_path = home / "config.yaml"
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULT_CONFIG, data)


def save_config(config: dict[str, Any], home: Path | None = None) -> Path:
    home = ensure_io_home(home)
    config_path = home / "config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path


def load_env(home: Path | None = None) -> dict[str, str]:
    home = ensure_io_home(home)
    env_path = home / ".env"
    return {key: value for key, value in dotenv_values(env_path).items() if value is not None}


def load_soul(home: Path | None = None) -> str:
    home = ensure_io_home(home)
    return (home / "SOUL.md").read_text(encoding="utf-8")


def memory_snapshot(home: Path | None = None) -> str:
    home = ensure_io_home(home)
    memories = []
    for name in ("MEMORY.md", "USER.md"):
        path = home / "memories" / name
        if path.exists():
            contents = path.read_text(encoding="utf-8").strip()
            if contents:
                memories.append(f"# {name}\n{contents}")
    return "\n\n".join(memories).strip()

