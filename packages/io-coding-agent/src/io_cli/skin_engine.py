"""IO CLI skin/theme engine.

Ported in spirit from IO' data-driven skin system, but adapted to IO's
current package graph and Rich theme primitives.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from io_tui import Theme

from .config import ensure_io_home, load_config, save_config

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SkinConfig:
    name: str
    description: str = ""
    colors: dict[str, str] = field(default_factory=dict)
    spinner: dict[str, Any] = field(default_factory=dict)
    branding: dict[str, str] = field(default_factory=dict)
    tool_prefix: str = "Φ"
    tool_emojis: dict[str, str] = field(default_factory=dict)
    banner_logo: str = ""
    banner_hero: str = ""

    def get_color(self, key: str, fallback: str = "") -> str:
        return self.colors.get(key, fallback)

    def get_branding(self, key: str, fallback: str = "") -> str:
        return self.branding.get(key, fallback)

    def get_spinner_list(self, key: str) -> list[str]:
        value = self.spinner.get(key, [])
        return [str(item) for item in value] if isinstance(value, list) else []


IO_AGENT_LOGO = """[bold #FFD700]         ⠘⠛⠛⢿⣿⣿⣿⠟⠉⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢈⣿⣟⡁⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#FFBF00]⠀⠀⠀⠀⠀⠀⣠⣴⡶⠞⠛⠛⢻⣿⡏⠀⢈⡉⠛⠻⢶⣶⣤⡀⠀⠀⠀⠀⠀⠀[/]
[#CD7F32]⠀⠀⠀⠀⣰⣾⡿⠋⠀⠀⠀⠀⠀⣿⣧⣄⠀⠀⠀⠀⠢⡙⢻⣿⣷⡄⠀⠀⠀⠀[/]
[#CD7F32]⠀⠀⠀⣼⣿⠏⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠈⢦⣿⡇⣿⡄⠀⠀⠀[/]
[#FFD700]⠀⠀⢸⣿⡿⢠⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠀⠘⣿⣇⣿⣧⠀⠀⠀[/]
[#FFD700]⠀⠀⢸⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⣿⣿⠛⠋⠀⠀⠀[/]
[#FFBF00]⠀⠀⠸⠿⠟⠿⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠀⢸⣿⠇⠀⠀⠀⠀⠀[/]
[#FFBF00]⠀⠀⠀⠣⠀⠀⠰⢣⡀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⢀⣾⠏⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠁⠀⠀⠀⠑⢦⣀⡀⢀⣿⣿⠉⣀⠀⣀⣠⡴⠟⠁⠀⠀⠀⠀⠀⠀⠀[/]
[#B8860B]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⢛⣿⣿⠏⢈⡉⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#DAA520]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⡿⠋⠀⡰⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀[/]
[#CD7F32]         ⠰⠶⠚⠉⠀⠀⠀⠀⠉⠓⠶[/]"""

IO_PHI_HERO = """[bold #FFD700]⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣻⣿⡿⠃⠀⠀⠀⠀⠀⠀⠀⠀⣀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣤⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⡿[/]
[bold #FFD700]⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣽⣿⡿⠃⠀⠀⠀⠀⠀⣀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣄⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⣦⣤⣾⣿⣿⣿⣿⣿⣿⣿⣷[/]
[#FFBF00]⣿⣿⣿⣿⣿⣿⣿⣿⣿⣽⣿⣧⣿⣿⡿⣻⣿⣿⡿⠋⠀⠀⠀⠀⢀⣤⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣄⠀⠀⠀⠀⠀⠀⠀⠀⢀⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿[/]
[#FFBF00]⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⣿⣿⡿⣼⡿⣻⣾⣿⣿⢟⡕⠀⠀⠀⢀⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣤⡀⠀⠀⠀⠀⠀⠘⢸⡷⣿⣿⣿⣿⣿⠟⠷⣿⣿⣿⣿[/]
[#FFD700]⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢷⢟⣼⣿⣿⡟⣱⡟⡀⠀⠀⣴⡿⠿⠛⠛⠛⠻⠿⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡄⠀⠀⠀⠀⢰⣷⣯⣽⡿⢛⡿⠁⢀⣺⣿⣿⣿⣿⣿[/]
[#FFD700]⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢠⣿⣿⣿⡿⣱⠟⣼⠃⠀⢸⣿⣿⣿⣿⣿⣷⣶⣤⣄⣀⠉⠉⠻⣿⣿⣿⣿⣿⣿⣿⡟⠛⠉⠉⠉⣀⣀⣤⣤⣤⣬⣽⣿⣿⡀⠀⠀⠀⠘⣯⣥⣴⣥⣀⣿⣿⣿⣿⣿⣿⣿[/]
[#FFBF00]⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣟⣿⣿⣿⣰⣇⡞⣱⠱⡀⢸⣿⣿⠿⠟⠻⠿⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣶⣿⣿⣿⣿⣿⣿⣿⢿⣿⣿⣿⣿⡇⠀⢀⣠⡱⡉⢻⣿⣿⣿⣿⣿⣿⣿⣷⡝⣿[/]
[#FFBF00]⣿⣿⣿⣿⣿⣿⣿⡟⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢇⣿⡄⡄⢸⣦⣄⠠⣤⣶⡀⠀⠤⠀⠉⠻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⠷⠚⢉⡉⠉⠉⢀⡈⠉⠛⢛⣻⡇⢠⡟⣭⡇⠀⣿⢠⣿⣿⣿⢿⣿⣿⣿⣿⣧[/]
[#CD7F32]⣿⣿⣿⣿⣿⣿⣿⣾⣿⣿⣿⣿⣿⡿⢟⣿⣾⠟⣼⣿⢹⡃⢸⣿⣿⣷⣝⣿⣷⣄⣀⣀⣠⣿⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣵⣾⣄⠀⠀⠀⣠⣾⢟⣠⣾⣿⣿⡇⢪⡝⣿⡇⢸⡇⢸⣿⣿⣷⣿⡿⠻⢿⡍⠉[/]
[#CD7F32]⣿⣿⠟⠉⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢸⣿⣿⡧⠳⡄⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣾⣿⣿⣿⣿⣿⣿⣿⡰⢸⣷⠟⠀⣾⠇⣺⣿⣿⣿⠟⠀⠀⠀⠉⠀[/]
[#FFD700]⠋⠀⠀⠀⠈⠙⢿⣿⣿⣿⣿⣿⣫⣿⣿⣿⣿⣌⣽⣶⣿⢗⡉⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⣴⡿⡱⠀⠰⣿⠻⣿⣿⣿⡟⠀⠀⠀⡰⠒⢀⣴⣶[/]
[#FFD700]⠀⠀⠀⠀⠀⠀⠀⠉⠛⢿⣿⣿⣿⣿⣿⣿⣿⣿⠿⣻⣱⣯⣤⣌⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠟⠿⠻⡄⢀⣀⣀⡦⠃⠈⣉⣩⡛⣦⣤⣦⣤⣴⣿⣿⣿[/]
[#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠉⠻⣿⣿⣿⠿⣫⣵⣿⣿⣯⣩⡿⠿⠚⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠏⡀⠀⠀⠿⢸⢿⠂⠀⢀⣾⠟⢿⣧⣬⣿⣿⣿⣿⣿⣿⣿[/]
[#FFBF00]⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣈⣽⣶⣿⣿⣿⣿⣿⣿⣿⣷⣶⣿⣜⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠋⠂⠐⠀⠖⠀⠀⠈⠄⠰⢇⠀⠀⠒⣿⣿⣿⣿⣿⣿⣿⣿⣿[/]
[#CD7F32]⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⡹⣿⣿⣿⣿⣿⣿⣟⣛⣛⡛⠛⠛⠛⠛⠛⢿⣿⣿⣿⣿⣿⣿⣿⠟⠁⠀⠂⠀⠀⢀⣠⣤⣤⢄⠀⠒⠂⢀⠀⠿⡛⣿⣿⣿⣿⣿⣿⣿[/]"""


_BUILTIN_SKINS: dict[str, dict[str, Any]] = {
    "default": {
        "name": "default",
        "description": "Classic IO gold and bronze",
        "colors": {
            "banner_border": "#CD7F32",
            "banner_title": "#FFD700",
            "banner_accent": "#FFBF00",
            "banner_dim": "#B8860B",
            "banner_text": "#FFF8DC",
            "ui_accent": "#FFBF00",
            "ui_label": "#4dd0e1",
            "ui_ok": "#4caf50",
            "ui_error": "#ef5350",
            "ui_warn": "#ffa726",
            "prompt": "#FFF8DC",
            "input_rule": "#CD7F32",
            "response_border": "#FFD700",
            "session_label": "#DAA520",
            "session_border": "#8B8682",
        },
        "branding": {
            "agent_name": "IO Agent",
            "welcome": "Welcome to IO. Type your message or /help for commands.",
            "goodbye": "Goodbye! Φ",
            "response_label": " Φ IO ",
            "prompt_symbol": "Φ ",
            "help_header": "(Φ) Available Commands",
        },
        "tool_prefix": "Φ",
        "banner_logo": IO_AGENT_LOGO,
        "banner_hero": IO_PHI_HERO,
    },
    "ares": {
        "name": "ares",
        "description": "Crimson and bronze war-room variant",
        "colors": {
            "banner_border": "#9F1C1C",
            "banner_title": "#C7A96B",
            "banner_accent": "#DD4A3A",
            "banner_dim": "#6B1717",
            "banner_text": "#F1E6CF",
            "ui_accent": "#DD4A3A",
            "ui_label": "#C7A96B",
            "ui_ok": "#4caf50",
            "ui_error": "#ef5350",
            "ui_warn": "#ffa726",
            "prompt": "#F1E6CF",
            "input_rule": "#9F1C1C",
            "response_border": "#C7A96B",
            "session_label": "#C7A96B",
            "session_border": "#6E584B",
        },
        "branding": {
            "agent_name": "IO Ares",
            "welcome": "Welcome to IO Ares.",
            "goodbye": "Farewell. Φ",
            "response_label": " ΦΦ Φ IO ",
            "prompt_symbol": "ΦΦ Φ ",
            "help_header": "(ΦΦ) Available Commands",
        },
        "tool_prefix": "ΦΦ",
        "banner_logo": IO_AGENT_LOGO.replace("#FFD700", "#C7A96B").replace("#FFBF00", "#DD4A3A"),
        "banner_hero": IO_PHI_HERO.replace("Φ", "ΦΦ"),
    },
    "mono": {
        "name": "mono",
        "description": "Clean grayscale monochrome",
        "colors": {
            "banner_border": "#555555",
            "banner_title": "#e6edf3",
            "banner_accent": "#aaaaaa",
            "banner_dim": "#444444",
            "banner_text": "#c9d1d9",
            "ui_accent": "#aaaaaa",
            "ui_label": "#888888",
            "ui_ok": "#888888",
            "ui_error": "#cccccc",
            "ui_warn": "#aaaaaa",
            "prompt": "#c9d1d9",
            "input_rule": "#555555",
            "response_border": "#aaaaaa",
            "session_label": "#aaaaaa",
            "session_border": "#666666",
        },
        "branding": {
            "agent_name": "IO Mono",
            "welcome": "Welcome to IO Mono.",
            "goodbye": "Goodbye.",
            "response_label": " IO ",
            "prompt_symbol": "> ",
            "help_header": "Commands",
        },
        "tool_prefix": "Φ",
        "banner_logo": IO_AGENT_LOGO.replace("#FFD700", "#e6edf3").replace("#FFBF00", "#aaaaaa").replace("#CD7F32", "#888888"),
        "banner_hero": IO_PHI_HERO.replace("#CD7F32", "#888888").replace("#FFBF00", "#aaaaaa").replace("#FFD700", "#e6edf3"),
    },
    "slate": {
        "name": "slate",
        "description": "Cool blue operator slate",
        "colors": {
            "banner_border": "#355c7d",
            "banner_title": "#7ec8e3",
            "banner_accent": "#5ea3c5",
            "banner_dim": "#547c99",
            "banner_text": "#e7f6ff",
            "ui_accent": "#7ec8e3",
            "ui_label": "#9fd6ea",
            "ui_ok": "#68b984",
            "ui_error": "#d95d5d",
            "ui_warn": "#f2c57c",
            "prompt": "#e7f6ff",
            "input_rule": "#355c7d",
            "response_border": "#7ec8e3",
            "session_label": "#9fd6ea",
            "session_border": "#547c99",
        },
        "branding": {
            "agent_name": "IO Slate",
            "welcome": "Welcome to IO Slate.",
            "goodbye": "Goodbye! Φ",
            "response_label": " Φ Slate ",
            "prompt_symbol": "Φ ",
            "help_header": "(Φ) Commands",
        },
        "tool_prefix": "Φ",
        "banner_logo": IO_AGENT_LOGO.replace("#FFD700", "#7ec8e3").replace("#FFBF00", "#5ea3c5").replace("#CD7F32", "#355c7d"),
        "banner_hero": IO_PHI_HERO.replace("#CD7F32", "#355c7d").replace("#FFBF00", "#5ea3c5").replace("#FFD700", "#7ec8e3"),
    },
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _skin_dir(home: Path | None = None) -> Path:
    return ensure_io_home(home) / "skins"


def list_skins(home: Path | None = None) -> list[SkinConfig]:
    seen = set()
    skins = []
    for name in sorted(_BUILTIN_SKINS):
        skins.append(load_skin_config(name, home=home))
        seen.add(name)
    for path in sorted(_skin_dir(home).glob("*.yaml")):
        if path.stem in seen:
            continue
        skins.append(load_skin_config(path.stem, home=home))
    return skins


def load_skin_config(name: str = "default", home: Path | None = None) -> SkinConfig:
    if not name:
        name = "default"
    base = _BUILTIN_SKINS["default"]
    payload = dict(base)
    if name in _BUILTIN_SKINS:
        payload = _deep_merge(base, _BUILTIN_SKINS[name])
    else:
        path = _skin_dir(home) / f"{name}.yaml"
        if path.exists():
            try:
                user_payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                if isinstance(user_payload, dict):
                    payload = _deep_merge(base, user_payload)
            except Exception as exc:
                logger.warning("Failed to load skin %s: %s", name, exc)
    return SkinConfig(
        name=str(payload.get("name", name)),
        description=str(payload.get("description", "")),
        colors=dict(payload.get("colors", {})),
        spinner=dict(payload.get("spinner", {})),
        branding=dict(payload.get("branding", {})),
        tool_prefix=str(payload.get("tool_prefix", "Φ")),
        tool_emojis=dict(payload.get("tool_emojis", {})),
        banner_logo=str(payload.get("banner_logo", IO_AGENT_LOGO)),
        banner_hero=str(payload.get("banner_hero", IO_PHI_HERO)),
    )


def get_active_skin(home: Path | None = None) -> SkinConfig:
    config = load_config(home)
    display = config.get("display", {})
    if isinstance(display, dict):
        name = str(display.get("skin", "default") or "default")
    else:
        name = "default"
    return load_skin_config(name, home=home)


def set_active_skin(name: str, home: Path | None = None) -> None:
    config = load_config(home)
    config.setdefault("display", {})
    config["display"]["skin"] = name
    save_config(config, home)


def _to_theme(skin: SkinConfig) -> Theme:
    base = asdict(Theme())
    labels = dict(base["labels"])
    response_label = skin.get_branding("response_label")
    if response_label:
        labels["assistant"] = response_label.strip()
    base.update(
        {
            "banner_border": skin.get_color("banner_border", base["banner_border"]),
            "banner_title": skin.get_color("banner_title", base["banner_title"]),
            "banner_text": skin.get_color("banner_text", base["banner_text"]),
            "accent": skin.get_color("ui_accent", base["accent"]),
            "response_border": skin.get_color("response_border", base["response_border"]),
            "prompt_symbol": skin.get_branding("prompt_symbol", base["prompt_symbol"]),
            "labels": labels,
        }
    )
    return Theme(**base)


class SkinEngine:
    def __init__(self, home: Path | None = None) -> None:
        self.home = ensure_io_home(home)

    def load(self, name: str | None = None) -> Theme:
        skin = load_skin_config(name, home=self.home) if name else get_active_skin(home=self.home)
        return _to_theme(skin)

    def load_skin(self, name: str | None = None) -> SkinConfig:
        return load_skin_config(name, home=self.home) if name else get_active_skin(home=self.home)
