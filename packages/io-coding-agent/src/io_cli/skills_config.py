"""IO-style skills configuration compatibility layer for IO."""

from __future__ import annotations

from typing import Any

from .config import load_config, save_config
from .skills import discover_skills, set_skill_enabled


def get_disabled_skills(config: dict[str, Any], platform: str | None = None) -> set[str]:
    skills_cfg = config.get("skills", {})
    global_disabled = set(skills_cfg.get("disabled", []))
    if platform is None:
        return global_disabled
    platform_disabled = skills_cfg.get("platform_disabled", {}).get(platform)
    if platform_disabled is None:
        return global_disabled
    return set(platform_disabled)


def save_disabled_skills(config: dict[str, Any], disabled: set[str], platform: str | None = None) -> dict[str, Any]:
    config.setdefault("skills", {})
    if platform is None:
        config["skills"]["disabled"] = sorted(disabled)
    else:
        config["skills"].setdefault("platform_disabled", {})
        config["skills"]["platform_disabled"][platform] = sorted(disabled)
    save_config(config)
    return config


def list_all_skills(*, platform: str = "cli", cwd=None) -> list[dict[str, Any]]:
    return [skill.to_dict() for skill in discover_skills(platform=platform, cwd=cwd)]


def skills_command(*, platform: str = "cli", cwd=None) -> list[dict[str, Any]]:
    return list_all_skills(platform=platform, cwd=cwd)


def toggle_skill(name: str, enabled: bool, *, platform: str = "cli") -> dict[str, Any]:
    config = load_config()
    set_skill_enabled(config, name, enabled, platform=platform)
    save_config(config)
    return config
