"""IO Swarm Manager - Background agent orchestration for Lean workflows.

Like Gauss's swarm manager, but built for IO's 7-package architecture.
Manages spawned agents, tracks lifecycle, enables attach/detach.
"""

from __future__ import annotations

import fcntl
import logging
import os
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_RECENT_OUTPUT_LIMIT = 256 * 1024


class TaskStatus(Enum):
    """Status of a swarm task."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class SwarmTask:
    """A single background task/agent."""

    task_id: str
    description: str
    command: str
    project_dir: Path
    status: TaskStatus = field(default=TaskStatus.QUEUED)

    # Runtime
    process: Optional[subprocess.Popen] = field(default=None, repr=False)
    thread: Optional[threading.Thread] = field(default=None, repr=False)
    start_time: Optional[float] = field(default=None)
    end_time: Optional[float] = field(default=None)

    # Output tracking
    _output_buffer: List[str] = field(default_factory=list, repr=False)
    _recent_output: bytearray = field(default_factory=bytearray, repr=False)
    _attached: bool = field(default=False, repr=False)

    # PTY for interactive sessions
    pty_master_fd: Optional[int] = field(default=None, repr=False)

    # Results
    exit_code: Optional[int] = field(default=None)
    error_message: Optional[str] = field(default=None)
    progress: str = field(default="Starting...")


class SwarmManager:
    """Manages background agent swarm.

    Thread-safe singleton that tracks all spawned agents.
    Supports both background (non-interactive) and interactive (PTY) tasks.
    """

    _instance: Optional[SwarmManager] = None
    _lock: threading.Lock = threading.Lock()

    # Type annotations for instance attributes
    _tasks: Dict[str, SwarmTask]
    _counter: int
    _task_lock: threading.Lock
    _on_complete: Optional[Callable[[SwarmTask], None]]

    def __new__(cls) -> SwarmManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._tasks = {}
                    inst._counter = 0
                    inst._task_lock = threading.Lock()
                    inst._on_complete = None
                    cls._instance = inst
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (for testing)."""
        with cls._lock:
            cls._instance = None

    def set_on_complete(self, callback: Optional[Callable[[SwarmTask], None]]) -> None:
        """Set callback for task completion."""
        self._on_complete = callback

    def spawn(
        self,
        command: List[str],
        description: str,
        project_dir: Path,
        env: Optional[Dict[str, str]] = None,
        interactive: bool = False,
    ) -> SwarmTask:
        """Spawn a new background task."""
        with self._task_lock:
            self._counter += 1
            task_id = f"io-{self._counter:03d}"
            task = SwarmTask(
                task_id=task_id,
                description=description,
                command=" ".join(command),
                project_dir=project_dir,
            )
            self._tasks[task_id] = task

        if interactive:
            target = self._run_interactive
        else:
            target = self._run_background

        thread = threading.Thread(
            target=target,
            args=(task, command, project_dir, env or {}),
            daemon=True,
            name=f"swarm-{task_id}",
        )
        task.thread = thread
        thread.start()

        logger.info(f"[Swarm] Spawned {task_id}: {description}")
        return task

    def _run_background(
        self,
        task: SwarmTask,
        command: List[str],
        cwd: Path,
        env: Dict[str, str],
    ) -> None:
        """Run task in background (non-interactive)."""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        task.progress = "Running..."

        full_env = {**os.environ, **env}

        try:
            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
            )
            task.process = proc

            stdout, stderr = proc.communicate()
            task.exit_code = proc.returncode

            if proc.returncode == 0:
                task.status = TaskStatus.COMPLETE
                task.progress = "Complete"
            else:
                task.status = TaskStatus.FAILED
                task.error_message = stderr[:500] if stderr else f"Exit code {proc.returncode}"
                task.progress = "Failed"

        except FileNotFoundError:
            task.status = TaskStatus.FAILED
            task.error_message = f"Command not found: {command[0]}"
            task.progress = "Failed"
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)[:500]
            task.progress = "Error"
        finally:
            task.end_time = time.time()
            if self._on_complete:
                try:
                    self._on_complete(task)
                except Exception:
                    pass

    def _run_interactive(
        self,
        task: SwarmTask,
        command: List[str],
        cwd: Path,
        env: Dict[str, str],
    ) -> None:
        """Run task with PTY for interactive attach/detach."""
        task.status = TaskStatus.RUNNING
        task.start_time = time.time()
        task.progress = "Running (interactive)"

        full_env = {**os.environ, **env}
        master_fd = None

        try:
            master_fd, slave_fd = os.openpty()

            try:
                sz = os.get_terminal_size()
                win = struct.pack("HHHH", sz.lines, sz.columns, 0, 0)
                fcntl.ioctl(slave_fd, termios.TIOCSWINSZ, win)
            except OSError:
                pass

            proc = subprocess.Popen(
                command,
                cwd=cwd,
                env=full_env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
            os.close(slave_fd)

            task.process = proc
            task.pty_master_fd = master_fd

            buf = b""
            while True:
                if task._attached:
                    time.sleep(0.25)
                    ret = proc.poll()
                    if ret is not None:
                        break
                    if task.status == TaskStatus.CANCELLED:
                        proc.terminate()
                        break
                    continue

                try:
                    ready, _, _ = select.select([master_fd], [], [], 0.5)
                except (ValueError, OSError):
                    break

                if master_fd in ready:
                    if task._attached:
                        continue
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break

                    task._recent_output.extend(chunk)
                    if len(task._recent_output) > _RECENT_OUTPUT_LIMIT:
                        del task._recent_output[:-_RECENT_OUTPUT_LIMIT]

                    buf += chunk
                    while b"\n" in buf:
                        line_bytes, buf = buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").rstrip("\r")
                        task._output_buffer.append(line)
                        if len(task._output_buffer) > 2000:
                            task._output_buffer = task._output_buffer[-1000:]

                ret = proc.poll()
                if ret is not None:
                    break
                if task.status == TaskStatus.CANCELLED:
                    proc.terminate()
                    break

            proc.wait()

            if task.status == TaskStatus.CANCELLED:
                task.progress = "Cancelled"
            elif proc.returncode == 0:
                task.status = TaskStatus.COMPLETE
                task.progress = "Complete"
            else:
                task.status = TaskStatus.FAILED
                task.progress = "Failed"

        except FileNotFoundError:
            task.status = TaskStatus.FAILED
            task.error_message = f"Command not found: {command[0]}"
            task.progress = "Failed"
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)[:500]
            task.progress = "Error"
        finally:
            task.process = None
            task.pty_master_fd = None
            task.end_time = time.time()
            if self._on_complete:
                try:
                    self._on_complete(task)
                except Exception:
                    pass

    def attach_to_task(self, task_id: str) -> int:
        """Attach terminal to a running interactive task.

        Returns exit code, or -1 on detach (Ctrl-]).
        """
        task = self.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.pty_master_fd is None or task.process is None:
            raise ValueError(f"Task {task_id} is not running interactively")

        master_fd = task.pty_master_fd
        real_stdin_fd = sys.stdin.fileno()
        stdout_fd = sys.stdout.fileno()

        try:
            old_tty_attrs = termios.tcgetattr(real_stdin_fd)
        except termios.error:
            old_tty_attrs = None

        try:
            tty.setraw(real_stdin_fd)

            try:
                sz = os.get_terminal_size(real_stdin_fd)
                win = struct.pack("HHHH", sz.lines, sz.columns, 0, 0)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, win)
            except OSError:
                pass

            task._attached = True

            if task.process is not None:
                try:
                    task.process.send_signal(signal.SIGWINCH)
                except (OSError, ProcessLookupError):
                    pass

            if task._recent_output:
                try:
                    os.write(stdout_fd, bytes(task._recent_output))
                except OSError:
                    pass

            def handle_sigwinch(signum, frame):
                try:
                    sz = os.get_terminal_size(real_stdin_fd)
                    win = struct.pack("HHHH", sz.lines, sz.columns, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, win)
                except Exception:
                    pass
                if task.process is not None:
                    try:
                        task.process.send_signal(signal.SIGWINCH)
                    except (OSError, ProcessLookupError):
                        pass

            prev_sigwinch = signal.signal(signal.SIGWINCH, handle_sigwinch)

            try:
                while True:
                    try:
                        rlist, _, _ = select.select([real_stdin_fd, master_fd], [], [], 0.25)
                    except (ValueError, OSError):
                        break

                    if real_stdin_fd in rlist:
                        try:
                            data = os.read(real_stdin_fd, 1024)
                        except OSError:
                            break
                        if not data:
                            break
                        if b"\x1d" in data:  # Ctrl-] detach
                            break
                        try:
                            os.write(master_fd, data)
                        except OSError:
                            break

                    if master_fd in rlist:
                        try:
                            data = os.read(master_fd, 4096)
                        except OSError:
                            break
                        if not data:
                            break
                        task._recent_output.extend(data)
                        if len(task._recent_output) > _RECENT_OUTPUT_LIMIT:
                            del task._recent_output[:-_RECENT_OUTPUT_LIMIT]
                        try:
                            os.write(stdout_fd, data)
                        except OSError:
                            break

                    if task.process is not None and task.process.poll() is not None:
                        try:
                            rlist2, _, _ = select.select([master_fd], [], [], 0.1)
                            if master_fd in rlist2:
                                remaining = os.read(master_fd, 4096)
                                if remaining:
                                    os.write(stdout_fd, remaining)
                        except OSError:
                            pass
                        break
            finally:
                signal.signal(signal.SIGWINCH, prev_sigwinch)
        finally:
            task._attached = False
            if old_tty_attrs is not None:
                termios.tcsetattr(real_stdin_fd, termios.TCSAFLUSH, old_tty_attrs)

        if task.process is not None:
            ret = task.process.poll()
            return ret if ret is not None else -1
        return -1

    def get_task(self, task_id: str) -> Optional[SwarmTask]:
        """Get task by ID."""
        with self._task_lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[TaskStatus] = None) -> List[SwarmTask]:
        """List all tasks, optionally filtered by status."""
        with self._task_lock:
            tasks = list(self._tasks.values())
        if status is not None:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False
            task.status = TaskStatus.CANCELLED
            task.end_time = time.time()

        if task.process is not None:
            try:
                task.process.terminate()
            except OSError:
                pass
        return True

    def counts(self) -> Dict[str, int]:
        """Return counts by status."""
        with self._task_lock:
            counts: Dict[str, int] = {}
            for t in self._tasks.values():
                counts[t.status.value] = counts.get(t.status.value, 0) + 1
            return counts
