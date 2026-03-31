"""Swarm CLI commands for io-coding-agent.

Integrates io-swarm into the main io CLI.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from io_swarm import (
    ProjectRegistry,
    SwarmManager,
    print_swarm_status,
    print_task_detail,
    spawn_draft,
    spawn_formalize,
    spawn_prove,
    spawn_review,
)


def cmd_swarm(argv: List[str], config: dict, home: Path) -> int:
    """Handle 'io swarm' commands."""
    parser = argparse.ArgumentParser(
        prog="io swarm",
        description="Manage background agent swarm",
    )
    subparsers = parser.add_subparsers(dest="swarm_cmd")

    # List
    list_parser = subparsers.add_parser("list", aliases=["ls"], help="List swarm tasks")
    list_parser.add_argument("--status", help="Filter by status")

    # Spawn
    spawn_parser = subparsers.add_parser("spawn", help="Spawn a task")
    spawn_parser.add_argument("--cmd", required=True, help="Command to run")
    spawn_parser.add_argument("--description", "-d", default="", help="Task description")
    spawn_parser.add_argument("--project", "-p", default=".", help="Project directory")
    spawn_parser.add_argument("--interactive", "-i", action="store_true", help="Interactive PTY")

    # Attach
    attach_parser = subparsers.add_parser("attach", help="Attach to interactive task")
    attach_parser.add_argument("task_id", help="Task ID (e.g., io-001)")

    # Cancel
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a task")
    cancel_parser.add_argument("task_id", help="Task ID")

    # Workflows
    prove_parser = subparsers.add_parser("prove", help="Spawn proof agent")
    prove_parser.add_argument("theorem", help="Theorem to prove")
    prove_parser.add_argument("--project", "-p", default=".", help="Project directory")
    prove_parser.add_argument("--interactive", "-i", action="store_true")

    draft_parser = subparsers.add_parser("draft", help="Spawn drafting agent")
    draft_parser.add_argument("topic", help="Topic to draft")
    draft_parser.add_argument("--project", "-p", default=".", help="Project directory")

    formalize_parser = subparsers.add_parser("formalize", help="Spawn formalization agent")
    formalize_parser.add_argument("statement", help="Statement to formalize")
    formalize_parser.add_argument("--project", "-p", default=".", help="Project directory")

    args = parser.parse_args(argv)

    if not args.swarm_cmd:
        parser.print_help()
        return 0

    manager = SwarmManager()
    console = Console()

    if args.swarm_cmd in ("list", "ls"):
        print_swarm_status(manager, console)
        return 0

    elif args.swarm_cmd == "spawn":
        project_dir = Path(args.project).resolve()
        task = manager.spawn(
            command=args.cmd.split(),
            description=args.description or args.cmd,
            project_dir=project_dir,
            interactive=args.interactive,
        )
        console.print(f"[green]Spawned {task.task_id}[/green]")
        return 0

    elif args.swarm_cmd == "attach":
        try:
            console.print(f"[dim]Attaching to {args.task_id}... (Ctrl-] to detach)[/dim]")
            exit_code = manager.attach_to_task(args.task_id)
            return exit_code if exit_code is not None else 0
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            return 1

    elif args.swarm_cmd == "cancel":
        if manager.cancel(args.task_id):
            console.print(f"[green]Cancelled {args.task_id}[/green]")
        else:
            console.print(f"[red]Could not cancel {args.task_id}[/red]")
        return 0

    elif args.swarm_cmd == "prove":
        project_dir = Path(args.project).resolve()
        task = spawn_prove(
            theorem=args.theorem,
            project_dir=project_dir,
            interactive=args.interactive,
        )
        console.print(f"[green]Spawned proof agent: {task.task_id}[/green]")
        return 0

    elif args.swarm_cmd == "draft":
        project_dir = Path(args.project).resolve()
        task = spawn_draft(
            topic=args.topic,
            project_dir=project_dir,
        )
        console.print(f"[green]Spawned drafting agent: {task.task_id}[/green]")
        return 0

    elif args.swarm_cmd == "formalize":
        project_dir = Path(args.project).resolve()
        task = spawn_formalize(
            statement=args.statement,
            project_dir=project_dir,
        )
        console.print(f"[green]Spawned formalization agent: {task.task_id}[/green]")
        return 0

    return 0


def cmd_project(argv: List[str], config: dict, home: Path) -> int:
    """Handle 'io project' commands."""
    parser = argparse.ArgumentParser(
        prog="io project",
        description="Manage Lean projects",
    )
    subparsers = parser.add_subparsers(dest="project_cmd")

    # Add
    add_parser = subparsers.add_parser("add", help="Add project to registry")
    add_parser.add_argument("name", help="Project name")
    add_parser.add_argument("path", help="Project path")
    add_parser.add_argument("--description", "-d", help="Project description")

    # List
    subparsers.add_parser("list", aliases=["ls"], help="List registered projects")

    # Remove
    remove_parser = subparsers.add_parser("remove", aliases=["rm"], help="Remove project")
    remove_parser.add_argument("name", help="Project name")

    args = parser.parse_args(argv)

    if not args.project_cmd:
        parser.print_help()
        return 0

    registry_path = home / "lean" / "registry.yaml"
    registry = ProjectRegistry(registry_path)
    console = Console()

    if args.project_cmd == "add":
        path = Path(args.path).resolve()
        project = registry.add(
            name=args.name,
            path=path,
            description=args.description,
        )
        console.print(f"[green]Added project: {project.name} → {project.path}[/green]")
        return 0

    elif args.project_cmd in ("list", "ls"):
        projects = registry.list_all()
        if not projects:
            console.print("[dim]No projects registered[/dim]")
            return 0

        from rich.table import Table

        table = Table(title="Registered Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Path", style="dim")
        table.add_column("Description", style="white")

        for proj in projects:
            table.add_row(proj.name, str(proj.path), proj.description or "")

        console.print(table)
        return 0

    elif args.project_cmd in ("remove", "rm"):
        if registry.remove(args.name):
            console.print(f"[green]Removed project: {args.name}[/green]")
        else:
            console.print(f"[red]Project not found: {args.name}[/red]")
        return 1 if not registry.remove(args.name) else 0

    return 0
