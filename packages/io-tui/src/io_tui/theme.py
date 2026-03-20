"""Theme primitives for terminal rendering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Theme:
    banner_border: str = "#7b1f1e"
    banner_title: str = "#b58c4a"
    banner_text: str = "#fff8e5"
    accent: str = "#ffb700"
    response_border: str = "#c87837"
    prompt_symbol: str = "Φ "
    labels: dict[str, str] = field(
        default_factory=lambda: {
            "user": "USER",
            "assistant": "Φ IO",
            "tool": "TOOL",
            "system": "SYSTEM",
        }
    )

