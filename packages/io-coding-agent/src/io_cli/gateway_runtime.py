"""
Gateway runtime status helpers.

Provides PID-file based detection of whether the gateway runtime is running,
used by send_message's check_fn to gate availability in the CLI.

The PID file lives at ``{IO_HOME}/gateway.pid``.  IO_HOME defaults to
``~/.io`` but can be overridden via the environment variable.  This means
separate IO_HOME directories naturally get separate PID files — a property
that will be useful when we add named profiles (multiple agents running
concurrently under distinct configurations).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_GATEWAY_KIND = "io-gateway"
_RUNTIME_STATUS_FILE = "gateway_state.json"
_LOCKS_DIRNAME = "gateway-locks"


def get_pid_path(home: Path | None = None) -> Path:
    """Return the path to the gateway PID file, respecting IO_HOME."""
    if home is None:
        home = Path(os.getenv("IO_HOME", Path.home() / ".io"))
    return home / "gateway.pid"


def get_runtime_status_path(home: Path | None = None) -> Path:
    """Return the persisted runtime health/status file path."""
    return get_pid_path(home).with_name(_RUNTIME_STATUS_FILE)


def _get_lock_dir() -> Path:
    """Return the machine-local directory for token-scoped gateway locks."""
    override = os.getenv("IO_GATEWAY_LOCK_DIR")
    if override:
        return Path(override)
    state_home = Path(os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_home / "io" / _LOCKS_DIRNAME


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope_hash(identity: str) -> str:
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _get_scope_lock_path(scope: str, identity: str) -> Path:
    return _get_lock_dir() / f"{scope}-{_scope_hash(identity)}.lock"


def _get_process_start_time(pid: int) -> Optional[int]:
    """Return the kernel start time for a process when available."""
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        # Field 22 in /proc/<pid>/stat is process start time (clock ticks).
        return int(stat_path.read_text().split()[21])
    except (FileNotFoundError, IndexError, PermissionError, ValueError, OSError):
        return None


def _read_process_cmdline(pid: int) -> Optional[str]:
    """Return the process command line as a space-separated string."""
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    try:
        raw = cmdline_path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError):
        return None

    if not raw:
        return None
    return raw.replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()


def _looks_like_gateway_process(pid: int) -> bool:
    """Return True when the live PID still looks like the IO gateway."""
    cmdline = _read_process_cmdline(pid)
    if not cmdline:
        return False

    patterns = (
        "io_cli.main gateway",
        "io_cli/main.py gateway",
        "io gateway",
        "gateway/run.py",
    )
    return any(pattern in cmdline for pattern in patterns)


def _record_looks_like_gateway(record: dict[str, Any]) -> bool:
    """Validate gateway identity from PID-file metadata when cmdline is unavailable."""
    if record.get("kind") != _GATEWAY_KIND:
        return False

    argv = record.get("argv")
    if not isinstance(argv, list) or not argv:
        return False

    cmdline = " ".join(str(part) for part in argv)
    patterns = (
        "io_cli.main gateway",
        "io_cli/main.py gateway",
        "io gateway",
        "gateway/run.py",
    )
    return any(pattern in cmdline for pattern in patterns)


def _build_pid_record() -> dict:
    return {
        "pid": os.getpid(),
        "kind": _GATEWAY_KIND,
        "argv": list(sys.argv),
        "start_time": _get_process_start_time(os.getpid()),
    }


def _build_runtime_status_record() -> dict[str, Any]:
    payload = _build_pid_record()
    payload.update({
        "gateway_state": "starting",
        "exit_reason": None,
        "platforms": {},
        "updated_at": _utc_now_iso(),
    })
    return payload


def _read_json_file(path: Path) -> Optional[dict[str, Any]]:
    if not path.exists():
        return None
    try:
        raw = path.read_text().strip()
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
    path.write_text(json.dumps(payload))


def read_pid_record(home: Path | None = None) -> Optional[dict]:
    pid_path = get_pid_path(home)
    if not pid_path.exists():
        return None

    raw = pid_path.read_text().strip()
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
    if isinstance(payload, dict):
        return payload
    return None


def write_pid_file(home: Path | None = None) -> None:
    """Write the current process PID and metadata to the gateway PID file."""
    _write_json_file(get_pid_path(home), _build_pid_record())


def write_runtime_status(
    home: Path | None = None,
    *,
    gateway_state: Optional[str] = None,
    exit_reason: Optional[str] = None,
    platform: Optional[str] = None,
    platform_state: Optional[str] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Persist gateway runtime health information for diagnostics/status."""
    path = get_runtime_status_path(home)
    payload = _read_json_file(path) or _build_runtime_status_record()
    payload.setdefault("platforms", {})
    payload.setdefault("kind", _GATEWAY_KIND)
    payload["pid"] = os.getpid()
    payload["start_time"] = _get_process_start_time(os.getpid())
    payload["updated_at"] = _utc_now_iso()

    if gateway_state is not None:
        payload["gateway_state"] = gateway_state
    if exit_reason is not None:
        payload["exit_reason"] = exit_reason

    if platform is not None:
        platform_payload = payload["platforms"].get(platform, {})
        if platform_state is not None:
            platform_payload["state"] = platform_state
        if error_code is not None:
            platform_payload["error_code"] = error_code
        if error_message is not None:
            platform_payload["error_message"] = error_message
        platform_payload["updated_at"] = _utc_now_iso()
        payload["platforms"][platform] = platform_payload

    _write_json_file(path, payload)


