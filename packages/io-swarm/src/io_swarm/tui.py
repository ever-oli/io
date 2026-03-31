"""Swarm TUI - Rich table displays for swarm status."""

from __future__ import annotations

import time
from typing import Optional

from rich.console import Console
from rich.table import Table

from .manager import SwarmManager, SwarmTask, TaskStatus


def format_elapsed(seconds: float) -> str:
    """Format elapsed time compactly."""
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h{minutes}m"


def status_indicator(status: TaskStatus) -> str:
    """Get colored status indicator."""
    colors = {
        TaskStatus.QUEUED: "[dim]○ queued[/]",
        TaskStatus.RUNNING: "[yellow]● running[/]",
        TaskStatus.COMPLETE: "[green]● done[/]",
        TaskStatus.FAILED: "[red]● failed[/]",
        TaskStatus.CANCELLED: "[dim]● cancel[/]",
    }
    return colors.get(status, str(status.value))


def render_swarm_table(manager: SwarmManager) -> Table:
    """Render Rich table of all swarm tasks."""
    table = Table(
        title="[bold blue]IO Swarm[/]",
        show_header=True,
        header_style="bold",
    )

    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Description", style="white", max_width=40)
    table.add_column("Project", style="dim", max_width=20)
    table.add_column("Status", no_wrap=True)
    table.add_column("Time", style="dim", no_wrap=True, justify="right")
    table.add_column("Progress", style="dim")

    now = time.time()
    for task in manager.list_tasks():
        elapsed = "—"
        if task.start_time is not None:
            end = task.end_time if task.end_time is not None else now
            elapsed = format_elapsed(end - task.start_time)

        project_name = task.project_dir.name
        progress = task.progress
        if task.pty_master_fd is not None and task.status == TaskStatus.RUNNING:
            progress += " [dim]› attach[/]"

        table.add_row(
            task.task_id,
            task.description,
            project_name,
            status_indicator(task.status),
            elapsed,
            progress,
        )

    return table


def render_task_detail(task: SwarmTask) -> Table:
    """Render detailed view of single task."""
    table = Table(
        title=f"[bold blue]Task {task.task_id}[/]",
        show_header=False,
        pad_edge=True,
    )

    table.add_column("Key", style="bold dim", no_wrap=True)
    table.add_column("Value", style="white")

    now = time.time()
    elapsed = "—"
    if task.start_time is not None:
        end = task.end_time if task.end_time is not None else now
        elapsed = format_elapsed(end - task.start_time)

    table.add_row("ID", task.task_id)
    table.add_row("Description", task.description)
    table.add_row("Command", task.command)
    table.add_row("Project", str(task.project_dir))
    table.add_row("Status", status_indicator(task.status))
    table.add_row("Elapsed", elapsed)
    table.add_row("Progress", task.progress)

    if task.pty_master_fd is not None and task.status == TaskStatus.RUNNING:
        table.add_row(
            "Attach", "[green]/swarm attach {0}[/] (Ctrl-] to detach)".format(task.task_id)
        )

    if task.exit_code is not None:
        table.add_row("Exit Code", str(task.exit_code))

    if task.error_message:
        table.add_row("Error", f"[red]{task.error_message}[/]")

    return table


def render_swarm_summary(manager: SwarmManager) -> Optional[str]:
    """Render one-line summary for status bar."""
    counts = manager.counts()
    if not counts:
        return None

    running = counts.get("running", 0)
    complete = counts.get("complete", 0)
    queued = counts.get("queued", 0)
    failed = counts.get("failed", 0)

    parts = []
    if running:
        noun = "agent" if running == 1 else "agents"
        parts.append(f"[yellow]{running} {noun} running[/]")
    if complete:
        parts.append(f"[green]{complete} complete[/]")
    if queued:
        parts.append(f"[dim]{queued} queued[/]")
    if failed:
        parts.append(f"[red]{failed} failed[/]")

    if not parts:
        return None

    return "[dim]Swarm:[/] " + " [dim]·[/] ".join(parts)


def print_swarm_status(manager: SwarmManager, console: Optional[Console] = None) -> None:
    """Print swarm status to console."""
    console = console or Console()
    tasks = manager.list_tasks()

    if not tasks:
        console.print("[dim]No active swarm tasks.[/]")
        return

    table = render_swarm_table(manager)
    console.print(table)

    summary = render_swarm_summary(manager)
    if summary:
        console.print(f"\n{summary}")


def print_task_detail(task: SwarmTask, console: Optional[Console] = None) -> None:
    """Print detailed task info."""
    console = console or Console()
    table = render_task_detail(task)
    console.print(table)
