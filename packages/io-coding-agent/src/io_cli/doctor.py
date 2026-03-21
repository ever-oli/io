"""Diagnostics for the IO CLI."""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from pathlib import Path

from .config import ensure_io_home, get_config_path, get_env_path, load_config, resolve_soul_path
from .session import SessionManager
from .status import status_report


def doctor_report(home: Path | None = None, cwd: Path | None = None) -> dict[str, object]:
    home = ensure_io_home(home)
    cwd = cwd or Path.cwd()
    config_path = get_config_path(home)
    env_path = get_env_path(home)
    sessions = SessionManager.list_for_cwd(cwd, home=home)
    status = status_report(home=home, cwd=cwd)
    packages = {
        "httpx": importlib.util.find_spec("httpx") is not None,
        "yaml": importlib.util.find_spec("yaml") is not None,
        "rich": importlib.util.find_spec("rich") is not None,
        "dotenv": importlib.util.find_spec("dotenv") is not None,
        "prompt_toolkit": importlib.util.find_spec("prompt_toolkit") is not None,
        "modal": importlib.util.find_spec("modal") is not None,
        "daytona": importlib.util.find_spec("daytona") is not None,
    }
    warnings: list[str] = []
    if not env_path.exists():
        warnings.append("Missing ~/.io/.env")
    if status["runtime"]["provider"] != "mock" and not status["auth"]["providers"][status["runtime"]["provider"]]["logged_in"]:
        warnings.append("Selected runtime provider is not authenticated.")
    terminal = status.get("terminal", {})
    if terminal.get("backend") == "ssh" and (
        not terminal.get("ssh_host") or not terminal.get("ssh_user")
    ):
        warnings.append("SSH terminal backend selected but ssh_host/ssh_user are not configured.")
    if terminal.get("backend") == "docker" and shutil.which("docker") is None:
        warnings.append("Docker terminal backend selected but docker is not installed.")
    if terminal.get("backend") == "singularity" and (
        shutil.which("apptainer") is None and shutil.which("singularity") is None
    ):
        warnings.append(
            "Singularity terminal backend selected but neither apptainer nor singularity is installed."
        )
    if terminal.get("backend") == "modal" and (
        not packages["modal"] or importlib.util.find_spec("minisweagent") is None
    ):
        warnings.append(
            "Modal terminal backend selected but the optional modal/minisweagent stack is missing."
        )
    if terminal.get("backend") == "daytona" and not packages["daytona"]:
        warnings.append("Daytona terminal backend selected but the daytona SDK is not installed.")
    cfg = load_config(home)
    soul_path, soul_source = resolve_soul_path(home, cwd=cwd, config=cfg)
    if soul_source == "io_home" and not soul_path.is_file():
        warnings.append(f"Missing {soul_path} (run io setup or add repo soul.md).")
    return {
        "python": {
            "version": sys.version.split()[0],
            "executable": sys.executable,
            "platform": platform.platform(),
        },
        "home": str(home),
        "cwd": str(cwd),
        "soul_path": str(soul_path),
        "soul_source": soul_source,
        "config_path": str(config_path),
        "env_path": str(env_path),
        "config_model": load_config(home).get("model", {}),
        "sessions_for_cwd": len(sessions),
        "packages": packages,
        "status": status,
        "warnings": warnings,
    }
