"""Edit diff preview utilities for IO CLI.

Provides file snapshot capture and diff summarization for edit operations.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def capture_local_edit_snapshot(file_path: Path | str) -> str:
    """Capture the current content of a file for diff comparison.
    
    Args:
        file_path: Path to the file to snapshot
        
    Returns:
        Current file content as string, or empty string if file doesn't exist
    """
    path = Path(file_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except (IOError, OSError):
        return ""


def summarize_diff_lines(
    original: str,
    modified: str,
    max_lines: int = 10,
    context_lines: int = 2,
) -> list[str]:
    """Generate a summary of diff between original and modified content.
    
    Args:
        original: Original file content
        modified: Modified file content
        max_lines: Maximum number of diff lines to return
        context_lines: Number of context lines around each change
        
    Returns:
        List of diff summary lines
    """
    if original == modified:
        return ["No changes made."]
    
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    
    # Ensure lines end with newline for proper diff
    if original_lines and not original_lines[-1].endswith("\n"):
        original_lines[-1] += "\n"
    if modified_lines and not modified_lines[-1].endswith("\n"):
        modified_lines[-1] += "\n"
    
    # Generate unified diff
    diff = list(difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile="original",
        tofile="modified",
        n=context_lines,
    ))
    
    if not diff:
        return ["No changes made."]
    
    # Skip the first two lines (---/+++ headers)
    diff_lines = diff[2:] if len(diff) > 2 else diff
    
    # Truncate if too long
    if len(diff_lines) > max_lines:
        half = max_lines // 2
        diff_lines = diff_lines[:half] + ["..."] + diff_lines[-half:]
    
    # Strip newlines for display
    return [line.rstrip("\n") for line in diff_lines]


def format_edit_preview(
    file_path: Path | str,
    original: str,
    modified: str,
    max_diff_lines: int = 10,
) -> str:
    """Format a preview of an edit operation.
    
    Args:
        file_path: Path to the edited file
        original: Original content
        modified: Modified content
        max_diff_lines: Maximum diff lines to show
        
    Returns:
        Formatted preview string
    """
    path = Path(file_path)
    
    if original == modified:
        return f"No changes to {path.name}"
    
    diff_lines = summarize_diff_lines(original, modified, max_diff_lines)
    
    preview = [f"Changes to {path.name}:"]
    preview.extend(diff_lines)
    
    # Add summary
    added = sum(1 for line in diff_lines if line.startswith("+"))
    removed = sum(1 for line in diff_lines if line.startswith("-"))
    preview.append(f"\n(+{added} / -{removed} lines)")
    
    return "\n".join(preview)
