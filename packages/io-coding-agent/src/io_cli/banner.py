"""Welcome banner, ASCII art, skills summary, and update check for the IO CLI."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from prompt_toolkit import print_formatted_text as _pt_print
from prompt_toolkit.formatted_text import ANSI as _PT_ANSI
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __release_date__ as RELEASE_DATE, __version__ as VERSION
from .config import ensure_io_home, get_project_root
from .skills import discover_skills
from .skin_engine import IO_AGENT_LOGO, IO_PHI_HERO, get_active_skin

logger = logging.getLogger(__name__)

_UPDATE_CHECK_CACHE_SECONDS = 6 * 3600
_update_result: int | None = None
_update_check_done = threading.Event()


def cprint(text: str) -> None:
    _pt_print(_PT_ANSI(text))


def _format_context_length(tokens: int | None) -> str:
    if not tokens:
        return "unknown"
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:g}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:g}K"
    return str(tokens)


def _display_toolset_name(toolset_name: str) -> str:
    if not toolset_name:
        return "unknown"
    return toolset_name[:-6] if toolset_name.endswith("_tools") else toolset_name


def check_for_updates(home: Path | None = None) -> int | None:
    io_home = ensure_io_home(home)
    cache_file = io_home / ".update_check"
    repo_dir = get_project_root()
    if not (repo_dir / ".git").exists():
        return None

    now = time.time()
    try:
        if cache_file.exists():
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if now - cached.get("ts", 0) < _UPDATE_CHECK_CACHE_SECONDS:
                return cached.get("behind")
    except Exception:
        pass

    try:
        subprocess.run(
            ["git", "fetch", "origin", "--quiet"],
            capture_output=True,
            timeout=10,
            cwd=str(repo_dir),
        )
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(repo_dir),
        )
        behind = int(result.stdout.strip()) if result.returncode == 0 else None
    except Exception:
        behind = None

    try:
        cache_file.write_text(json.dumps({"ts": now, "behind": behind}), encoding="utf-8")
    except Exception:
        pass

    return behind


def prefetch_update_check(home: Path | None = None) -> None:
    def _run() -> None:
        global _update_result
        _update_result = check_for_updates(home=home)
        _update_check_done.set()

    threading.Thread(target=_run, daemon=True).start()


def get_update_result(timeout: float = 0.25) -> int | None:
    _update_check_done.wait(timeout=timeout)
    return _update_result


def _skills_summary(home: Path | None, cwd: str) -> tuple[int, str]:
    skills = [skill for skill in discover_skills(home=home, cwd=Path(cwd), platform="cli") if skill.enabled]
    names = ", ".join(skill.name for skill in skills[:6])
    if len(skills) > 6:
        names += f", +{len(skills) - 6} more"
    return len(skills), names or "none"


def build_welcome_banner(
    console: Console,
    model: str,
    cwd: str,
    tools: list[dict[str, Any]] | None = None,
    enabled_toolsets: list[str] | None = None,
    session_id: str | None = None,
    get_toolset_for_tool=None,
    context_length: int | None = None,
    *,
    home: Path | None = None,
) -> Panel:
    del console
    del get_toolset_for_tool

    skin = get_active_skin(home=home)
    update = get_update_result(timeout=0.05)
    skill_count, skill_names = _skills_summary(home, cwd)

    info = Table.grid(padding=(0, 1))
    info.add_column(style=skin.get_color("banner_accent", "#FFBF00"))
    info.add_column(style=skin.get_color("banner_text", "#FFF8DC"))
    info.add_row("Agent", skin.get_branding("agent_name", "IO Agent"))
    info.add_row("Version", f"{VERSION} ({RELEASE_DATE})")
    info.add_row("Model", model or "auto")
    info.add_row("Context", _format_context_length(context_length))
    info.add_row("CWD", cwd)
    if enabled_toolsets:
        info.add_row("Toolsets", ", ".join(_display_toolset_name(item) for item in enabled_toolsets))
    if tools:
        info.add_row("Tools", str(len(tools)))
    info.add_row("Skills", f"{skill_count} enabled")
    if skill_names != "none":
        info.add_row("Skill Set", skill_names)
    if session_id:
        info.add_row("Session", session_id[:12])
    if update is not None:
        info.add_row("Updates", "up to date" if update == 0 else f"{update} commit(s) behind")

    body = Group(
        Text.from_markup(skin.banner_logo or IO_AGENT_LOGO),
        Text.from_markup(skin.banner_hero or IO_PHI_HERO),
        info,
    )
    return Panel(
        body,
        title=skin.get_branding("agent_name", "IO Agent"),
        subtitle=skin.get_branding("welcome", "Welcome to IO"),
        border_style=skin.get_color("banner_border", "#CD7F32"),
    )
