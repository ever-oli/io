"""Claw Code Integration - Claude Code command/tool router and parity tracker.

This module integrates patterns from the claw-code repository (clean-room Claude Code
rewrite) into IO, providing:

1. Command/tool metadata from Claude Code's 300+ commands
2. Prompt-to-command routing using token matching
3. Parity auditing to compare IO's coverage vs Claude Code
4. Reference data for implementing missing features

Usage:
    from io_cli.claw_integration import ClawRouter, ParityAudit

    # Route a prompt to matching commands
    router = ClawRouter()
    matches = router.route_prompt("commit my changes")

    # Audit parity coverage
    audit = ParityAudit()
    report = audit.compare_with_io_commands(IO_COMMAND_REGISTRY)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

# Reference data paths
REFERENCE_DIR = Path(__file__).parent / "reference_data"
COMMANDS_PATH = REFERENCE_DIR / "claw_commands.json"
TOOLS_PATH = REFERENCE_DIR / "claw_tools.json"


@dataclass(frozen=True)
class ClawCommand:
    """A command definition from Claude Code."""

    name: str
    source_hint: str
    responsibility: str

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> ClawCommand:
        return cls(
            name=data["name"],
            source_hint=data["source_hint"],
            responsibility=data["responsibility"],
        )


@dataclass(frozen=True)
class ClawTool:
    """A tool definition from Claude Code."""

    name: str
    source_hint: str
    responsibility: str

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> ClawTool:
        return cls(
            name=data["name"],
            source_hint=data["source_hint"],
            responsibility=data["responsibility"],
        )


@dataclass(frozen=True)
class RouteMatch:
    """A matched command or tool from routing."""

    kind: str  # "command" or "tool"
    name: str
    source_hint: str
    score: int
    responsibility: str


@lru_cache(maxsize=1)
def load_claw_commands() -> tuple[ClawCommand, ...]:
    """Load all Claude Code command definitions."""
    if not COMMANDS_PATH.exists():
        return ()
    data = json.loads(COMMANDS_PATH.read_text())
    return tuple(ClawCommand.from_dict(entry) for entry in data)


@lru_cache(maxsize=1)
def load_claw_tools() -> tuple[ClawTool, ...]:
    """Load all Claude Code tool definitions."""
    if not TOOLS_PATH.exists():
        return ()
    data = json.loads(TOOLS_PATH.read_text())
    return tuple(ClawTool.from_dict(entry) for entry in data)


class ClawRouter:
    """Routes prompts to Claude Code commands and tools.

    Uses token-based scoring similar to claw-code's PortRuntime.
    """

    def __init__(self):
        self.commands = load_claw_commands()
        self.tools = load_claw_tools()

    def route_prompt(self, prompt: str, limit: int = 5) -> list[RouteMatch]:
        """Route a prompt to matching commands and tools.

        Args:
            prompt: The user's prompt to route
            limit: Maximum number of matches to return

        Returns:
            List of RouteMatch objects sorted by relevance
        """
        # Tokenize prompt
        tokens = {
            token.lower() for token in prompt.replace("/", " ").replace("-", " ").split() if token
        }

        # Score commands and tools
        command_matches = self._score_items(tokens, self.commands, "command")
        tool_matches = self._score_items(tokens, self.tools, "tool")

        # Interleave: best command, best tool, then remaining
        selected: list[RouteMatch] = []

        if command_matches:
            selected.append(command_matches.pop(0))
        if tool_matches:
            selected.append(tool_matches.pop(0))

        # Add remaining sorted by score
        remaining = sorted(command_matches + tool_matches, key=lambda m: (-m.score, m.kind, m.name))
        selected.extend(remaining[: max(0, limit - len(selected))])

        return selected[:limit]

    def _score_items(self, tokens: set[str], items: tuple[Any, ...], kind: str) -> list[RouteMatch]:
        """Score items against tokens and return sorted matches."""
        matches: list[RouteMatch] = []

        for item in items:
            score = self._calculate_score(tokens, item)
            if score > 0:
                matches.append(
                    RouteMatch(
                        kind=kind,
                        name=item.name,
                        source_hint=item.source_hint,
                        score=score,
                        responsibility=item.responsibility,
                    )
                )

        # Sort by score (descending), then name
        matches.sort(key=lambda m: (-m.score, m.name))
        return matches

    def _calculate_score(self, tokens: set[str], item: Any) -> int:
        """Calculate match score for an item against tokens."""
        score = 0
        haystacks = [item.name.lower(), item.source_hint.lower(), item.responsibility.lower()]

        for token in tokens:
            if any(token in haystack for haystack in haystacks):
                score += 1

        return score

    def find_command(self, name: str) -> ClawCommand | None:
        """Find a command by exact name."""
        needle = name.lower()
        for cmd in self.commands:
            if cmd.name.lower() == needle:
                return cmd
        return None

    def find_tool(self, name: str) -> ClawTool | None:
        """Find a tool by exact name."""
        needle = name.lower()
        for tool in self.tools:
            if tool.name.lower() == needle:
                return tool
        return None


@dataclass
class ParityReport:
    """Report comparing IO coverage to Claude Code."""

    total_claw_commands: int
    total_claw_tools: int
    matched_commands: list[str]
    missing_commands: list[str]
    matched_tools: list[str]
    missing_tools: list[str]
    coverage_pct: float
    recommendations: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render report as Markdown."""
        lines = [
            "# IO vs Claude Code Parity Report",
            "",
            f"**Command Coverage:** {len(self.matched_commands)}/{self.total_claw_commands} ({self.coverage_pct:.1f}%)",
            f"**Tool Coverage:** {len(self.matched_tools)}/{self.total_claw_tools}",
            "",
            "## Missing Commands (Top 20)",
        ]

        for cmd in self.missing_commands[:20]:
            lines.append(f"- `{cmd}`")

        if len(self.missing_commands) > 20:
            lines.append(f"- ... and {len(self.missing_commands) - 20} more")

        lines.extend(
            [
                "",
                "## Missing Tools (Top 10)",
            ]
        )

        for tool in self.missing_tools[:10]:
            lines.append(f"- `{tool}`")

        if self.recommendations:
            lines.extend(
                [
                    "",
                    "## Recommendations",
                ]
            )
            for rec in self.recommendations:
                lines.append(f"- {rec}")

        return "\n".join(lines)


