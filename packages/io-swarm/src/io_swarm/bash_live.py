"""Bash live view - PTY streaming for long-running commands.

Inspired by lucasmeijer/pi-bash-live-view.
Streams terminal output in real-time for build systems and long commands.
"""

from __future__ import annotations

import fcntl
import logging
import os
import select
import struct
import subprocess
import sys
import termios
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TextIO

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)


class BashLiveView:
    """Live terminal streaming for long-running commands."""

    def __init__(
        self,
        command: List[str],
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        max_lines: int = 100,
    ):
        self.command = command
        self.cwd = cwd
        self.env = env
        self.max_lines = max_lines
        self.output_buffer: List[str] = []
        self.process: Optional[subprocess.Popen] = None
        self.pty_master: Optional[int] = None
        self._stop_event = threading.Event()
        self.exit_code: Optional[int] = None

    def _set_terminal_size(self, fd: int, rows: int = 24, cols: int = 80) -> None:
        """Set PTY terminal size."""
        try:
            size = struct.pack("HHHH", rows, cols, 0, 0)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
        except OSError:
            pass

    def _read_output(self, callback: Optional[Callable[[str], None]] = None) -> None:
        """Read output from PTY in background thread."""
        if self.pty_master is None:
            return

        while not self._stop_event.is_set():
            try:
                ready, _, _ = select.select([self.pty_master], [], [], 0.1)
                if self.pty_master in ready:
                    try:
                        data = os.read(self.pty_master, 4096)
                    except OSError:
                        break

                    if not data:
                        break

                    text = data.decode("utf-8", errors="replace")
                    lines = text.split("\n")

                    for line in lines:
                        if line:
                            self.output_buffer.append(line)
                            if len(self.output_buffer) > self.max_lines:
                                self.output_buffer.pop(0)

                            if callback:
                                callback(line)
            except (select.error, OSError):
                break

    def run(
        self,
        console: Optional[Console] = None,
        show_live: bool = True,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> int:
        """Run command with live streaming.

        Args:
            console: Rich console for display
            show_live: Whether to show live output widget
            on_output: Callback for each output line

        Returns:
            Exit code
        """
        console = console or Console()

        # Create PTY
        master_fd, slave_fd = os.openpty()
        self.pty_master = master_fd

        # Set terminal size
        self._set_terminal_size(master_fd)

        # Start process
        full_env = {**os.environ, **(self.env or {})}

        try:
            self.process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                env=full_env,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
            )
        except Exception as e:
            logger.error(f"Failed to start process: {e}")
            os.close(master_fd)
            os.close(slave_fd)
            return 1

        os.close(slave_fd)

        # Start reader thread
        reader_thread = threading.Thread(
            target=self._read_output,
            args=(on_output,),
            daemon=True,
        )
        reader_thread.start()

        if show_live:
            # Show live widget
            with Live(
                self._render_widget(),
                console=console,
                refresh_per_second=4,
            ) as live:
                while self.process.poll() is None:
                    live.update(self._render_widget())
                    import time

                    time.sleep(0.25)

                # Final update
                live.update(self._render_widget())
        else:
            # Just wait
            self.process.wait()

        # Cleanup
        self._stop_event.set()
        reader_thread.join(timeout=1.0)

        self.exit_code = self.process.returncode
        os.close(master_fd)
        self.pty_master = None

        return self.exit_code or 0

    def _render_widget(self) -> Panel:
        """Render live widget."""
        # Get recent output
        recent = self.output_buffer[-20:] if self.output_buffer else ["Starting..."]

        # Format output
        text = Text("\n".join(recent))

        # Status
        if self.process and self.process.poll() is None:
            status = "[yellow]●[/yellow] Running"
        else:
            status = "[green]●[/green] Complete" if (self.exit_code == 0) else "[red]●[/red] Failed"

        return Panel(
            text,
            title=f"[bold]{status}[/bold] {self.command[0]}",
            subtitle=f"[dim]{len(self.output_buffer)} lines[/dim]",
            border_style="blue",
        )

    def get_output(self) -> str:
        """Get full output as string."""
        return "\n".join(self.output_buffer)


def run_with_live_view(
    command: List[str],
    cwd: Optional[Path] = None,
    console: Optional[Console] = None,
) -> tuple[int, str]:
    """Convenience function to run command with live view.

    Returns:
        (exit_code, output)
    """
    viewer = BashLiveView(command, cwd=cwd)
    exit_code = viewer.run(console=console, show_live=True)
    return exit_code, viewer.get_output()
