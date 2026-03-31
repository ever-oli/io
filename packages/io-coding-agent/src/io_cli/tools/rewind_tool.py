"""RewindTool - Rewind files to previous state.

Restore files to a previous version or undo changes.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from io_agent import Tool, ToolContext, ToolResult


class RewindTool(Tool):
    """Rewind/restore files to previous versions."""

    name = "rewind"
    description = "Rewind files to a previous state. Restore from backups or undo recent changes."

    async def execute(
        self,
        file_path: str,
        action: str = "list",
        version: int | None = None,
        context: ToolContext | None = None,
    ) -> ToolResult:
        """Execute rewind operation.

        Args:
            file_path: Path to file to rewind
            action: Action to perform (list, restore, backup)
            version: Version number to restore (for restore action)
            context: Tool execution context
        """
        path = Path(file_path)
        backup_dir = (
            Path.home()
            / ".io"
            / "backups"
            / path.parent.relative_to(path.parent.anchor if path.is_absolute() else ".")
        )
        backup_dir.mkdir(parents=True, exist_ok=True)

        if action == "list":
            return await self._list_versions(backup_dir, path.name)
        elif action == "backup":
            return await self._create_backup(path, backup_dir)
        elif action == "restore":
            if version is None:
                return ToolResult(content="❌ Version number required for restore", is_error=True)
            return await self._restore_version(path, backup_dir, version)
        else:
            return ToolResult(content=f"❌ Unknown action: {action}", is_error=True)

    async def _list_versions(self, backup_dir: Path, filename: str) -> ToolResult:
        """List available versions."""
        versions = []

        for backup_file in sorted(backup_dir.glob(f"{filename}.*.bak"), reverse=True):
            try:
                # Parse timestamp from filename
                timestamp_str = backup_file.suffixes[0][1:]  # Remove leading dot
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")

                # Get metadata
                meta_file = backup_file.with_suffix(backup_file.suffix + ".meta")
                if meta_file.exists():
                    meta = json.loads(meta_file.read_text())
                else:
                    meta = {}

                versions.append(
                    {
                        "version": len(versions) + 1,
                        "timestamp": timestamp.isoformat(),
                        "size": backup_file.stat().st_size,
                        "description": meta.get("description", "Auto-backup"),
                    }
                )
            except (ValueError, json.JSONDecodeError):
                continue

        if not versions:
            return ToolResult(content=f"📂 No backups found for {filename}")

        lines = [f"📜 Available Versions for {filename}:", ""]
        for v in versions:
            lines.append(f"Version {v['version']}:")
            lines.append(f"  Time: {v['timestamp']}")
            lines.append(f"  Size: {v['size']} bytes")
            lines.append(f"  Note: {v['description']}")
            lines.append("")

        return ToolResult(content="\n".join(lines), data={"versions": versions})

    async def _create_backup(self, path: Path, backup_dir: Path) -> ToolResult:
        """Create a backup of current file."""
        if not path.exists():
            return ToolResult(content=f"❌ File not found: {path}", is_error=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"{path.name}.{timestamp}.bak"

        # Copy file
        import shutil

        shutil.copy2(path, backup_file)

        # Create metadata
        meta = {
            "timestamp": timestamp,
            "description": "Manual backup",
            "original_path": str(path),
        }
        meta_file = backup_file.with_suffix(backup_file.suffix + ".meta")
        meta_file.write_text(json.dumps(meta, indent=2))

        return ToolResult(
            content=f"✅ Created backup: {backup_file.name}",
            data={"backup_file": str(backup_file)},
        )

    async def _restore_version(self, path: Path, backup_dir: Path, version: int) -> ToolResult:
        """Restore a specific version."""
        # Get list of backups
        backups = sorted(backup_dir.glob(f"{path.name}.*.bak"), reverse=True)

        if version < 1 or version > len(backups):
            return ToolResult(
                content=f"❌ Invalid version {version}. Available: 1-{len(backups)}",
                is_error=True,
            )

        backup_file = backups[version - 1]

        # Create backup of current state first
        if path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            current_backup = backup_dir / f"{path.name}.{timestamp}.bak"
            import shutil

            shutil.copy2(path, current_backup)

        # Restore
        import shutil

        shutil.copy2(backup_file, path)

        return ToolResult(
            content=f"✅ Restored {path.name} to version {version} (from {backup_file.name})",
            data={
                "restored_from": str(backup_file),
                "version": version,
            },
        )
