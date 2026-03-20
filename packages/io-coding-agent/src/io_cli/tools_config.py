"""IO-style tool configuration compatibility layer for IO."""

from __future__ import annotations

from typing import Any

from .config import load_config, save_config
from .toolsets import available_toolsets, enabled_toolsets_for_platform, set_toolset_enabled


CONFIGURABLE_TOOLSETS = [
    (spec.name, spec.label, spec.description)
    for spec in available_toolsets()
]


def get_platform_toolsets(config: dict[str, Any], platform: str = "cli") -> list[str]:
    return enabled_toolsets_for_platform(config, platform)


def save_platform_toolsets(config: dict[str, Any], toolsets: list[str], platform: str = "cli") -> dict[str, Any]:
    current = enabled_toolsets_for_platform(config, platform)
    for toolset in list(current):
        if toolset not in toolsets:
            set_toolset_enabled(config, toolset, False, platform=platform)
    for toolset in toolsets:
        set_toolset_enabled(config, toolset, True, platform=platform)
    save_config(config)
    return config


def toolsets_command(platform: str = "cli") -> list[dict[str, Any]]:
    config = load_config()
    enabled = set(enabled_toolsets_for_platform(config, platform))
    rows = []
    for name, label, description in CONFIGURABLE_TOOLSETS:
        rows.append(
            {
                "name": name,
                "label": label,
                "description": description,
                "enabled": name in enabled,
                "platform": platform,
            }
        )
    return rows
