"""Local terminal execution backend."""

from __future__ import annotations

import os
from pathlib import Path

from .base import BaseEnvironment


def _find_shell() -> str:
    return os.environ.get("SHELL") or "/bin/bash"


class LocalEnvironment(BaseEnvironment):
    backend = "local"

    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
    ) -> dict[str, object]:
        workdir = cwd if isinstance(cwd, Path) else Path(str(cwd)).expanduser()
        env = {**os.environ, **self.env}
        return self._run_subprocess(
            [_find_shell(), "-lc", command],
            cwd=workdir,
            timeout=timeout,
            stdin_data=stdin_data,
            env=env,
        )

    def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
        workdir = cwd if isinstance(cwd, Path) else Path(str(cwd)).expanduser()
        return registry.spawn(
            command,
            cwd=workdir,
            task_id=task_id,
            env=self.env,
            backend=self.backend,
        )
