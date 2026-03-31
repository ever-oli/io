"""Claw Code CLI commands for IO.

Adds `io claw` subcommands for accessing Claude Code reference data,
routing prompts, and running parity audits.
"""

from __future__ import annotations

import argparse
from typing import Any

from . import ClawRouter, ParityAudit, get_claw_stats, load_claw_commands, load_claw_tools


def add_claw_subparser(subparsers: Any) -> None:
    """Add the 'claw' subparser to the main CLI."""
    claw = subparsers.add_parser("claw", help="Claude Code reference data and parity tracking")
    claw_subparsers = claw.add_subparsers(dest="claw_command")

    # stats
    claw_subparsers.add_parser("stats", help="Show claw-code statistics")

    # route
    route = claw_subparsers.add_parser("route", help="Route a prompt to matching commands/tools")
    route.add_argument("prompt", help="Prompt to route")
    route.add_argument("--limit", type=int, default=5, help="Max matches to show")

    # audit
    audit = claw_subparsers.add_parser("audit", help="Run parity audit vs IO commands")
    audit.add_argument("--json", action="store_true", help="Output as JSON")

    # commands
    commands = claw_subparsers.add_parser("commands", help="List all Claude Code commands")
    commands.add_argument("--limit", type=int, default=20)
    commands.add_argument("--search", help="Filter by keyword")

    # tools
    tools = claw_subparsers.add_parser("tools", help="List all Claude Code tools")
    tools.add_argument("--limit", type=int, default=20)
    tools.add_argument("--search", help="Filter by keyword")

    # show-command
    show_cmd = claw_subparsers.add_parser("show-command", help="Show command details")
    show_cmd.add_argument("name", help="Command name")

    # show-tool
    show_tool = claw_subparsers.add_parser("show-tool", help="Show tool details")
    show_tool.add_argument("name", help="Tool name")


def handle_claw_command(args: argparse.Namespace) -> int:
    """Handle claw subcommands."""

    if args.claw_command == "stats":
        stats = get_claw_stats()
        print(f"Claw Code Statistics")
        print(f"====================")
        print(f"Total Commands: {stats['total_commands']}")
        print(f"Total Tools: {stats['total_tools']}")
        print(f"\nTop Categories:")
        for cat, count in stats["top_categories"]:
            print(f"  {cat}: {count}")
        print(f"\nSample Commands:")
        for cmd in stats["command_names"]:
            print(f"  - {cmd}")
        return 0

    if args.claw_command == "route":
        router = ClawRouter()
        matches = router.route_prompt(args.prompt, limit=args.limit)

        if not matches:
            print(f"No matches found for: {args.prompt}")
            return 0

        print(f"Matches for: {args.prompt}")
        print("=" * 50)
        for i, match in enumerate(matches, 1):
            print(f"\n{i}. [{match.kind.upper()}] {match.name} (score: {match.score})")
            print(f"   Source: {match.source_hint}")
            print(f"   {match.responsibility}")
        return 0

    if args.claw_command == "audit":
        # Get IO commands - import here to avoid circular imports
        from ..commands import COMMAND_REGISTRY

        io_names = [cmd.name for cmd in COMMAND_REGISTRY]
        audit = ParityAudit()
        report = audit.compare_with_io_commands(io_names)

        if args.json:
            import json

            data = {
                "total_claw_commands": report.total_claw_commands,
                "total_claw_tools": report.total_claw_tools,
                "matched_commands": report.matched_commands,
                "missing_commands": report.missing_commands,
                "matched_tools": report.matched_tools,
                "missing_tools": report.missing_tools,
                "coverage_pct": report.coverage_pct,
                "recommendations": report.recommendations,
            }
            print(json.dumps(data, indent=2))
        else:
            print(report.to_markdown())
        return 0

    if args.claw_command == "commands":
        commands = load_claw_commands()

        if args.search:
            needle = args.search.lower()
            commands = [
                c
                for c in commands
                if needle in c.name.lower() or needle in c.responsibility.lower()
            ]

        print(f"Claude Code Commands ({len(commands)} total)")
        print("=" * 60)
        for cmd in commands[: args.limit]:
            print(f"\n{cmd.name}")
            print(f"  Source: {cmd.source_hint}")
            print(f"  {cmd.responsibility}")

        if len(commands) > args.limit:
            print(f"\n... and {len(commands) - args.limit} more")
        return 0

    if args.claw_command == "tools":
        tools = load_claw_tools()

        if args.search:
            needle = args.search.lower()
            tools = [
                t for t in tools if needle in t.name.lower() or needle in t.responsibility.lower()
            ]

        print(f"Claude Code Tools ({len(tools)} total)")
        print("=" * 60)
        for tool in tools[: args.limit]:
            print(f"\n{tool.name}")
            print(f"  Source: {tool.source_hint}")
            print(f"  {tool.responsibility}")

        if len(tools) > args.limit:
            print(f"\n... and {len(tools) - args.limit} more")
        return 0

    if args.claw_command == "show-command":
        router = ClawRouter()
        cmd = router.find_command(args.name)

        if not cmd:
            print(f"Command not found: {args.name}")
            return 1

        print(f"Command: {cmd.name}")
        print(f"Source: {cmd.source_hint}")
        print(f"\n{cmd.responsibility}")
        return 0

    if args.claw_command == "show-tool":
        router = ClawRouter()
        tool = router.find_tool(args.name)

        if not tool:
            print(f"Tool not found: {args.name}")
            return 1

        print(f"Tool: {tool.name}")
        print(f"Source: {tool.source_hint}")
        print(f"\n{tool.responsibility}")
        return 0

    # No subcommand - print help
    print("Usage: io claw <command>")
    print("\nCommands:")
    print("  stats          Show claw-code statistics")
    print("  route          Route a prompt to commands/tools")
    print("  audit          Run parity audit vs IO")
    print("  commands       List all Claude Code commands")
    print("  tools          List all Claude Code tools")
    print("  show-command   Show command details")
    print("  show-tool      Show tool details")
    return 0
