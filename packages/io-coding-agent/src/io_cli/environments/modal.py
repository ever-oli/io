"""Modal cloud execution backend."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
from pathlib import Path
from typing import Any

from .base import BaseEnvironment, EnvironmentConfigurationError, get_sandbox_dir


_SNAPSHOT_STORE = get_sandbox_dir() / "modal_snapshots.json"


def _load_snapshots() -> dict[str, str]:
    if not _SNAPSHOT_STORE.exists():
        return {}
    try:
        data = json.loads(_SNAPSHOT_STORE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_snapshots(data: dict[str, str]) -> None:
    _SNAPSHOT_STORE.parent.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_STORE.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


class ModalEnvironment(BaseEnvironment):
    backend = "modal"

    def __init__(
        self,
        *,
        image: str,
        timeout: int,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        modal_sandbox_kwargs: dict[str, Any] | None = None,
        persistent_filesystem: bool = True,
        task_id: str = "default",
    ) -> None:
        super().__init__(timeout=timeout, env=env, cwd=cwd or "/root")
        if not image:
            raise EnvironmentConfigurationError("Modal backend requires modal_image to be configured.")

        try:
            import modal  # noqa: F401
            from minisweagent.environments.extra.swerex_modal import SwerexModalEnvironment
        except Exception as exc:
            raise EnvironmentConfigurationError(
                "Modal backend requires the optional 'modal' and 'minisweagent' stack."
            ) from exc

        self._persistent = persistent_filesystem
        self._task_id = task_id
        self._inner: Any | None = None

        sandbox_kwargs = {
            key: value
            for key, value in (modal_sandbox_kwargs or {}).items()
            if value not in (None, 0, "", False)
        }

        effective_image: Any = image
        if self._persistent:
            snapshot_id = _load_snapshots().get(self._task_id)
            if snapshot_id:
                try:
                    import modal

                    effective_image = modal.Image.from_id(snapshot_id)
                except Exception:
                    effective_image = image

        self._inner = SwerexModalEnvironment(
            image=effective_image,
            cwd=str(self.cwd or "/root"),
            timeout=timeout,
            startup_timeout=180.0,
            runtime_timeout=max(float(timeout), 600.0),
            modal_sandbox_kwargs=sandbox_kwargs,
            install_pipx=True,
        )

    def execute(
        self,
        command: str,
        *,
        cwd: Path | str,
        timeout: int | None = None,
        stdin_data: str | None = None,
        stream_callback=None,
    ) -> dict[str, object]:
        if self._inner is None:
            return {"output": "Modal backend is not available.", "returncode": 1, "timed_out": False}

        exec_command = command
        if stdin_data is not None:
            marker = "IO_MODAL_EOF"
            exec_command = f"{command} << '{marker}'\n{stdin_data}\n{marker}"

        try:
            result = self._inner.execute(
                exec_command,
                cwd=str(cwd or self.cwd or "/root"),
                timeout=timeout or self.timeout,
            )
        except Exception as exc:
            return {"output": f"Modal execution error: {exc}", "returncode": 1, "timed_out": False}

        output = ""
        returncode = 0
        timed_out = False
        if isinstance(result, dict):
            output = str(result.get("output") or result.get("result") or "")
            returncode = int(result.get("returncode", result.get("exit_code", 0)) or 0)
            timed_out = bool(result.get("timed_out", False))
        else:
            output = str(result)
        if stream_callback and output:
            stream_callback("stdout", output)
        return {"output": output, "returncode": returncode, "timed_out": timed_out}

    def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
        del registry, command, cwd, task_id
        raise EnvironmentConfigurationError(
            "Modal backend does not yet support IO-style background process management."
        )

    def cleanup(self) -> None:
        if self._inner is None:
            return
        if self._persistent:
            try:
                sandbox = getattr(self._inner, "deployment", None)
                sandbox = getattr(sandbox, "_sandbox", None) if sandbox is not None else None
                if sandbox is not None:
                    async def _snapshot() -> str:
                        image = await sandbox.snapshot_filesystem.aio()
                        return str(image.object_id)

                    try:
                        snapshot_id = asyncio.run(_snapshot())
                    except RuntimeError:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                            snapshot_id = pool.submit(asyncio.run, _snapshot()).result(timeout=60)
                    snapshots = _load_snapshots()
                    snapshots[self._task_id] = snapshot_id
                    _save_snapshots(snapshots)
            except Exception:
                pass
        stop = getattr(self._inner, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass
        self._inner = None
