"""YAML-backed theme loading."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from io_tui import Theme

from .config import ensure_io_home


class SkinEngine:
    def __init__(self, home: Path | None = None) -> None:
        self.home = ensure_io_home(home)

    def load(self, name: str = "default") -> Theme:
        path = self.home / "skins" / f"{name}.yaml"
        if not path.exists():
            return Theme()
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        colors = payload.get("colors", {})
        branding = payload.get("branding", {})
        base = asdict(Theme())
        labels = dict(base["labels"])
        if branding.get("response_label"):
            labels["assistant"] = branding["response_label"]
        base.update(
            {
                "banner_border": colors.get("banner_border", base["banner_border"]),
                "banner_title": colors.get("banner_title", base["banner_title"]),
                "banner_text": colors.get("banner_text", base["banner_text"]),
                "accent": colors.get("ui_accent", base["accent"]),
                "response_border": colors.get("response_border", base["response_border"]),
                "prompt_symbol": branding.get("prompt_symbol", base["prompt_symbol"]),
                "labels": labels,
            }
        )
        return Theme(**base)

