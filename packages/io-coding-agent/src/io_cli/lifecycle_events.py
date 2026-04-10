"""Lifecycle event formatting for IO CLI.

Handles formatting of agent lifecycle events for display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


def format_lifecycle_event_lines(event_type: str, payload: dict[str, Any]) -> list[str]:
    """Format a lifecycle event into display lines.
    
    Args:
        event_type: Type of lifecycle event
        payload: Event payload dictionary
        
    Returns:
        List of formatted display lines
    """
    message = payload.get("message", "")
    
    lines: list[str] = []
    
    if event_type == "start":
        lines.append(f"▶ {message}")
    elif event_type == "complete":
        lines.append(f"✓ {message}")
    elif event_type == "error":
        lines.append(f"✗ {message}")
    elif event_type == "warning":
        lines.append(f"⚠ {message}")
    elif event_type == "info":
        lines.append(f"ℹ {message}")
    elif event_type == "progress":
        step = payload.get("step", 0)
        total = payload.get("total", 1)
        lines.append(f"⋯ {message} ({step}/{total})")
    elif event_type == "context_compacted":
        lines.append(f"📦 Context compacted")
    elif event_type == "runtime_route":
        runtime = payload.get("runtime", "unknown")
        lines.append(f"🔧 Runtime: {runtime}")
    else:
        if message:
            lines.append(f"  {message}")
    
    # Add any extra details
    if details := payload.get("details"):
        for detail in details if isinstance(details, list) else [details]:
            lines.append(f"    {detail}")
    
    return lines
