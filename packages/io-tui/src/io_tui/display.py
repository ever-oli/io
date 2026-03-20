"""Rich-based transcript formatting."""

from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from .theme import Theme


def banner(theme: Theme | None = None) -> Panel:
    theme = theme or Theme()
    body = Text.assemble(
        ("Φ IO AGENT\n", theme.banner_title),
        ("Most Wanted Research", theme.banner_text),
    )
    return Panel(body, border_style=theme.banner_border)


def render_message(role: str, content: Any, *, theme: Theme | None = None) -> Panel:
    theme = theme or Theme()
    label = theme.labels.get(role, role.upper())
    text = Text(str(content))
    return Panel(text, title=label, border_style=theme.response_border)


def render_transcript(messages: list[dict[str, Any]], *, theme: Theme | None = None) -> Group:
    theme = theme or Theme()
    panels = [render_message(message.get("role", "message"), message.get("content", ""), theme=theme) for message in messages]
    return Group(*panels)


def print_transcript(messages: list[dict[str, Any]], *, console: Console | None = None, theme: Theme | None = None) -> None:
    console = console or Console()
    console.print(render_transcript(messages, theme=theme))

