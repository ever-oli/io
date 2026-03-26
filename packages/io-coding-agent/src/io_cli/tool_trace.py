"""Hermes-style tool trace formatting for terminal/gateway visibility."""

from __future__ import annotations

import json
from typing import Any

_REDACT_KEYS = ("token", "secret", "password", "api_key", "apikey", "auth", "cookie")
_TOOL_KINDS = ("read", "search", "patch", "terminal", "memory", "default")
_TRACE_ICON_PRESETS: dict[str, dict[str, str]] = {
    "emoji": {
        "read": "📖",
        "search": "🔎",
        "patch": "🔧",
        "terminal": "💻",
        "memory": "🧠",
        "default": "🛠️",
    },
    "neo": {
        "read": "📚",
        "search": "🕵️",
        "patch": "🧩",
        "terminal": "⌨️",
        "memory": "💾",
        "default": "⚙️",
    },
    "ascii": {
        "read": "R>",
        "search": "S>",
        "patch": "P>",
        "terminal": "T>",
        "memory": "M>",
        "default": "*>",
    },
}


def _redact(value: Any, *, key_name: str = "") -> Any:
    if any(flag in key_name.lower() for flag in _REDACT_KEYS):
        return "***"
    if isinstance(value, dict):
        return {str(k): _redact(v, key_name=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, key_name=key_name) for v in value]
    return value


def _tool_kind(tool_name: str) -> str:
    name = str(tool_name or "").lower()
    if "read" in name:
        return "read"
    if "search" in name or "grep" in name or "rg" in name:
        return "search"
    if "patch" in name or "edit" in name or "write" in name:
        return "patch"
    if "terminal" in name or "bash" in name or "shell" in name:
        return "terminal"
    if "memory" in name:
        return "memory"
    return "default"


def tool_icon(tool_name: str, *, icon_preset: str = "emoji", icon_overrides: dict[str, str] | None = None) -> str:
    preset = _TRACE_ICON_PRESETS.get(str(icon_preset or "emoji").strip().lower(), _TRACE_ICON_PRESETS["emoji"])
    kind = _tool_kind(tool_name)
    icon = str(preset.get(kind, preset["default"]))
    overrides = icon_overrides if isinstance(icon_overrides, dict) else {}
    if kind in overrides and str(overrides[kind]).strip():
        return str(overrides[kind]).strip()
    if "default" in overrides and str(overrides["default"]).strip() and kind == "default":
        return str(overrides["default"]).strip()
    return icon


def should_trace_tool(tool_name: str, *, suppress_tools: list[str] | None = None) -> bool:
    name = str(tool_name or "").strip().lower()
    if not name:
        return False
    blocked = {str(item).strip().lower() for item in (suppress_tools or []) if str(item).strip()}
    return name not in blocked


def format_tool_trace_lines(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    mode: str = "compact",
    icon_preset: str = "emoji",
    icon_overrides: dict[str, str] | None = None,
    duration_seconds: float | None = None,
) -> list[str]:
    args = arguments if isinstance(arguments, dict) else {}
    redacted = _redact(args)
    keys = sorted(redacted.keys())
    mode_norm = str(mode or "compact").strip().lower()
    if mode_norm not in {"compact", "verbose"}:
        mode_norm = "compact"
    if mode_norm == "verbose":
        payload = json.dumps(redacted, ensure_ascii=False, indent=2, sort_keys=True)
        if len(payload) > 1200:
            payload = payload[:1197] + "..."
    else:
        payload = json.dumps(redacted, ensure_ascii=False)
        if len(payload) > 400:
            payload = payload[:397] + "..."
    suffix = ""
    if duration_seconds is not None:
        try:
            suffix = f" (+{float(duration_seconds):.2f}s)"
        except Exception:
            suffix = ""
    return [
        f"{tool_icon(tool_name, icon_preset=icon_preset, icon_overrides=icon_overrides)} {tool_name}({keys}){suffix}",
        payload,
    ]

