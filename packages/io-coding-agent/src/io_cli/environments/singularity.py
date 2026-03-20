"""Singularity and Apptainer terminal execution backend."""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

from .base import BaseEnvironment, EnvironmentConfigurationError, get_sandbox_dir


def _find_singularity() -> str:
    executable = shutil.which("apptainer") or shutil.which("singularity")
    if executable:
        return executable
    raise EnvironmentConfigurationError(
        "Singularity backend selected but neither apptainer nor singularity was found in PATH."
    )


class SingularityEnvironment(BaseEnvironment):
    backend = "singularity"

    def __init__(
        self,
        *,
        image: str,
        timeout: int,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        cpu: int = 0,
        memory: int = 0,
        disk: int = 0,
        persistent_filesystem: bool = False,
        task_id: str = "default",
    ) -> None:
        super().__init__(timeout=timeout, env=env, cwd=cwd)
        if not image:
            raise EnvironmentConfigurationError(
                "Singularity backend requires singularity_image to be configured."
            )
        self.executable = _find_singularity()
        self.image = image
        self.cpu = max(0, int(cpu))
        self.memory = max(0, int(memory))
        self.disk = max(0, int(disk))
        self.persistent_filesystem = persistent_filesystem
        self.task_id = task_id
        self.overlay_dir: Path | None = None
        if self.persistent_filesystem:
            overlay_root = get_sandbox_dir() / "singularity" / "overlays"
            overlay_root.mkdir(parents=True, exist_ok=True)
            self.overlay_dir = overlay_root / f"overlay-{self.task_id}"
            self.overlay_dir.mkdir(parents=True, exist_ok=True)

    def _build_argv(self, command: str, *, cwd: Path | str) -> list[str]:
        argv = [self.executable, "exec", "--containall", "--no-home"]
        if self.overlay_dir is not None:
            argv.extend(["--overlay", str(self.overlay_dir)])
        else:
            argv.append("--writable-tmpfs")
        if self.memory > 0:
            argv.extend(["--memory", f"{self.memory}M"])
        if self.cpu > 0:
            argv.extend(["--cpus", str(self.cpu)])
        effective_cwd: Path | str = cwd or self.cwd or "/tmp"
        exec_command = command
        if isinstance(effective_cwd, Path):
            bind_source = effective_cwd.resolve()
            argv.extend(["--bind", f"{str(bind_source)}:/workspace"])
            argv.extend(["--pwd", "/workspace"])
        else:
            cwd_value = str(effective_cwd).strip()
            if cwd_value and cwd_value not in {".", "./"}:
                if cwd_value == "~" or cwd_value.startswith("~/"):
                    exec_command = f"cd {shlex.quote(cwd_value)} && {command}"
                else:
                    argv.extend(["--pwd", cwd_value])
        argv.extend([self.image, "bash", "-lc", exec_command])
        return argv

    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict[str, object]:
        env = {**os.environ, **self.env}
        return self._run_subprocess(
            self._build_argv(command, cwd=cwd),
            timeout=timeout,
            stdin_data=stdin_data,
            env=env,
        )

    def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
        host_cwd = cwd if isinstance(cwd, Path) else Path.cwd()
        return registry.spawn(
            command,
            argv=self._build_argv(command, cwd=cwd),
            cwd=host_cwd,
            task_id=task_id,
            backend=self.backend,
        )
