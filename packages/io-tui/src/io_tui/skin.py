"""Skin engine for IO TUI aesthetics.

Theming system for Rich terminal displays.
Inspired by Gauss's skin_engine but simplified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Skin:
    """Color theme for TUI."""

    # Status colors
    success: str = "#8B9B7A"  # Green
    error: str = "#B07070"  # Red
    warning: str = "#C8A85C"  # Yellow
    info: str = "#5B8DB8"  # Blue

    # UI accents
    accent: str = "#C8C0B0"  # Beige
    dim: str = "#6B6B60"  # Gray
    highlight: str = "#9B8B7A"  # Brown

    # Borders and structure
    border: str = "#5B6B4F"  # Dark green
    title: str = "#C8C0B0"  # Light beige
    text: str = "#C8C0B0"  # Default text

    # Swarm-specific
    running: str = "#C8A85C"  # Yellow
    queued: str = "#6B6B60"  # Gray
    complete: str = "#8B9B7A"  # Green
    failed: str = "#B07070"  # Red
    cancelled: str = "#6B6B60"  # Gray

    def get(self, key: str, default: str = "") -> str:
        """Get color by key."""
        return getattr(self, key, default)


# Predefined skins
SKINS = {
    "default": Skin(),
    "dark": Skin(
        success="#4ADE80",
        error="#F87171",
        warning="#FBBF24",
        info="#60A5FA",
        accent="#A78BFA",
        dim="#6B7280",
        highlight="#C084FC",
        border="#4B5563",
        title="#F3F4F6",
        text="#E5E7EB",
        running="#FBBF24",
        queued="#6B7280",
        complete="#4ADE80",
        failed="#F87171",
        cancelled="#6B7280",
    ),
    "light": Skin(
        success="#16A34A",
        error="#DC2626",
        warning="#D97706",
        info="#2563EB",
        accent="#7C3AED",
        dim="#6B7280",
        highlight="#9333EA",
        border="#9CA3AF",
        title="#111827",
        text="#374151",
        running="#D97706",
        queued="#9CA3AF",
        complete="#16A34A",
        failed="#DC2626",
        cancelled="#9CA3AF",
    ),
    "gauss": Skin(
        success="#8B9B7A",
        error="#B07070",
        warning="#C8A85C",
        info="#5B8DB8",
        accent="#C8C0B0",
        dim="#6B6B60",
        highlight="#9B8B7A",
        border="#5B6B4F",
        title="#C8C0B0",
        text="#C8C0B0",
        running="#C8A85C",
        queued="#6B6B60",
        complete="#8B9B7A",
        failed="#B07070",
        cancelled="#6B6B60",
    ),
}


class SkinEngine:
    """Manages active skin and provides color lookups."""

    _instance: Optional[SkinEngine] = None

    def __new__(cls) -> SkinEngine:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skin = SKINS["default"]
            cls._instance._name = "default"
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset to default skin."""
        cls._instance = None

    @property
    def skin(self) -> Skin:
        """Get current skin."""
        return self._skin

    @skin.setter
    def skin(self, value: Skin) -> None:
        """Set active skin."""
        self._skin = value

    def set_skin(self, name: str) -> bool:
        """Set skin by name."""
        if name in SKINS:
            self._skin = SKINS[name]
            self._name = name
            return True
        return False

    def get_color(self, key: str, default: str = "") -> str:
        """Get color for key."""
        return self._skin.get(key, default)

    def get_status_color(self, status: str) -> str:
        """Get color for task status."""
        mapping = {
            "running": self._skin.running,
            "queued": self._skin.queued,
            "complete": self._skin.complete,
            "failed": self._skin.failed,
            "cancelled": self._skin.cancelled,
        }
        return mapping.get(status, self._skin.text)

    @property
    def name(self) -> str:
        """Get current skin name."""
        return self._name

    def list_skins(self) -> list[str]:
        """List available skin names."""
        return list(SKINS.keys())


# Global accessor
def get_skin() -> Skin:
    """Get active skin."""
    return SkinEngine().skin


def set_skin(name: str) -> bool:
    """Set skin by name."""
    return SkinEngine().set_skin(name)
