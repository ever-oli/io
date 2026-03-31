"""Interactive `/model` picker: one prompt + fuzzy Tab completion (slash-command style dropdown)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from io_ai import ModelRegistry, fuzzy_filter
from io_ai.types import ModelRef
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion

from .models import list_auth_available_model_refs


def _prompt_toolkit_in_thread() -> bool:
    """REPL slash handling uses ``asyncio.run()``; nested PT ``run()`` needs ``in_thread=True``."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


class _AuthModelCompleter(Completer):
    """Fuzzy-match configured-provider models; Tab / typing shows the same style of menu as slash commands."""

    def __init__(self, refs: list[ModelRef]) -> None:
        self._refs = refs

    def get_completions(self, document: Any, complete_event: Any) -> Any:
        text = document.text_before_cursor
        raw = text.strip()
        if not raw:
            candidates = self._refs[:80]
        else:
            candidates = fuzzy_filter(
                self._refs,
                raw,
                lambda r: f"{r.provider} {r.remote_id} {r.id} {r.label}",
            )
        for m in candidates[:80]:
            disp = f"{m.provider}/{m.remote_id}"
            if len(disp) > 64:
                disp = disp[:61] + "…"
            yield Completion(
                m.id,
                start_position=-len(text),
                display=disp,
                display_meta=m.id,
            )


def run_model_picker_dialog(
    *,
    home: Path,
    config: dict[str, Any],
    env: dict[str, str],
) -> tuple[str | None, str]:
    """One-line picker with fuzzy dropdown (prompt_toolkit completer).

    Returns ``(model_id, "")`` on success, or ``(None, reason_tag)``.
    """
    _ = env
    refs = list_auth_available_model_refs(home=home, config=config)
    if not refs:
        return None, "no_providers"

    if not sys.stdin.isatty():
        return None, "notty"

    in_thread = _prompt_toolkit_in_thread()
    current = str((config.get("model") or {}).get("default") or "").strip()
    if current and not any(r.id == current for r in refs):
        current = ""

    session = PromptSession(
        completer=_AuthModelCompleter(refs),
        complete_while_typing=True,
        complete_style="column",  # Force single-column style to avoid duplicates
    )
    try:
        line = session.prompt(
            "Model (type to filter, Tab for menu, Enter to apply) › ",
            default=current,
            in_thread=in_thread,
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return None, "cancelled"

    if not line:
        return None, "cancelled"

    ids = {r.id for r in refs}
    if line in ids:
        return line, ""

    registry = ModelRegistry()
    try:
        resolved = registry.resolve(model=line, provider=None)
    except Exception:
        resolved = None
    if resolved is not None and resolved.id in ids:
        return resolved.id, ""

    matches = fuzzy_filter(refs, line, lambda r: f"{r.provider} {r.remote_id} {r.id}")
    if len(matches) == 1:
        return matches[0].id, ""
    return None, "no_matches"
