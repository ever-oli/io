"""Gateway runtime status helpers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_GATEWAY_KIND = "io-gateway"
_RUNTIME_STATUS_FILE = "gateway_state.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_pid_path(home: Path) -> Path:
    return home / "gateway.pid"


def get_runtime_status_path(home: Path) -> Path:
    return home / _RUNTIME_STATUS_FILE


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_process_command(pid: int) -> str | None:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    command = result.stdout.strip()
    return command or None


def _looks_like_gateway_process(pid: int) -> bool:
    command = _read_process_command(pid)
    if not command:
        return False
    patterns = (
        "io_cli.main gateway",
        "io_cli/main.py gateway",
        " io gateway",
        "gateway/run.py",
        "io_cli.main gateway",
        " io gateway",
    )
    return any(pattern in command for pattern in patterns)


def _build_pid_record() -> dict[str, Any]:
    return {
        "pid": os.getpid(),
        "kind": _GATEWAY_KIND,
        "argv": list(sys.argv),
        "updated_at": _utc_now_iso(),
    }


def read_pid_record(home: Path) -> dict[str, Any] | None:
    path = get_pid_path(home)
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        try:
            return {"pid": int(raw)}
        except ValueError:
            return None
    if isinstance(payload, int):
        return {"pid": payload}
    return payload if isinstance(payload, dict) else None


def write_pid_file(home: Path) -> None:
    _write_json_file(get_pid_path(home), _build_pid_record())


def remove_pid_file(home: Path) -> None:
    try:
        get_pid_path(home).unlink(missing_ok=True)
    except Exception:
        pass


def read_runtime_status(home: Path) -> dict[str, Any] | None:
    return _read_json_file(get_runtime_status_path(home))


def write_runtime_status(
    home: Path,
    *,
    gateway_state: str | None = None,
    exit_reason: str | None = None,
    platform: str | None = None,
    platform_state: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    payload = read_runtime_status(home) or {
        **_build_pid_record(),
        "gateway_state": "starting",
        "exit_reason": None,
        "platforms": {},
    }
    payload["updated_at"] = _utc_now_iso()
    if gateway_state is not None:
        payload["gateway_state"] = gateway_state
    if exit_reason is not None:
        payload["exit_reason"] = exit_reason
    if platform is not None:
        platforms = payload.setdefault("platforms", {})
        platform_payload = platforms.get(platform, {})
        if platform_state is not None:
            platform_payload["state"] = platform_state
        if error_code is not None:
            platform_payload["error_code"] = error_code
        if error_message is not None:
            platform_payload["error_message"] = error_message
        platform_payload["updated_at"] = _utc_now_iso()
        platforms[platform] = platform_payload
    _write_json_file(get_runtime_status_path(home), payload)


def gateway_runtime_snapshot(home: Path) -> dict[str, Any]:
    pid_record = read_pid_record(home)
    runtime_status = read_runtime_status(home) or {}
    pid = None
    running = False
    command = None

    if isinstance(pid_record, dict):
        try:
            pid = int(pid_record.get("pid"))
        except (TypeError, ValueError):
            pid = None

    if pid is not None:
        try:
            os.kill(pid, 0)
        except OSError:
            running = False
        else:
            command = _read_process_command(pid)
            running = _looks_like_gateway_process(pid) or pid_record.get("kind") == _GATEWAY_KIND

    return {
        "running": running,
        "pid": pid,
        "command": command,
        "pid_path": str(get_pid_path(home)),
        "runtime_status_path": str(get_runtime_status_path(home)),
        "gateway_state": runtime_status.get("gateway_state"),
        "exit_reason": runtime_status.get("exit_reason"),
        "platforms": runtime_status.get("platforms", {}),
        "updated_at": runtime_status.get("updated_at"),
    }
