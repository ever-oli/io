"""Self-upgrade command for IO.

Inspired by maxpetretta/pi-upgrade.
Upgrades the core io-coding-agent to the latest release.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)


def _candidate_install_roots(home: Path | None = None) -> list[Path]:
    candidates: list[Path] = []

    install_dir = str(os.environ.get("IO_INSTALL_DIR", "") or "").strip()
    if install_dir:
        candidates.append(Path(install_dir).expanduser())

    if home is not None:
        candidates.append(home / "io")

    try:
        repo_root = Path(__file__).resolve().parents[4]
        candidates.append(repo_root)
    except Exception:
        pass

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


def detect_git_install_root(home: Path | None = None) -> Path | None:
    for candidate in _candidate_install_roots(home):
        if (candidate / ".git").exists() and (candidate / "scripts" / "install.sh").is_file():
            return candidate
    return None


def _current_git_branch(repo_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    branch = result.stdout.strip()
    if result.returncode != 0 or not branch or branch == "HEAD":
        return None
    return branch


def _installer_update_command(repo_root: Path, branch: str | None = None) -> list[str]:
    cmd = ["bash", str(repo_root / "scripts" / "install.sh"), "--skip-setup", "--dir", str(repo_root)]
    if branch:
        cmd.extend(["--branch", branch])
    return cmd


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
    home: Path | None = None,
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

    repo_root = detect_git_install_root(home)
    if repo_root is not None:
        branch = _current_git_branch(repo_root) or "main"
        console.print(
            Panel(
                f"Install mode: git checkout\nPath: {repo_root}\nBranch: {branch}",
                title="IO Update",
                border_style="blue",
            )
        )
        if force:
            console.print("[dim]Force flag is ignored for git installs; the installer always refreshes the checkout and dependencies.[/dim]")
        cmd = _installer_update_command(repo_root, branch=branch)
        if dry_run:
            console.print(f"[dim]Would run: {' '.join(cmd)}[/dim]")
            return True
        console.print("[yellow]Updating IO from git checkout...[/yellow]")
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            console.print(f"[red]Update failed: {exc}[/red]")
            return False
        console.print("[green]Update complete![/green]")
        console.print("\n[dim]Restart IO to use the updated code.[/dim]")
        return True

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


def cmd_upgrade(
    argv: list,
    *,
    home: Path | None = None,
    console: Optional[Console] = None,
) -> int:
    """CLI handler for upgrade command."""
    console = console or Console()

    force = "--force" in argv
    dry_run = "--dry-run" in argv

    success = upgrade_io(home=home, force=force, dry_run=dry_run, console=console)
    return 0 if success else 1
