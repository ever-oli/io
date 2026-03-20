"""Base interfaces for IO terminal execution backends."""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class EnvironmentConfigurationError(RuntimeError):
    """Raised when a terminal backend is unavailable or misconfigured."""


def get_sandbox_dir() -> Path:
    """Return the host-side root for backend sandbox storage."""
    custom = os.getenv("TERMINAL_SANDBOX_DIR")
    if custom:
        root = Path(custom).expanduser()
    else:
        root = Path(os.getenv("IO_HOME", Path.home() / ".io")).expanduser() / "sandboxes"
    root.mkdir(parents=True, exist_ok=True)
    return root


class BaseEnvironment(ABC):
    backend = "base"

    def __init__(
        self,
        *,
        timeout: int,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        self.timeout = timeout
        self.env = dict(env or {})
        self.cwd = str(cwd) if cwd is not None else ""

    @abstractmethod
    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict[str, Any]:
        """Execute a command and return a IO-style payload."""

    @abstractmethod
    def spawn_background(
        self,
        *,
        registry: Any,
        command: str,
        cwd: Path | str,
        task_id: str,
    ) -> Any:
        """Start a background process via the shared process registry."""

    def cleanup(self) -> None:
        """Release backend resources."""

    def stop(self) -> None:
        self.cleanup()

    def __del__(self) -> None:
        try:
            self.cleanup()
        except Exception:
            pass

    def _prepare_command(self, command: str) -> tuple[str, str | None]:
        return command, None

    def _timeout_result(self, timeout: int | None) -> dict[str, Any]:
        effective_timeout = timeout or self.timeout
        return {
            "output": f"Command timed out after {effective_timeout}s",
            "returncode": 124,
            "timed_out": True,
        }

    def _run_subprocess(
        self,
        argv: list[str],
        *,
        cwd: Path | str | None = None,
        timeout: int | None = None,
        stdin_data: str | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        effective_timeout = timeout or self.timeout
        resolved_cwd = str(cwd) if cwd is not None else None
        try:
            result = subprocess.run(
                argv,
                cwd=resolved_cwd,
                env=env,
                input=stdin_data,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=effective_timeout,
            )
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(
                part.strip()
                for part in (
                    (exc.stdout or ""),
                    (exc.stderr or ""),
                    f"[Command timed out after {effective_timeout}s]",
                )
                if part and part.strip()
            )
            return {
                "output": output,
                "returncode": 124,
                "timed_out": True,
            }
        merged = "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part and part.strip()
        ).strip()
        return {
            "output": merged,
            "returncode": result.returncode,
            "timed_out": False,
        }
