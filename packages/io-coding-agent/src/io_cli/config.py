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
        "provider": "auto",
        "default": "anthropic/claude-opus-4.6",
        "base_url": "",
        "api_mode": "",
    },
    "toolsets": ["io-cli"],
    "agent": {
        "max_turns": 90,
    },
    "terminal": {
        "backend": "local",
        "cwd": ".",
        "timeout": 180,
        "persistent_shell": True,
        "docker_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "docker_mount_cwd_to_workspace": False,
        "docker_forward_env": [],
        "singularity_image": "docker://python:3.11-slim",
        "modal_image": "debian_slim",
        "daytona_image": "python:3.11",
        "container_cpu": 1,
        "container_memory": 5120,
        "container_disk": 51200,
        "container_persistent": True,
        "ssh_host": "",
        "ssh_user": "",
        "ssh_port": 22,
        "ssh_key": "",
    },
    "browser": {
        "inactivity_timeout": 120,
        "record_sessions": False,
    },
    "web": {
        "backend": "local",
        "timeout": 20,
        "max_extract_chars": 5000,
        "user_agent": "IO Agent/0.1.2",
    },
    "checkpoints": {
        "enabled": True,
        "max_snapshots": 50,
    },
    "compression": {
        "enabled": True,
        "threshold": 0.5,
        "summary_model": "google/gemini-3-flash-preview",
        "summary_provider": "auto",
        "summary_base_url": "",
    },
    "smart_model_routing": {
        "enabled": False,
        "max_simple_chars": 160,
        "max_simple_words": 28,
        "cheap_model": {},
    },
    "auxiliary": {
        key: {"provider": "auto", "model": "", "base_url": "", "api_key": ""}
        for key in (
            "vision",
            "web_extract",
            "compression",
            "session_search",
            "skills_hub",
            "approval",
            "mcp",
            "flush_memories",
        )
    },
    "display": {
        "compact": False,
        "personality": "operator",
        "resume_display": "full",
        "bell_on_complete": False,
        "show_reasoning": False,
        "streaming": False,
        "show_cost": False,
        "skin": "default",
    },
    "privacy": {
        "redact_pii": False,
    },
    "security": {
        "website_blocklist": {
            "enabled": False,
            "domains": [],
            "shared_files": [],
        },
    },
    "gateway": {
        "enabled": False,
    },
    "nuggets": {
        "auto_promote": True,
    },
    "skills": {
        "auto_load": True,
        "disabled": [],
        "platform_disabled": {},
    },
    "platform_toolsets": {
        "cli": ["io-cli"],
        "telegram": ["io-telegram"],
        "discord": ["io-discord"],
        "slack": ["io-slack"],
        "whatsapp": ["io-whatsapp"],
        "signal": ["io-signal"],
        "email": ["io-email"],
        "sms": ["io-sms"],
        "homeassistant": ["io-homeassistant"],
        "dingtalk": ["io-dingtalk"],
        "webhook": ["io-cli"],
    },
    "custom_providers": [],
}


def get_io_home() -> Path:
    return Path(os.getenv("IO_HOME", Path.home() / ".io"))


def get_config_path(home: Path | None = None) -> Path:
    return ensure_io_home(home) / "config.yaml"


def get_env_path(home: Path | None = None) -> Path:
    return ensure_io_home(home) / ".env"


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _secure_dir(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _ensure_default_soul(home: Path) -> None:
    soul_path = home / "SOUL.md"
    if soul_path.exists():
        return
    soul_path.write_text(DEFAULT_SOUL_MD, encoding="utf-8")
    _secure_file(soul_path)


def ensure_io_home(home: Path | None = None) -> Path:
    home = home or get_io_home()
    directories = (
        home,
        home / "cron",
        home / "logs",
        home / "memories",
        home / "skills",
        home / "skins",
        home / "gateway",
        home / "pairing",
        home / "sandboxes",
        home / "agent",
        home / "agent" / "sessions",
        home / "agent" / "extensions",
    )
    for path in directories:
        path.mkdir(parents=True, exist_ok=True)
        _secure_dir(path)

    _ensure_default_soul(home)

    config_path = home / "config.yaml"
    if not config_path.exists():
        config_path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
        _secure_file(config_path)

    env_path = home / ".env"
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")
        _secure_file(env_path)

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
    _secure_file(config_path)
    return config_path


def _walk_path(config: dict[str, Any], path: str, *, create: bool = False) -> tuple[dict[str, Any], str]:
    cursor = config
    parts = [segment for segment in path.split(".") if segment]
    if not parts:
        raise ValueError("Config path cannot be empty.")
    for segment in parts[:-1]:
        value = cursor.get(segment)
        if not isinstance(value, dict):
            if not create:
                raise KeyError(path)
            value = {}
            cursor[segment] = value
        cursor = value
    return cursor, parts[-1]


def get_config_value(config: dict[str, Any], path: str) -> Any:
    cursor: Any = config
    for segment in [segment for segment in path.split(".") if segment]:
        if not isinstance(cursor, dict) or segment not in cursor:
            raise KeyError(path)
        cursor = cursor[segment]
    return cursor


def set_config_value(config: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    parent, leaf = _walk_path(config, path, create=True)
    parent[leaf] = value
    return config


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
