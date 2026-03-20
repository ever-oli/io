"""Daytona cloud execution backend."""

from __future__ import annotations

import math
import shlex
import threading
import time
from pathlib import Path
from typing import Any

from .base import BaseEnvironment, EnvironmentConfigurationError


class DaytonaEnvironment(BaseEnvironment):
    backend = "daytona"

    def __init__(
        self,
        *,
        image: str,
        timeout: int,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        cpu: int = 1,
        memory: int = 5120,
        disk: int = 10240,
        persistent_filesystem: bool = True,
        task_id: str = "default",
    ) -> None:
        super().__init__(timeout=timeout, env=env, cwd=cwd or "/home/daytona")
        if not image:
            raise EnvironmentConfigurationError(
                "Daytona backend requires daytona_image to be configured."
            )
        try:
            from daytona import (
                CreateSandboxFromImageParams,
                Daytona,
                DaytonaError,
                Resources,
                SandboxState,
            )
        except Exception as exc:
            raise EnvironmentConfigurationError(
                "Daytona backend requires the optional 'daytona-sdk' Python package."
            ) from exc

        self._persistent = persistent_filesystem
        self._task_id = task_id
        self._daytona = Daytona()
        self._daytona_error_cls = DaytonaError
        self._sandbox_state = SandboxState
        self._lock = threading.Lock()
        self._sandbox: Any | None = None

        resources = Resources(
            cpu=max(1, int(cpu)),
            memory=max(1, math.ceil(max(1, int(memory)) / 1024)),
            disk=min(10, max(1, math.ceil(max(1, int(disk)) / 1024))),
        )
        labels = {"io_task_id": task_id}
        sandbox_name = f"io-{task_id}"

        if self._persistent:
            try:
                self._sandbox = self._daytona.get(sandbox_name)
                self._sandbox.start()
            except Exception:
                self._sandbox = None

        if self._sandbox is None:
            self._sandbox = self._daytona.create(
                CreateSandboxFromImageParams(
                    image=image,
                    name=sandbox_name,
                    labels=labels,
                    auto_stop_interval=0,
                    resources=resources,
                )
            )

    def _ensure_sandbox_ready(self) -> None:
        assert self._sandbox is not None
        refresh = getattr(self._sandbox, "refresh_data", None)
        if callable(refresh):
            refresh()
        state = getattr(self._sandbox, "state", None)
        if state in (self._sandbox_state.STOPPED, self._sandbox_state.ARCHIVED):
            self._sandbox.start()

    def _exec_in_thread(self, command: str, *, cwd: str, timeout: int) -> dict[str, object]:
        assert self._sandbox is not None
        timed_command = f"timeout {timeout} sh -c {shlex.quote(command)}"
        result_holder: dict[str, object] = {"result": None, "error": None}

        def _run() -> None:
            try:
                response = self._sandbox.process.exec(timed_command, cwd=cwd)
                result_holder["result"] = {
                    "output": getattr(response, "result", "") or "",
                    "returncode": int(getattr(response, "exit_code", 0) or 0),
                    "timed_out": False,
                }
            except Exception as exc:
                result_holder["error"] = exc

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        deadline = time.monotonic() + timeout + 10
        while thread.is_alive():
            thread.join(timeout=0.2)
            if time.monotonic() > deadline:
                try:
                    self._sandbox.stop()
                except Exception:
                    pass
                return self._timeout_result(timeout)

        if result_holder["error"] is not None:
            return {"error": result_holder["error"]}
        result = result_holder["result"]
        return result if isinstance(result, dict) else {"output": "", "returncode": 1, "timed_out": False}

    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict[str, object]:
        with self._lock:
            self._ensure_sandbox_ready()

        exec_command = command
        if stdin_data is not None:
            marker = "IO_DAYTONA_EOF"
            exec_command = f"{command} << '{marker}'\n{stdin_data}\n{marker}"

        result = self._exec_in_thread(
            exec_command,
            cwd=str(cwd or self.cwd or "/home/daytona"),
            timeout=timeout or self.timeout,
        )
        if "error" not in result:
            return result

        error = result["error"]
        if isinstance(error, self._daytona_error_cls):
            with self._lock:
                try:
                    self._ensure_sandbox_ready()
                except Exception:
                    return {"output": f"Daytona execution error: {error}", "returncode": 1, "timed_out": False}
            retry = self._exec_in_thread(
                exec_command,
                cwd=str(cwd or self.cwd or "/home/daytona"),
                timeout=timeout or self.timeout,
            )
            if "error" not in retry:
                return retry
        return {"output": f"Daytona execution error: {error}", "returncode": 1, "timed_out": False}

    def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
        del registry, command, cwd, task_id
        raise EnvironmentConfigurationError(
            "Daytona backend does not yet support IO-style background process management."
        )

    def cleanup(self) -> None:
        with self._lock:
            if self._sandbox is None:
                return
            try:
                if self._persistent:
                    self._sandbox.stop()
                else:
                    self._daytona.delete(self._sandbox)
            except Exception:
                pass
            self._sandbox = None
