"""Spawn ``io gateway run`` in the background (REPL / messaging slash)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def spawn_gateway_run_detached(home: Path) -> tuple[int | None, str, str]:
    """Start ``io gateway run`` detached. Returns ``(pid_or_none, log_path, message)``."""
    env = {**os.environ, "IO_HOME": str(home)}
    io_exe = shutil.which("io")
    if io_exe:
        cmd: list[str] = [io_exe, "gateway", "run"]
    else:
        cmd = [
            sys.executable,
            "-c",
            "import sys; from io_cli.cli import main as _m; raise SystemExit(_m(['gateway', 'run']))",
        ]

    log_dir = home / "gateway"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "run.log"
    log_f = open(log_path, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    except OSError as exc:
        log_f.close()
        return None, str(log_path), f"Failed to spawn gateway: {exc}"
    log_f.close()
    pid = proc.pid
    msg = (
        f"Started gateway run in the background (pid {pid}).\n"
        f"Log: {log_path}\n"
        "Stop with: io gateway stop (or kill the process)."
    )
    return pid, str(log_path), msg
