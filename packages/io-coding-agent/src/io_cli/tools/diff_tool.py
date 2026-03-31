"""DiffTool - Show changes and diffs.

Display unified diffs of file changes, similar to git diff.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult


class DiffTool(Tool):
    """Show unified diff of changes between files or content."""

    name = "diff"
    description = "Show unified diff between files, or between current content and proposed changes. Supports git-style diffs with context."

    async def execute(
        self,
        file_path: str | None = None,
        original_content: str | None = None,
        new_content: str | None = None,
        original_file: str | None = None,
        new_file: str | None = None,
        context_lines: int = 3,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Show diff.

        Args:
            file_path: File to show diff for (compares current vs last saved)
            original_content: Original content as string
            new_content: New content as string
            original_file: Path to original file
            new_file: Path to new file
            context_lines: Number of context lines in diff
            context: Tool execution context
        """
        try:
            # Get original content
            if original_file:
                orig_path = Path(original_file)
                if not orig_path.exists():
                    return ToolResult(
                        content=f"❌ Original file not found: {original_file}", is_error=True
                    )
                old_lines = orig_path.read_text().splitlines()
            elif original_content is not None:
                old_lines = original_content.splitlines()
            elif file_path:
                # Check if we have a backup/version
                file_path_obj = Path(file_path)
                if file_path_obj.exists():
                    old_lines = file_path_obj.read_text().splitlines()
                else:
                    old_lines = []
            else:
                return ToolResult(
                    content="❌ Must provide file_path, original_content, or original_file",
                    is_error=True,
                )

            # Get new content
            if new_file:
                new_path = Path(new_file)
                if not new_path.exists():
                    return ToolResult(content=f"❌ New file not found: {new_file}", is_error=True)
                new_lines = new_path.read_text().splitlines()
            elif new_content is not None:
                new_lines = new_content.splitlines()
            else:
                return ToolResult(content="❌ Must provide new_content or new_file", is_error=True)

            # Generate unified diff
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile="original",
                tofile="modified",
                lineterm="",
                n=context_lines,
            )

            diff_text = "\n".join(diff)

            if not diff_text:
                return ToolResult(content="✅ No differences found - files/content are identical")

            # Count changes
            additions = sum(
                1
                for line in diff_text.splitlines()
                if line.startswith("+") and not line.startswith("+++")
            )
            deletions = sum(
                1
                for line in diff_text.splitlines()
                if line.startswith("-") and not line.startswith("---")
            )

            summary = f"📊 Diff Summary: +{additions} additions, -{deletions} deletions"

            return ToolResult(
                content=f"{summary}\n\n```diff\n{diff_text}\n```",
                data={
                    "additions": additions,
                    "deletions": deletions,
                    "diff": diff_text,
                },
            )

        except Exception as e:
            return ToolResult(content=f"❌ Error generating diff: {e}", is_error=True)
