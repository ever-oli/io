"""Tirith pre-exec scan — subset of OpenGauss ``tools/tirith_security.py`` (MIT / Hermes lineage).

Runs the ``tirith`` CLI if available: exit 0=allow, 1=block, 2=warn.
IO checks PATH and ``~/.io/bin/tirith``. Optional **``io security tirith-install``**
installs via ``cargo install --root ~/.io`` (Rust crate ``tirith``). See
``docs/open_gauss_hermes_port.md``.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MAX_FINDINGS = 50
_MAX_SUMMARY_LEN = 500


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _load_security_tirith_config(home: Path | None) -> dict[str, Any]:
    defaults = {
        "tirith_enabled": True,
        "tirith_path": "tirith",
        "tirith_timeout": 5,
        "tirith_fail_open": True,
    }
    cfg: dict[str, Any] = {}
    if home is not None:
        try:
            from ..config import load_config

            raw = load_config(home).get("security") or {}
            if isinstance(raw, dict):
                nested = raw.get("tirith")
                if isinstance(nested, dict):
                    cfg = nested
        except OSError:
            pass

    return {
        "tirith_enabled": _env_bool("TIRITH_ENABLED", bool(cfg.get("enabled", defaults["tirith_enabled"]))),
        "tirith_path": os.getenv("TIRITH_BIN", str(cfg.get("path", defaults["tirith_path"]))),
        "tirith_timeout": _env_int("TIRITH_TIMEOUT", int(cfg.get("timeout", defaults["tirith_timeout"]))),
        "tirith_fail_open": _env_bool(
            "TIRITH_FAIL_OPEN", bool(cfg.get("fail_open", defaults["tirith_fail_open"]))
        ),
    }


def _resolve_tirith_binary(path: str, home: Path | None) -> str | None:
    expanded = os.path.expanduser(path)
    if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
        return expanded
    found = shutil.which(expanded)
    if found:
        return found
    if home is not None:
        local = home / "bin" / "tirith"
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
    return None


def check_command_security(command: str, *, home: Path | None = None) -> dict[str, Any]:
    """Run Tirith on *command*.

    Returns:
        ``{"action": "allow"|"warn"|"block", "findings": [...], "summary": str}``
    """
    cfg = _load_security_tirith_config(home)
    if not cfg["tirith_enabled"]:
        return {"action": "allow", "findings": [], "summary": ""}

    tirith_path = _resolve_tirith_binary(cfg["tirith_path"], home)
    if tirith_path is None:
        if cfg["tirith_fail_open"]:
            return {"action": "allow", "findings": [], "summary": ""}
        return {
            "action": "block",
            "findings": [],
            "summary": "tirith binary not found (fail-closed)",
        }

    timeout = int(cfg["tirith_timeout"])
    fail_open = bool(cfg["tirith_fail_open"])

    try:
        result = subprocess.run(
            [
                tirith_path,
                "check",
                "--json",
                "--non-interactive",
                "--shell",
                "posix",
                "--",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except OSError as exc:
        logger.warning("tirith spawn failed: %s", exc)
        if fail_open:
            return {"action": "allow", "findings": [], "summary": f"tirith unavailable: {exc}"}
        return {"action": "block", "findings": [], "summary": f"tirith spawn failed: {exc}"}
    except subprocess.TimeoutExpired:
        logger.warning("tirith timed out after %ds", timeout)
        if fail_open:
            return {"action": "allow", "findings": [], "summary": f"tirith timed out ({timeout}s)"}
        return {"action": "block", "findings": [], "summary": f"tirith timed out ({timeout}s)"}

    code = result.returncode
    if code == 0:
        action = "allow"
    elif code == 1:
        action = "block"
    elif code == 2:
        action = "warn"
    else:
        logger.warning("tirith unexpected exit code %d", code)
        if fail_open:
            return {"action": "allow", "findings": [], "summary": f"tirith exit {code}"}
        return {"action": "block", "findings": [], "summary": f"tirith exit {code}"}

    findings: list[Any] = []
    summary = ""
    try:
        data = json.loads(result.stdout) if result.stdout.strip() else {}
        raw = data.get("findings", [])
        if isinstance(raw, list):
            findings = raw[:_MAX_FINDINGS]
        summary = str(data.get("summary", "") or "")[:_MAX_SUMMARY_LEN]
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.debug("tirith JSON parse failed")
        if action == "block":
            summary = "security issue detected (details unavailable)"
        elif action == "warn":
            summary = "security warning (details unavailable)"

    return {"action": action, "findings": findings, "summary": summary}


def install_tirith_via_cargo(
    home: Path,
    *,
    package: str = "tirith",
    timeout: int = 900,
) -> tuple[int, str, str]:
    """Run ``cargo install <package> --locked --root <home>`` (installs to ``<home>/bin/``).

    Tirith is a **Rust** crate (`cargo install tirith`); see upstream README.
    Returns ``(exit_code, expected_binary_path, combined_output)``.
    """
    cargo = shutil.which("cargo")
    dest = home / "bin" / "tirith"
    if not cargo:
        return (
            127,
            str(dest),
            "cargo not found on PATH; install Rust (rustup) or use brew/npm per "
            "https://github.com/sheeki03/tirith — then add tirith to PATH or re-run this command.",
        )
    home.mkdir(parents=True, exist_ok=True)
    (home / "bin").mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [cargo, "install", package, "--locked", "--root", str(home)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired:
        return 124, str(dest), f"cargo install timed out after {timeout}s"
    except OSError as exc:
        return 1, str(dest), str(exc)
    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode, str(dest), out


def tirith_approval_suffix(command: str, *, home: Path | None) -> str | None:
    """If Tirith says block or warn, return text for ``approval_reason``; else None."""
    verdict = check_command_security(command, home=home)
    action = verdict.get("action")
    summary = str(verdict.get("summary") or "").strip()
    if action == "block":
        base = "Tirith blocked this command"
        return f"{base}: {summary}" if summary else base
    if action == "warn":
        base = "Tirith reported a security warning"
        return f"{base}: {summary}" if summary else base
    return None
