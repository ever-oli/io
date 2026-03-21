"""Generic prompt_toolkit helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console

from .display import banner, print_transcript, render_message
from .theme import Theme

if TYPE_CHECKING:
    from prompt_toolkit.auto_suggest import AutoSuggest
    from prompt_toolkit.completion import Completer

ReplMultilineMode = Literal["meta_submit", "single_ctrl_j", "buffer"]


def _ctrl_j_newline_bindings() -> KeyBindings:
    """Enter submits; Ctrl-J inserts newline (Hermes/pi-style single-line shell feel)."""
    kb = KeyBindings()

    @kb.add("c-j")
    def _insert_newline(event: object) -> None:
        event.current_buffer.insert_text("\n")  # type: ignore[attr-defined]

    return kb


def read_multiline_buffer(console: Console, *, sentinel: str, prompt: str = "> ") -> str:
    """Read lines until a line equals *sentinel* (strip compared). For paste-heavy input."""
    console.print(
        f"[dim]Buffer mode: each line is one [bold]Enter[/]. "
        f"Type [bold]{sentinel}[/] alone on a line to submit.[/]"
    )
    lines: list[str] = []
    end = sentinel.strip()
    while True:
        try:
            line = input(prompt)
        except EOFError:
            break
        if line.strip() == end:
            break
        lines.append(line)
    return "\n".join(lines)


@dataclass
class TerminalUI:
    console: Console = field(default_factory=Console)
    theme: Theme = field(default_factory=Theme)
    history: InMemoryHistory = field(default_factory=InMemoryHistory)

    def render_banner(self) -> None:
        self.console.print(banner(self.theme))

    def render_message(self, role: str, content: Any) -> None:
        self.console.print(render_message(role, content, theme=self.theme))

    def render_transcript(self, messages: list[dict[str, Any]]) -> None:
        print_transcript(messages, console=self.console, theme=self.theme)

    def prompt(
        self,
        message: str | None = None,
        *,
        completer: Completer | None = None,
        auto_suggest: AutoSuggest | None = None,
        complete_while_typing: bool = True,
        multiline: bool = False,
        multiline_mode: ReplMultilineMode = "meta_submit",
        buffer_sentinel: str = "END",
    ) -> str:
        """Read input.

        * **meta_submit** — ``multiline=True``: Enter newline, Esc/Meta+Enter submit.
        * **single_ctrl_j** — one logical prompt: Enter submits, **Ctrl-J** newline.
        * **buffer** — simple ``input()`` loop until *buffer_sentinel* line.
        """
        if multiline_mode == "buffer":
            return read_multiline_buffer(self.console, sentinel=buffer_sentinel)

        kwargs: dict[str, Any] = {"history": self.history}
        if completer is not None:
            kwargs["completer"] = completer
            kwargs["complete_while_typing"] = complete_while_typing
        if auto_suggest is not None:
            kwargs["auto_suggest"] = auto_suggest

        if multiline_mode == "single_ctrl_j" and multiline:
            kwargs["multiline"] = False
            kwargs["key_bindings"] = _ctrl_j_newline_bindings()
        elif multiline_mode == "meta_submit" and multiline:
            kwargs["multiline"] = True
            kwargs["prompt_continuation"] = lambda width, line_number, is_soft_wrap: "." * min(3, width) + "\n"

        session: PromptSession[str] = PromptSession(**kwargs)
        return session.prompt(message or self.theme.prompt_symbol)
