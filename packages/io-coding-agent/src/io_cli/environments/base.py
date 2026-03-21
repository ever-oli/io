"""Base interfaces for IO terminal execution backends."""

from __future__ import annotations

import os
import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from threading import Thread
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
        stream_callback: Callable[[str, str], None] | None = None,
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
        stream_callback: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        effective_timeout = timeout or self.timeout
        resolved_cwd = str(cwd) if cwd is not None else None
        if stream_callback is None:
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

        # Streaming: pump stdout/stderr lines to *stream_callback* (stream_name, chunk).
        out_chunks: list[str] = []
        err_chunks: list[str] = []

        def _pump(pipe: Any, name: str, bucket: list[str]) -> None:
            try:
                for line in iter(pipe.readline, ""):
                    if not line:
                        break
                    bucket.append(line)
                    stream_callback(name, line)
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        try:
            proc = subprocess.Popen(
                argv,
                cwd=resolved_cwd,
                env=env,
                stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            return {"output": str(exc), "returncode": 1, "timed_out": False}

        threads: list[Thread] = []
        if proc.stdout is not None:
            threads.append(Thread(target=_pump, args=(proc.stdout, "stdout", out_chunks), daemon=True))
        if proc.stderr is not None:
            threads.append(Thread(target=_pump, args=(proc.stderr, "stderr", err_chunks), daemon=True))
        for thread in threads:
            thread.start()
        if proc.stdin is not None and stdin_data is not None:
            try:
                proc.stdin.write(stdin_data)
                proc.stdin.close()
            except Exception:
                pass
        try:
            proc.wait(timeout=effective_timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
            stream_callback("stderr", f"\n[Command timed out after {effective_timeout}s]\n")
            merged = "".join(out_chunks) + "".join(err_chunks)
            return {"output": merged.strip(), "returncode": 124, "timed_out": True}
        for thread in threads:
            thread.join(timeout=1.0)
        merged = "".join(out_chunks) + "".join(err_chunks)
        return {
            "output": merged.strip(),
            "returncode": int(proc.returncode or 0),
            "timed_out": False,
        }
