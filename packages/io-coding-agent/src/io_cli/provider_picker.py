"""Interactive `/provider` picker: fuzzy Tab dropdown (same UX as ``model_picker``)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from io_ai import fuzzy_filter
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion

from .auth import auth_status
from .model_picker import _prompt_toolkit_in_thread


@dataclass(frozen=True)
class _ProviderRow:
    """One selectable default-provider option."""

    provider_id: str
    label: str
    configured: bool


def list_provider_picker_rows(home: Path) -> list[_ProviderRow]:
    """All provider ids from auth status plus ``auto``, with labels."""
    rows: list[_ProviderRow] = []
    status = auth_status(home)
    providers = status.get("providers") or {}
    if not isinstance(providers, dict):
        providers = {}

    rows.append(
        _ProviderRow(
            "auto",
            "Automatic (detect from model / API keys)",
            True,
        )
    )
    for pid in sorted(providers.keys()):
        if pid == "auto":
            continue
        pdata = providers[pid]
        if not isinstance(pdata, dict):
            continue
        label = str(pdata.get("label", pid))
        configured = bool(pdata.get("logged_in"))
        rows.append(_ProviderRow(str(pid), label, configured))

    # De-dupe by id (e.g. if auto ever appeared twice)
    seen: set[str] = set()
    out: list[_ProviderRow] = []
    for r in rows:
        if r.provider_id in seen:
            continue
        seen.add(r.provider_id)
        out.append(r)
    return out


class _ProviderPickerCompleter(Completer):
    """Fuzzy-match provider ids and labels."""

    def __init__(self, rows: list[_ProviderRow]) -> None:
        self._rows = rows

    def get_completions(self, document: Any, complete_event: Any) -> Any:
        text = document.text_before_cursor
        raw = text.strip()
        if not raw:
            candidates = self._rows[:80]
        else:
            candidates = fuzzy_filter(
                self._rows,
                raw,
                lambda r: f"{r.provider_id} {r.label}",
            )
        for r in candidates[:80]:
            disp = r.label
            if len(disp) > 52:
                disp = disp[:49] + "…"
            meta = r.provider_id
            if not r.configured and r.provider_id != "auto":
                meta = f"{r.provider_id} (not configured)"
            yield Completion(
                r.provider_id,
                start_position=-len(text),
                display=disp,
                display_meta=meta,
            )


def run_provider_picker_dialog(
    *,
    home: Path,
    config: dict[str, Any],
) -> tuple[str | None, str]:
    """One-line picker with fuzzy dropdown.

    Returns ``(provider_id, "")`` on success, or ``(None, reason_tag)``.
    """
    rows = list_provider_picker_rows(home)
    if not rows:
        return None, "no_providers"

    if not sys.stdin.isatty():
        return None, "notty"

    in_thread = _prompt_toolkit_in_thread()
    current = str((config.get("model") or {}).get("provider") or "auto").strip()
    if current and not any(r.provider_id == current for r in rows):
        current = ""

    session = PromptSession(
        completer=_ProviderPickerCompleter(rows),
        complete_while_typing=True,
    )
    try:
        line = session.prompt(
            "Provider (type to filter, Tab for menu, Enter to apply) › ",
            default=current,
            in_thread=in_thread,
        ).strip()
    except (EOFError, KeyboardInterrupt):
        return None, "cancelled"

    if not line:
        return None, "cancelled"

    ids = {r.provider_id for r in rows}
    if line in ids:
        return line, ""

    matches = fuzzy_filter(
        rows,
        line,
        lambda r: f"{r.provider_id} {r.label}",
    )
    if len(matches) == 1:
        return matches[0].provider_id, ""
    return None, "no_matches"
