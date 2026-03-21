"""Terminal tab / window title (OSC 0), pi-tui–style."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Lowercase phi (pi-mono uses a distinctive glyph in the tab; IO uses φ for the agent).
_BRAND = "φ io"


def _sanitize_title(text: str) -> str:
    """Strip bytes that break OSC sequences or annoy shells."""
    return text.replace("\x07", "").replace("\x1b", "").replace("\n", " ").strip()


def format_io_window_title(cwd: Path) -> str:
    """Human-readable title: ``φ io — ~/project`` (home shortened to ``~``)."""
    try:
        resolved = cwd.resolve()
    except (OSError, RuntimeError):
        resolved = Path(cwd)
    home = Path.home()
    try:
        rel = resolved.relative_to(home)
        path_s = "~/" + str(rel)
    except ValueError:
        path_s = str(resolved)
    return _sanitize_title(f"{_BRAND} — {path_s}")


def set_terminal_title(title: str, *, file: object | None = None) -> None:
    """Set icon/window title via OSC 0 (same as pi ``ProcessTerminal.setTitle``)."""
    if os.environ.get("IO_TERMINAL_TITLE", "").strip().lower() in {"0", "false", "no", "off"}:
        return
    out = file if file is not None else sys.stdout
    try:
        if hasattr(out, "isatty") and not out.isatty():
            return
    except Exception:
        return
    safe = _sanitize_title(title)[:240]
    if not safe:
        return
    try:
        out.write(f"\x1b]0;{safe}\x07")
        out.flush()
    except Exception:
        pass
