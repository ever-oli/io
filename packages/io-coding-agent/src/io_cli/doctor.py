"""Diagnostics for the IO CLI."""

from __future__ import annotations

from pathlib import Path

from .auth import auth_status
from .config import ensure_io_home, load_config
from .session import SessionManager


def doctor_report(home: Path | None = None, cwd: Path | None = None) -> dict[str, object]:
    home = ensure_io_home(home)
    cwd = cwd or Path.cwd()
    sessions = SessionManager.list_for_cwd(cwd, home=home)
    return {
        "home": str(home),
        "cwd": str(cwd),
        "config_model": load_config(home).get("model", {}),
        "sessions_for_cwd": len(sessions),
        "auth": auth_status(home),
    }