class ParityAudit:
    """Audits IO's command/tool coverage against Claude Code."""

    def __init__(self):
        self.commands = load_claw_commands()
        self.tools = load_claw_tools()

    def compare_with_io_commands(self, io_command_names: list[str]) -> ParityReport:
        """Compare IO commands against Claude Code commands.

        Args:
            io_command_names: List of command names from IO's registry

        Returns:
            ParityReport showing coverage gaps
        """
        io_names_lower = {name.lower() for name in io_command_names}

        matched_commands = []
        missing_commands = []

        for cmd in self.commands:
            if cmd.name.lower() in io_names_lower:
                matched_commands.append(cmd.name)
            else:
                missing_commands.append(cmd.name)

        # For now, assume no tools are implemented (future: compare with ToolRegistry)
        matched_tools = []
        missing_tools = [tool.name for tool in self.tools]

        coverage_pct = (len(matched_commands) / len(self.commands) * 100) if self.commands else 0

        # Generate recommendations
        recommendations = self._generate_recommendations(missing_commands)

        return ParityReport(
            total_claw_commands=len(self.commands),
            total_claw_tools=len(self.tools),
            matched_commands=matched_commands,
            missing_commands=missing_commands,
            matched_tools=matched_tools,
            missing_tools=missing_tools,
            coverage_pct=coverage_pct,
            recommendations=recommendations,
        )

    def _generate_recommendations(self, missing_commands: list[str]) -> list[str]:
        """Generate implementation recommendations based on missing commands."""
        recommendations = []

        # Group by category
        git_cmds = [
            c for c in missing_commands if c in ["branch", "commit", "commit-push-pr", "diff"]
        ]
        config_cmds = [c for c in missing_commands if c in ["config", "theme", "output-style"]]

        if git_cmds:
            recommendations.append(f"Consider adding Git commands: {', '.join(git_cmds[:3])}")

        if config_cmds:
            recommendations.append(
                f"Configuration commands available: {', '.join(config_cmds[:3])}"
            )

        # High-value commands
        high_value = ["compact", "review", "plan", "skills", "memory"]
        missing_high = [c for c in high_value if c in missing_commands]
        if missing_high:
            recommendations.append(f"High-impact commands to add: {', '.join(missing_high)}")

        return recommendations


def get_claw_stats() -> dict[str, Any]:
    """Get quick stats about available claw-code data."""
    commands = load_claw_commands()
    tools = load_claw_tools()

    # Categorize commands
    categories = {}
    for cmd in commands:
        cat = cmd.source_hint.split("/")[1] if "/" in cmd.source_hint else "other"
        categories[cat] = categories.get(cat, 0) + 1

    return {
        "total_commands": len(commands),
        "total_tools": len(tools),
        "top_categories": sorted(categories.items(), key=lambda x: -x[1])[:5],
        "command_names": [c.name for c in commands[:10]],  # Sample
    }


# Convenience exports
__all__ = [
    "ClawRouter",
    "ParityAudit",
    "ParityReport",
    "RouteMatch",
    "ClawCommand",
    "ClawTool",
    "load_claw_commands",
    "load_claw_tools",
    "get_claw_stats",
]
