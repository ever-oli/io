"""Lifecycle event formatting for IO CLI.

Handles formatting of agent lifecycle events for display.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


def format_lifecycle_event_lines(event: dict[str, Any]) -> list[str]:
    """Format a lifecycle event into display lines.
    
    Args:
        event: Lifecycle event dictionary with type, message, etc.
        
    Returns:
        List of formatted display lines
    """
    event_type = event.get("type", "unknown")
    message = event.get("message", "")
    
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
        step = event.get("step", 0)
        total = event.get("total", 1)
        lines.append(f"⋯ {message} ({step}/{total})")
    else:
        lines.append(f"  {message}")
    
    # Add any extra details
    if details := event.get("details"):
        for detail in details if isinstance(details, list) else [details]:
            lines.append(f"    {detail}")
    
    return lines
