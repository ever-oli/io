"""Local process registry for IO-style background process management."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MAX_OUTPUT_CHARS = 200_000


@dataclass
class ProcessSession:
    id: str
    command: str
    cwd: str
    task_id: str = ""
    backend: str = "local"
    argv: list[str] | None = None
    pid: int | None = None
    process: subprocess.Popen[str] | None = None
    started_at: float = field(default_factory=time.time)
    exited: bool = False
    exit_code: int | None = None
    output_buffer: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _reader_thread: threading.Thread | None = field(default=None, repr=False)


class ProcessRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, ProcessSession] = {}
        self._lock = threading.Lock()

    def spawn(
        self,
        command: str,
        *,
        argv: list[str] | None = None,
        cwd: str | Path | None = None,
        task_id: str = "",
        env: dict[str, str] | None = None,
        backend: str = "local",
    ) -> ProcessSession:
        session = ProcessSession(
            id=f"proc_{uuid.uuid4().hex[:12]}",
            command=command,
            cwd=str(Path(cwd or Path.cwd()).resolve()),
            task_id=task_id,
            backend=backend,
            argv=list(argv) if argv else None,
        )
        popen_args = session.argv
        if popen_args is None:
            shell = os.environ.get("SHELL") or "/bin/zsh"
            popen_args = [shell, "-lc", command]
        process = subprocess.Popen(
            popen_args,
            cwd=session.cwd,
            env={**os.environ, **(env or {})},
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            bufsize=1,
            preexec_fn=None if os.name == "nt" else os.setsid,
        )
        session.process = process
        session.pid = process.pid
        reader = threading.Thread(target=self._reader_loop, args=(session,), daemon=True)
        session._reader_thread = reader
        with self._lock:
            self._sessions[session.id] = session
        reader.start()
        return session

    def _reader_loop(self, session: ProcessSession) -> None:
        assert session.process is not None
        stream = session.process.stdout
        if stream is None:
            with session._lock:
                session.exited = True
                session.exit_code = session.process.wait()
            return
        try:
            for chunk in stream:
                self._append_output(session, chunk)
        finally:
            return_code = session.process.wait()
            with session._lock:
                session.exited = True
                session.exit_code = return_code

    def _append_output(self, session: ProcessSession, chunk: str) -> None:
        with session._lock:
            session.output_buffer = (session.output_buffer + chunk)[-MAX_OUTPUT_CHARS:]

    def _get(self, session_id: str) -> ProcessSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_sessions(self, *, task_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            sessions = list(self._sessions.values())
        rows = []
        for session in sessions:
            if task_id and session.task_id != task_id:
                continue
            rows.append(self._snapshot(session))
        rows.sort(key=lambda row: float(row["started_at"]), reverse=True)
        return rows

    def poll(self, session_id: str) -> dict[str, Any]:
        session = self._get(session_id)
        if session is None:
            return {"error": f"Unknown process session: {session_id}"}
        return self._snapshot(session)

    def read_log(self, session_id: str, *, offset: int = 0, limit: int = 200) -> dict[str, Any]:
        session = self._get(session_id)
        if session is None:
            return {"error": f"Unknown process session: {session_id}"}
        with session._lock:
            lines = session.output_buffer.splitlines()
        if limit <= 0:
            limit = 200
        start = offset if offset > 0 else max(0, len(lines) - limit)
        page = lines[start : start + limit]
        snapshot = self._snapshot(session)
        snapshot["lines"] = page
        snapshot["offset"] = start
        snapshot["returned"] = len(page)
        snapshot["total_lines"] = len(lines)
        return snapshot

    def wait(self, session_id: str, *, timeout: int | None = None) -> dict[str, Any]:
        session = self._get(session_id)
        if session is None:
            return {"error": f"Unknown process session: {session_id}"}
        process = session.process
        if process is None:
            return {"error": f"Process handle unavailable for {session_id}"}
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            snapshot = self._snapshot(session)
            snapshot["timed_out"] = True
            return snapshot
        return self._snapshot(session)

    def kill_process(self, session_id: str) -> dict[str, Any]:
        session = self._get(session_id)
        if session is None:
            return {"error": f"Unknown process session: {session_id}"}
        process = session.process
        if process is None:
            return {"error": f"Process handle unavailable for {session_id}"}
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as exc:
            return {"error": f"Failed to kill process: {exc}"}
        return self.wait(session_id, timeout=1)

    def write_stdin(self, session_id: str, data: str) -> dict[str, Any]:
        session = self._get(session_id)
        if session is None:
            return {"error": f"Unknown process session: {session_id}"}
        process = session.process
        if process is None or process.stdin is None:
            return {"error": "Process stdin is not available."}
        try:
            process.stdin.write(data)
            process.stdin.flush()
        except Exception as exc:
            return {"error": f"Failed to write to process stdin: {exc}"}
        return {"ok": True, "session_id": session_id, "bytes_written": len(data)}

    def submit_stdin(self, session_id: str, data: str) -> dict[str, Any]:
        return self.write_stdin(session_id, f"{data}\n")

    def _snapshot(self, session: ProcessSession) -> dict[str, Any]:
        with session._lock:
            output = session.output_buffer
            exited = session.exited
            exit_code = session.exit_code
            pid = session.pid
        return {
            "session_id": session.id,
            "command": session.command,
            "cwd": session.cwd,
            "task_id": session.task_id,
            "backend": session.backend,
            "pid": pid,
            "running": not exited,
            "exited": exited,
            "exit_code": exit_code,
            "started_at": session.started_at,
            "output": output,
        }


process_registry = ProcessRegistry()
