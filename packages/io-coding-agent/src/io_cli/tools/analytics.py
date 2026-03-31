"""Analytics and usage tracking system for IO.

This module provides tools for tracking usage metrics, token consumption,
session statistics, and generating insights dashboards.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import load_config

logger = logging.getLogger(__name__)

# Database path
_DB_PATH: Path | None = None
_db_lock = asyncio.Lock()


@dataclass
class UsageEvent:
    """A single usage event."""

    timestamp: float
    event_type: str  # message, tool_use, command, session_start, etc.
    session_id: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenUsage:
    """Token usage for a session or time period."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""
    provider: str = ""


@dataclass
class SessionMetrics:
    """Metrics for a single session."""

    session_id: str
    start_time: float
    end_time: float | None = None
    message_count: int = 0
    tool_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    commands_used: list[str] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    files_modified: list[str] = field(default_factory=list)
    cwd: str = ""


class AnalyticsTracker:
    """Tracks usage analytics for IO."""

    def __init__(self, home: Path):
        self.home = home
        self.db_path = home / "analytics.db"
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Initialize the analytics database."""
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Events table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                session_id TEXT NOT NULL,
                details TEXT
            )
        """
        )

        # Sessions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                start_time REAL NOT NULL,
                end_time REAL,
                message_count INTEGER DEFAULT 0,
                tool_calls TEXT,
                commands_used TEXT,
                prompt_tokens INTEGER DEFAULT 0,
                completion_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                model TEXT,
                provider TEXT,
                files_modified TEXT,
                cwd TEXT
            )
        """
        )

        # Daily aggregates
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_stats (
                date TEXT PRIMARY KEY,
                session_count INTEGER DEFAULT 0,
                message_count INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0.0,
                tool_calls INTEGER DEFAULT 0,
                unique_files_modified INTEGER DEFAULT 0
            )
        """
        )

        conn.commit()
        conn.close()

    def track_event(
        self, event_type: str, session_id: str, details: dict[str, Any] | None = None
    ) -> None:
        """Track a single event."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO events (timestamp, event_type, session_id, details)
                VALUES (?, ?, ?, ?)
            """,
                (time.time(), event_type, session_id, json.dumps(details or {})),
            )

            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to track event: {e}")

    def start_session(self, session_id: str, cwd: str = "") -> None:
        """Record session start."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO sessions
                (session_id, start_time, cwd)
                VALUES (?, ?, ?)
            """,
                (session_id, time.time(), cwd),
            )

            conn.commit()
            conn.close()

            self.track_event("session_start", session_id, {"cwd": cwd})
        except Exception as e:
            logger.warning(f"Failed to start session tracking: {e}")

    def end_session(self, session_id: str) -> None:
        """Record session end."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE sessions SET end_time = ? WHERE session_id = ?
            """,
                (time.time(), session_id),
            )

            conn.commit()
            conn.close()

            self.track_event("session_end", session_id)
        except Exception as e:
            logger.warning(f"Failed to end session tracking: {e}")

    def record_message(
        self,
        session_id: str,
        role: str,
        token_usage: TokenUsage | None = None,
    ) -> None:
        """Record a message exchange."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE sessions SET message_count = message_count + 1
                WHERE session_id = ?
            """,
                (session_id,),
            )

            if token_usage:
                cursor.execute(
                    """
                    UPDATE sessions SET
                        prompt_tokens = prompt_tokens + ?,
                        completion_tokens = completion_tokens + ?,
                        total_tokens = total_tokens + ?,
                        cost_usd = cost_usd + ?
                    WHERE session_id = ?
                """,
                    (
                        token_usage.prompt_tokens,
                        token_usage.completion_tokens,
                        token_usage.total_tokens,
                        token_usage.cost_usd,
                        session_id,
                    ),
                )

            conn.commit()
            conn.close()

            self.track_event(
                "message",
                session_id,
                {"role": role, "tokens": token_usage.total_tokens if token_usage else 0},
            )
        except Exception as e:
            logger.warning(f"Failed to record message: {e}")

    def record_tool_use(self, session_id: str, tool_name: str, success: bool = True) -> None:
        """Record a tool usage."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT tool_calls FROM sessions WHERE session_id = ?
            """,
                (session_id,),
            )
            row = cursor.fetchone()

            tool_calls = json.loads(row[0]) if row and row[0] else {}
            tool_calls[tool_name] = tool_calls.get(tool_name, 0) + 1

            cursor.execute(
                """
                UPDATE sessions SET tool_calls = ? WHERE session_id = ?
            """,
                (json.dumps(tool_calls), session_id),
            )

            conn.commit()
            conn.close()

            self.track_event("tool_use", session_id, {"tool": tool_name, "success": success})
        except Exception as e:
            logger.warning(f"Failed to record tool use: {e}")

    def record_command(self, session_id: str, command: str) -> None:
        """Record a slash command usage."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT commands_used FROM sessions WHERE session_id = ?
            """,
                (session_id,),
            )
            row = cursor.fetchone()

            commands = json.loads(row[0]) if row and row[0] else []
            commands.append(command)

            cursor.execute(
                """
                UPDATE sessions SET commands_used = ? WHERE session_id = ?
            """,
                (json.dumps(commands), session_id),
            )

            conn.commit()
            conn.close()

            self.track_event("command", session_id, {"command": command})
        except Exception as e:
            logger.warning(f"Failed to record command: {e}")

    def record_file_modification(self, session_id: str, file_path: str) -> None:
        """Record a file modification."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT files_modified FROM sessions WHERE session_id = ?
            """,
                (session_id,),
            )
            row = cursor.fetchone()

            files = json.loads(row[0]) if row and row[0] else []
            if file_path not in files:
                files.append(file_path)

            cursor.execute(
                """
                UPDATE sessions SET files_modified = ? WHERE session_id = ?
            """,
                (json.dumps(files), session_id),
            )

            conn.commit()
            conn.close()

            self.track_event("file_modify", session_id, {"file": file_path})
        except Exception as e:
            logger.warning(f"Failed to record file modification: {e}")

    def get_session_summary(self, days: int = 7) -> dict[str, Any]:
        """Get summary statistics for the given time period."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cutoff_time = time.time() - (days * 24 * 60 * 60)

            cursor.execute(
                """
                SELECT COUNT(*), SUM(message_count), SUM(total_tokens), SUM(cost_usd)
                FROM sessions
                WHERE start_time > ?
            """,
                (cutoff_time,),
            )
            row = cursor.fetchone()

            total_sessions = row[0] or 0
            total_messages = row[1] or 0
            total_tokens = row[2] or 0
            total_cost = row[3] or 0.0

            # Get top tools
            cursor.execute(
                """
                SELECT tool_calls FROM sessions WHERE start_time > ?
            """,
                (cutoff_time,),
            )
            tool_counts: dict[str, int] = defaultdict(int)
            for row in cursor.fetchall():
                if row[0]:
                    tools = json.loads(row[0])
                    for tool, count in tools.items():
                        tool_counts[tool] += count

            top_tools = sorted(tool_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            conn.close()

            return {
                "period_days": days,
                "total_sessions": total_sessions,
                "total_messages": total_messages,
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost,
                "avg_tokens_per_session": total_tokens // max(total_sessions, 1),
                "top_tools": top_tools,
            }
        except Exception as e:
            logger.warning(f"Failed to get session summary: {e}")
            return {}

    def get_daily_stats(self, days: int = 30) -> list[dict[str, Any]]:
        """Get daily usage statistics."""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            results = []
            for i in range(days):
                date = datetime.now() - timedelta(days=i)
                date_str = date.strftime("%Y-%m-%d")

                cursor.execute(
                    """
                    SELECT COUNT(*), SUM(message_count), SUM(total_tokens), SUM(cost_usd)
                    FROM sessions
                    WHERE date(datetime(start_time, 'unixepoch')) = ?
                """,
                    (date_str,),
                )
                row = cursor.fetchone()

                results.append(
                    {
                        "date": date_str,
                        "sessions": row[0] or 0,
                        "messages": row[1] or 0,
                        "tokens": row[2] or 0,
                        "cost_usd": row[3] or 0.0,
                    }
                )

            conn.close()
            return results
        except Exception as e:
            logger.warning(f"Failed to get daily stats: {e}")
            return []


class AnalyticsReportTool(Tool):
    """Generate analytics reports on usage, costs, and activity."""

    name = "analytics_report"
    description = (
        "Generate a usage analytics report for the specified time period. "
        "Shows session counts, token usage, costs, and most-used tools."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "enum": ["today", "yesterday", "week", "month", "all"],
                "description": "Time period for the report",
                "default": "week",
            },
            "days": {
                "type": "integer",
                "description": "Number of days to include (overrides period if set)",
                "minimum": 1,
                "maximum": 365,
            },
            "format": {
                "type": "string",
                "enum": ["summary", "detailed", "json"],
                "description": "Report format",
                "default": "summary",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        period = str(arguments.get("period", "week"))
        days_override = arguments.get("days")
        format_type = str(arguments.get("format", "summary"))

        # Map period to days
        period_days = {
            "today": 1,
            "yesterday": 1,
            "week": 7,
            "month": 30,
            "all": 365,
        }

        days = days_override if days_override else period_days.get(period, 7)

        tracker = AnalyticsTracker(context.home)
        summary = tracker.get_session_summary(days)

        if format_type == "json":
            return ToolResult(content=json.dumps(summary, indent=2))

        lines = [
            f"📊 IO Analytics Report - Last {days} days",
            "",
            f"Total Sessions: {summary.get('total_sessions', 0)}",
            f"Total Messages: {summary.get('total_messages', 0)}",
            f"Total Tokens: {summary.get('total_tokens', 0):,}",
            f"Total Cost: ${summary.get('total_cost_usd', 0):.4f}",
            f"Avg Tokens/Session: {summary.get('avg_tokens_per_session', 0):,}",
            "",
        ]

        top_tools = summary.get("top_tools", [])
        if top_tools:
            lines.append("Top Tools Used:")
            for tool, count in top_tools:
                lines.append(f"  {tool}: {count}")
            lines.append("")

        if format_type == "detailed":
            daily = tracker.get_daily_stats(days)
            lines.append("Daily Breakdown:")
            lines.append(
                f"{'Date':<12} {'Sessions':<10} {'Messages':<10} {'Tokens':<12} {'Cost':<10}"
            )
            lines.append("-" * 55)
            for day in daily:
                lines.append(
                    f"{day['date']:<12} {day['sessions']:<10} {day['messages']:<10} "
                    f"{day['tokens']:<12,} ${day['cost_usd']:<9.4f}"
                )

        return ToolResult(content="\n".join(lines))


class AnalyticsStatusTool(Tool):
    """Get current analytics tracking status."""

    name = "analytics_status"
    description = (
        "Check if analytics tracking is enabled and view basic stats. "
        "Shows current session info and today's usage."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        tracker = AnalyticsTracker(context.home)
        today_stats = tracker.get_session_summary(1)

        lines = [
            "📈 Analytics Status",
            "",
            f"Database: {tracker.db_path}",
            "",
            "Today's Activity:",
            f"  Sessions: {today_stats.get('total_sessions', 0)}",
            f"  Messages: {today_stats.get('total_messages', 0)}",
            f"  Tokens: {today_stats.get('total_tokens', 0):,}",
            f"  Cost: ${today_stats.get('total_cost_usd', 0):.4f}",
            "",
            "Available Reports:",
            "  analytics_report period=today",
            "  analytics_report period=week",
            "  analytics_report period=month format=detailed",
        ]

        return ToolResult(content="\n".join(lines))


class AnalyticsExportTool(Tool):
    """Export analytics data to a file."""

    name = "analytics_export"
    description = (
        "Export analytics data to JSON or CSV format for external analysis. "
        "Useful for creating custom reports or archiving."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "enum": ["json", "csv"],
                "description": "Export format",
                "default": "json",
            },
            "days": {
                "type": "integer",
                "description": "Number of days to export",
                "default": 30,
                "minimum": 1,
                "maximum": 365,
            },
            "output": {
                "type": "string",
                "description": "Output file path (optional, defaults to analytics_export_<date>.<ext>)",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        export_format = str(arguments.get("format", "json"))
        days = int(arguments.get("days", 30))
        output_path = arguments.get("output")

        tracker = AnalyticsTracker(context.home)
        daily_stats = tracker.get_daily_stats(days)

        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = context.cwd / f"analytics_export_{timestamp}.{export_format}"
        else:
            output_path = Path(str(output_path))
            if not output_path.is_absolute():
                output_path = context.cwd / output_path

        if export_format == "json":
            data = {
                "export_date": datetime.now().isoformat(),
                "period_days": days,
                "daily_stats": daily_stats,
            }
            output_path.write_text(json.dumps(data, indent=2))
        else:  # csv
            lines = ["date,sessions,messages,tokens,cost_usd"]
            for day in daily_stats:
                lines.append(
                    f"{day['date']},{day['sessions']},{day['messages']},"
                    f"{day['tokens']},{day['cost_usd']}"
                )
            output_path.write_text("\n".join(lines))

        return ToolResult(
            content=f"✓ Analytics exported to: {output_path}\n"
            f"  Period: {days} days\n"
            f"  Format: {export_format.upper()}\n"
            f"  Records: {len(daily_stats)}"
        )


class AnalyticsInsightsTool(Tool):
    """Get AI-powered insights about usage patterns."""

    name = "analytics_insights"
    description = (
        "Generate insights and recommendations based on usage patterns. "
        "Identifies trends, efficiency opportunities, and usage patterns."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "enum": ["week", "month", "all"],
                "description": "Time period for analysis",
                "default": "month",
            },
        },
        "required": [],
    }

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        period = str(arguments.get("period", "month"))
        days = {"week": 7, "month": 30, "all": 365}.get(period, 30)

        tracker = AnalyticsTracker(context.home)
        summary = tracker.get_session_summary(days)
        daily = tracker.get_daily_stats(min(days, 30))

        lines = [
            f"💡 Usage Insights - Last {days} days",
            "",
        ]

        # Calculate trends
        if len(daily) >= 7:
            recent = daily[:7]
            older = daily[7:14] if len(daily) >= 14 else []

            recent_sessions = sum(d["sessions"] for d in recent)
            older_sessions = sum(d["sessions"] for d in older) if older else recent_sessions

            if recent_sessions > older_sessions * 1.2:
                lines.append(
                    "📈 Trend: Usage is increasing! (+{:.0%})".format(
                        (recent_sessions / max(older_sessions, 1)) - 1
                    )
                )
            elif recent_sessions < older_sessions * 0.8:
                lines.append("📉 Trend: Usage is decreasing")
            else:
                lines.append("📊 Trend: Usage is stable")

        # Cost insights
        total_cost = summary.get("total_cost_usd", 0)
        if total_cost > 10:
            lines.append(f"💰 You've spent ${total_cost:.2f} in the last {days} days")
            lines.append("   Tip: Consider using a cheaper model for simpler tasks")
        elif total_cost > 0:
            lines.append(f"💰 Cost so far: ${total_cost:.4f}")

        # Tool usage insights
        top_tools = summary.get("top_tools", [])
        if top_tools:
            lines.append("")
            lines.append("🔧 Most Used Tools:")
            for tool, count in top_tools[:5]:
                lines.append(f"  {tool}: {count} uses")

        # Activity patterns
        active_days = sum(1 for d in daily if d["sessions"] > 0)
        if active_days > 0:
            lines.append("")
            lines.append(f"📅 Active days: {active_days}/{len(daily)}")
            avg_per_active = summary.get("total_sessions", 0) / active_days
            lines.append(f"   Average sessions per active day: {avg_per_active:.1f}")

        # Recommendations
        lines.append("")
        lines.append("💡 Recommendations:")
        if summary.get("total_tokens", 0) / max(summary.get("total_sessions", 1), 1) > 10000:
            lines.append("  • Consider using context compression for long sessions")
        if len(top_tools) > 5:
            lines.append("  • You're using a diverse set of tools - great exploration!")
        if total_cost > 20:
            lines.append("  • Review expensive sessions to optimize token usage")

        return ToolResult(content="\n".join(lines))


# Register tools
GLOBAL_TOOL_REGISTRY.register(AnalyticsReportTool())
GLOBAL_TOOL_REGISTRY.register(AnalyticsStatusTool())
GLOBAL_TOOL_REGISTRY.register(AnalyticsExportTool())
GLOBAL_TOOL_REGISTRY.register(AnalyticsInsightsTool())


# Convenience function for tracking from other modules
def get_tracker(home: Path) -> AnalyticsTracker:
    """Get or create an analytics tracker for the given home directory."""
    return AnalyticsTracker(home)
