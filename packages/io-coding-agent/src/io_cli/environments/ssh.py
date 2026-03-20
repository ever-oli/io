"""SSH-backed terminal execution."""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

from .base import BaseEnvironment, EnvironmentConfigurationError


def _find_ssh() -> str:
    ssh = shutil.which("ssh")
    if ssh:
        return ssh
    raise EnvironmentConfigurationError(
        "SSH backend selected but no ssh executable was found in PATH."
    )


class SSHEnvironment(BaseEnvironment):
    backend = "ssh"

    def __init__(
        self,
        *,
        host: str,
        user: str,
        port: int,
        key_path: str,
        timeout: int,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
    ) -> None:
        super().__init__(timeout=timeout, env=env, cwd=cwd)
        if not host or not user:
            raise EnvironmentConfigurationError(
                "SSH backend requires ssh_host and ssh_user to be configured."
            )
        self.host = host
        self.user = user
        self.port = port
        self.key_path = key_path
        self.ssh = _find_ssh()

    def _build_argv(self, command: str, *, cwd: Path | str) -> list[str]:
        remote_cwd = str(cwd or self.cwd or "~")
        remote_command = f"bash -lc {shlex.quote(f'cd {remote_cwd} && {command}')}"
        argv = [
            self.ssh,
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=10",
        ]
        if self.port and self.port != 22:
            argv.extend(["-p", str(self.port)])
        if self.key_path:
            argv.extend(["-i", self.key_path])
        argv.append(f"{self.user}@{self.host}")
        argv.append(remote_command)
        return argv

    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict[str, object]:
        return self._run_subprocess(
            self._build_argv(command, cwd=cwd),
            timeout=timeout,
            stdin_data=stdin_data,
        )

    def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
        return registry.spawn(
            command,
            argv=self._build_argv(command, cwd=cwd),
            cwd=Path.cwd(),
            task_id=task_id,
            backend=self.backend,
        )
