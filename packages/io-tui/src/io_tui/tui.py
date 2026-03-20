"""Generic prompt_toolkit helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from .display import banner, print_transcript, render_message
from .theme import Theme

if TYPE_CHECKING:
    from prompt_toolkit.auto_suggest import AutoSuggest
    from prompt_toolkit.completion import Completer


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
    ) -> str:
        """Read one line. Optional *completer* / *auto_suggest* enable tab menus (Hermes-style REPL)."""
        kwargs: dict[str, Any] = {"history": self.history}
        if completer is not None:
            kwargs["completer"] = completer
            kwargs["complete_while_typing"] = complete_while_typing
        if auto_suggest is not None:
            kwargs["auto_suggest"] = auto_suggest
        session: PromptSession[str] = PromptSession(**kwargs)
        return session.prompt(message or self.theme.prompt_symbol)
