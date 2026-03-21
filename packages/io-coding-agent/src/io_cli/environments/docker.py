"""Docker-backed terminal execution."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from .base import BaseEnvironment, EnvironmentConfigurationError


def _find_docker() -> str:
    docker = shutil.which("docker")
    if docker:
        return docker
    raise EnvironmentConfigurationError(
        "Docker backend selected but no docker executable was found in PATH."
    )


class DockerEnvironment(BaseEnvironment):
    backend = "docker"

    def __init__(
        self,
        *,
        image: str,
        timeout: int,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        mount_cwd: bool = True,
        forward_env: list[str] | None = None,
    ) -> None:
        super().__init__(timeout=timeout, env=env, cwd=cwd)
        self.image = image
        self.mount_cwd = mount_cwd
        self.forward_env = [item for item in (forward_env or []) if item]
        self.docker = _find_docker()
        if not self.image:
            raise EnvironmentConfigurationError(
                "Docker backend requires a docker image to be configured."
            )

    def _build_argv(self, command: str, *, cwd: Path | str) -> list[str]:
        host_cwd = cwd if isinstance(cwd, Path) else Path(str(cwd)).expanduser()
        argv = [self.docker, "run", "--rm", "-i"]
        container_cwd = self.cwd or "/root"
        if self.mount_cwd:
            container_cwd = "/workspace"
            argv.extend(["-v", f"{str(host_cwd.resolve())}:{container_cwd}"])
        argv.extend(["-w", container_cwd])
        for key in self.forward_env:
            value = self.env.get(key) or os.environ.get(key)
            if value:
                argv.extend(["-e", f"{key}={value}"])
        argv.extend([self.image, "bash", "-lc", command])
        return argv

    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
        stream_callback=None,
    ) -> dict[str, object]:
        return self._run_subprocess(
            self._build_argv(command, cwd=cwd),
            timeout=timeout,
            stdin_data=stdin_data,
            stream_callback=stream_callback,
        )

    def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
        host_cwd = cwd if isinstance(cwd, Path) else Path(str(cwd)).expanduser()
        return registry.spawn(
            command,
            argv=self._build_argv(command, cwd=cwd),
            cwd=host_cwd,
            task_id=task_id,
            backend=self.backend,
        )
