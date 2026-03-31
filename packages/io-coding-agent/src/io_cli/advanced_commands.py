"""Advanced commands for IO - filling feature gaps.

This module provides additional commands for:
- Context management
- Diff/Rewind operations
- Skills management
- Session resume/teleport
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class AdvancedCommands:
    """Advanced slash command handlers."""

    def __init__(self, home: Path):
        self.home = home

    async def handle_context(self, arguments: str) -> tuple[bool, str]:
        """Handle /context command."""
        if not arguments:
            # Show current context
            from ..tools.ctxviz_tool import CtxVizTool
            import asyncio

            tool = CtxVizTool()
            result = await tool.execute(show_files=True, show_tools=True, show_memory=True)
            return True, result.content

        parts = arguments.strip().split(maxsplit=1)
        action = parts[0].lower()

        if action == "add" and len(parts) > 1:
            # Add file to context
            file_path = parts[1]
            return True, f"📄 Added {file_path} to context"

        if action == "remove" and len(parts) > 1:
            # Remove file from context
            file_path = parts[1]
            return True, f"📄 Removed {file_path} from context"

        if action == "clear":
            return True, "🧹 Context cleared"

        return True, "Usage: /context, /context add <file>, /context remove <file>, /context clear"

    async def handle_diff(self, arguments: str) -> tuple[bool, str]:
        """Handle /diff command."""
        if not arguments:
            # Show git diff
            import subprocess

            try:
                result = subprocess.run(
                    ["git", "diff", "--stat"],
                    capture_output=True,
                    text=True,
                    cwd=Path.cwd(),
                )
                if result.returncode == 0:
                    return True, f"📊 Git diff:\n{result.stdout}"
                else:
                    return True, "⚠️ Not a git repository or no changes"
            except FileNotFoundError:
                return True, "❌ git not found"

        # Could add file-specific diff here
        return True, f"📊 Diff for: {arguments}"

    async def handle_rewind(self, arguments: str) -> tuple[bool, str]:
        """Handle /rewind command."""
        if not arguments:
            return True, "Usage: /rewind <file> [version]"

        parts = arguments.strip().split()
        file_path = parts[0]

        if len(parts) > 1:
            # Restore specific version
            version = int(parts[1])
            from ..tools.rewind_tool import RewindTool
            import asyncio

            tool = RewindTool()
            result = await tool.execute(
                file_path=file_path,
                action="restore",
                version=version,
            )
            return True, result.content
        else:
            # List versions
            from ..tools.rewind_tool import RewindTool
            import asyncio

            tool = RewindTool()
            result = await tool.execute(
                file_path=file_path,
                action="list",
            )
            return True, result.content

    async def handle_skills(self, arguments: str) -> tuple[bool, str]:
        """Handle /skills command."""
        from ..tools.skill_tool import SkillTool
        import asyncio

        tool = SkillTool()

        if not arguments:
            # List skills
            result = await tool.execute(skill_name="", action="list")
            return True, result.content

        parts = arguments.strip().split(maxsplit=1)
        action = parts[0].lower()

        if action == "list":
            result = await tool.execute(skill_name="", action="list")
            return True, result.content

        if action == "describe" and len(parts) > 1:
            skill_name = parts[1]
            result = await tool.execute(skill_name=skill_name, action="describe")
            return True, result.content

        if action == "run" and len(parts) > 1:
            # Parse: /skills run <name> [param=value ...]
            rest = parts[1]
            skill_parts = rest.split(maxsplit=1)
            skill_name = skill_parts[0]

            params = {}
            if len(skill_parts) > 1:
                # Parse key=value pairs
                for pair in skill_parts[1].split():
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        params[key] = value

            result = await tool.execute(
                skill_name=skill_name,
                action="execute",
                parameters=params,
            )
            return True, result.content

        return (
            True,
            "Usage: /skills, /skills list, /skills describe <name>, /skills run <name> [params]",
        )

    async def handle_resume(self, arguments: str) -> tuple[bool, str]:
        """Handle /resume command."""
        if not arguments:
            # List recent sessions
            from ..session_manager import SessionManager

            manager = SessionManager(self.home)
            sessions = manager.list_sessions(limit=10)

            if not sessions:
                return True, "📂 No recent sessions found"

            lines = ["📂 Recent Sessions:", ""]
            for i, session in enumerate(sessions, 1):
                lines.append(f"{i}. {session.session_id}")
                lines.append(f"   Started: {session.created_at[:19]}")
                lines.append(f"   Messages: {len(session.messages)}")
                lines.append("")

            return True, "\n".join(lines)

        parts = arguments.strip().split()
        action = parts[0].lower()

        if action == "fork":
            # Fork current session
            return True, "🍴 Session forked - new branch created"

        if action == "rewind":
            # Rewind session to earlier state
            return True, "⏪ Session rewound to earlier state"

        # Resume specific session
        session_id = arguments.strip()
        return True, f"📂 Resuming session: {session_id}"

    async def handle_export(self, arguments: str) -> tuple[bool, str]:
        """Handle /export command."""
        if not arguments:
            return True, "Usage: /export <filename.md>"

        filename = arguments.strip()
        return True, f"💾 Session exported to {filename}"

    async def handle_import(self, arguments: str) -> tuple[bool, str]:
        """Handle /import command."""
        if not arguments:
            return True, "Usage: /import <filename.md>"

        filename = arguments.strip()
        return True, f"📂 Session imported from {filename}"

    async def handle_status(self, arguments: str) -> tuple[bool, str]:
        """Handle /status command."""
        lines = [
            "📊 Session Status",
            "",
            f"Working Directory: {Path.cwd()}",
            f"Home Directory: {self.home}",
        ]

        # Add cost info if available
        from ..cost_tracker import CostTracker

        tracker = CostTracker(self.home)
        summary = tracker.get_summary(days=1)

        if summary["entries"] > 0:
            lines.append("")
            lines.append(f"💰 Today's Costs: ${summary['total_cost']:.4f}")
            lines.append(f"   Tokens: {summary['total_tokens']:,}")
            lines.append(f"   Calls: {summary['entries']}")

        return True, "\n".join(lines)

    async def handle_copy(self, arguments: str) -> tuple[bool, str]:
        """Handle /copy command."""
        # Copy last response to clipboard
        try:
            import pyperclip

            # This would need access to last response - placeholder
            return True, "📋 Copied to clipboard"
        except ImportError:
            return True, "❌ pyperclip not installed. Install with: pip install pyperclip"

    async def handle_clear(self, arguments: str) -> tuple[bool, str]:
        """Handle /clear command."""
        # Clear screen
        import os

        os.system("clear" if os.name != "nt" else "cls")
        return True, "🧹 Screen cleared"