def read_runtime_status(home: Path | None = None) -> Optional[dict[str, Any]]:
    """Read the persisted gateway runtime health/status information."""
    return _read_json_file(get_runtime_status_path(home))


def remove_pid_file(home: Path | None = None) -> None:
    """Remove the gateway PID file if it exists."""
    try:
        get_pid_path(home).unlink(missing_ok=True)
    except Exception:
        pass


def gateway_runtime_snapshot(home: Path | None = None) -> dict[str, Any]:
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
            command = _read_process_cmdline(pid)
            running = (
                _looks_like_gateway_process(pid)
                or _record_looks_like_gateway(pid_record or {})
                or (isinstance(pid_record, dict) and pid_record.get("kind") == _GATEWAY_KIND)
            )

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


def acquire_scoped_lock(scope: str, identity: str, metadata: Optional[dict[str, Any]] = None, home: Path | None = None) -> tuple[bool, Optional[dict[str, Any]]]:
    """Acquire a machine-local lock keyed by scope + identity.

    Used to prevent multiple local gateways from using the same external identity
    at once (e.g. the same Telegram bot token across different IO_HOME dirs).
    """
    lock_path = _get_scope_lock_path(scope, identity)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        **_build_pid_record(),
        "scope": scope,
        "identity_hash": _scope_hash(identity),
        "metadata": metadata or {},
        "updated_at": _utc_now_iso(),
    }

    existing = _read_json_file(lock_path)
    if existing:
        try:
            existing_pid = int(existing["pid"])
        except (KeyError, TypeError, ValueError):
            existing_pid = None

        if existing_pid == os.getpid() and existing.get("start_time") == record.get("start_time"):
            _write_json_file(lock_path, record)
            return True, existing

        stale = existing_pid is None
        if not stale:
            try:
                os.kill(existing_pid, 0)
            except (ProcessLookupError, PermissionError):
                stale = True
            else:
                current_start = _get_process_start_time(existing_pid)
                if (
                    existing.get("start_time") is not None
                    and current_start is not None
                    and current_start != existing.get("start_time")
                ):
                    stale = True
        if stale:
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass
        else:
            return False, existing

    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False, _read_json_file(lock_path)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
    except Exception:
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return True, None


def release_scoped_lock(scope: str, identity: str, home: Path | None = None) -> None:
    """Release a previously-acquired scope lock when owned by this process."""
    del home
    lock_path = _get_scope_lock_path(scope, identity)
    existing = _read_json_file(lock_path)
    if not existing:
        return
    if existing.get("pid") != os.getpid():
        return
    if existing.get("start_time") != _get_process_start_time(os.getpid()):
        return
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def read_scope_lock(
    scope: str,
    identity: str,
    home: Path | None = None,
) -> Optional[dict[str, Any]]:
    del home
    return _read_json_file(_get_scope_lock_path(scope, identity))


def get_running_pid(home: Path | None = None) -> Optional[int]:
    """Return the PID of a running gateway instance, or ``None``.

    Checks the PID file and verifies the process is actually alive.
    Cleans up stale PID files automatically.
    """
    record = read_pid_record(home)
    if not record:
        remove_pid_file(home)
        return None

    try:
        pid = int(record["pid"])
    except (KeyError, TypeError, ValueError):
        remove_pid_file(home)
        return None

    try:
        os.kill(pid, 0)  # signal 0 = existence check, no actual signal sent
    except (ProcessLookupError, PermissionError):
        remove_pid_file(home)
        return None

    recorded_start = record.get("start_time")
    current_start = _get_process_start_time(pid)
    if recorded_start is not None and current_start is not None and current_start != recorded_start:
        remove_pid_file(home)
        return None

    if not _looks_like_gateway_process(pid):
        if not _record_looks_like_gateway(record):
            remove_pid_file(home)
            return None

    return pid


def is_gateway_running(home: Path | None = None) -> bool:
    """Check if the gateway runtime is currently running."""
    return get_running_pid(home) is not None
