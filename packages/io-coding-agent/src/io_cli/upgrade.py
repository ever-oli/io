"""Self-upgrade command for IO.

Inspired by maxpetretta/pi-upgrade.
Upgrades the core io-coding-agent to the latest release.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)


def get_current_version() -> str:
    """Get current IO version."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "io-coding-agent"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.split("\n"):
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "unknown"


def get_latest_version() -> Optional[str]:
    """Check latest version from PyPI."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "index", "versions", "io-coding-agent"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.split("\n"):
            if "Available versions:" in line:
                versions = line.split(":", 1)[1].strip()
                # First version is latest
                return versions.split(",")[0].strip()
    except Exception:
        pass
    return None


def upgrade_io(
    force: bool = False,
    dry_run: bool = False,
    console: Optional[Console] = None,
) -> bool:
    """Upgrade IO to latest version.

    Args:
        force: Reinstall even if already on latest
        dry_run: Show what would happen without doing it
        console: Rich console for output

    Returns:
        True if upgrade succeeded
    """
    console = console or Console()

    current = get_current_version()
    latest = get_latest_version()

    console.print(
        Panel(
            f"Current: {current}\nLatest: {latest or 'unknown'}",
            title="IO Upgrade",
            border_style="blue",
        )
    )

    if latest and current == latest and not force:
        console.print("[green]Already on latest version![/green]")
        return True

    if dry_run:
        console.print(f"[dim]Would run: pip install --upgrade io-coding-agent[/dim]")
        return True

    # Determine package manager
    pip_cmd = [sys.executable, "-m", "pip"]

    # Check if using uv
    try:
        result = subprocess.run(
            ["which", "uv"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            pip_cmd = ["uv", "pip"]
    except Exception:
        pass

    console.print("[yellow]Upgrading IO...[/yellow]")

    try:
        result = subprocess.run(
            [*pip_cmd, "install", "--upgrade", "io-coding-agent"],
            capture_output=False,
            check=True,
        )

        console.print("[green]Upgrade complete![/green]")
        console.print("\n[dim]Please restart IO to use the new version.[/dim]")
        console.print("[dim]Run: io[/dim]")

        return True

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Upgrade failed: {e}[/red]")
        return False


def cmd_upgrade(argv: list, console: Optional[Console] = None) -> int:
    """CLI handler for upgrade command."""
    console = console or Console()

    force = "--force" in argv
    dry_run = "--dry-run" in argv

    success = upgrade_io(force=force, dry_run=dry_run, console=console)
    return 0 if success else 1
