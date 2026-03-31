"""Enhanced Session Manager - Resume, teleport, fork, and rewind capabilities.

Features:
- Session snapshots and resumption
- Fork sessions into branches
- Rewind to previous states
- Export/import sessions
- PR-linked sessions
"""

from __future__ import annotations

import json
import shutil
import tarfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class SessionSnapshot:
    """A point-in-time snapshot of a session."""

    id: str
    session_id: str
    timestamp: str
    description: str
    messages_count: int
    files_modified: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "description": self.description,
            "messages_count": self.messages_count,
            "files_modified": self.files_modified,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        return cls(
            id=data["id"],
            session_id=data["session_id"],
            timestamp=data["timestamp"],
            description=data["description"],
            messages_count=data["messages_count"],
            files_modified=data.get("files_modified", []),
        )


class EnhancedSessionManager:
    """Enhanced session management with advanced features."""

    def __init__(self, home: Path):
        self.home = home
        self.sessions_dir = home / "agent" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self.snapshots_dir = home / "snapshots"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        self.exports_dir = home / "exports"
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        self.branches_dir = home / "branches"
        self.branches_dir.mkdir(parents=True, exist_ok=True)

    def _get_session_path(self, session_id: str) -> Path:
        """Get the path for a session file."""
        return self.sessions_dir / f"{session_id}.jsonl"

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent sessions."""
        sessions = []

        for session_file in sorted(
            self.sessions_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            try:
                # Read first line to get metadata
                with open(session_file, "r") as f:
                    first_line = f.readline()
                    if first_line:
                        data = json.loads(first_line)
                        sessions.append(
                            {
                                "session_id": data.get("session_id", session_file.stem),
                                "created_at": data.get("timestamp", ""),
                                "messages": self._count_messages(session_file),
                            }
                        )
            except (json.JSONDecodeError, IOError):
                continue

            if len(sessions) >= limit:
                break

        return sessions

    def _count_messages(self, session_file: Path) -> int:
        """Count messages in a session file."""
        try:
            with open(session_file, "r") as f:
                return sum(1 for _ in f)
        except IOError:
            return 0

    async def fork_session(self, session_id: str, branch_name: str | None = None) -> str:
        """Fork a session into a new branch.

        Returns:
            New session ID
        """
        original_path = self._get_session_path(session_id)
        if not original_path.exists():
            raise ValueError(f"Session not found: {session_id}")

        # Generate new session ID
        new_session_id = f"{session_id}_fork_{uuid.uuid4().hex[:8]}"
        if branch_name:
            new_session_id = f"{session_id}_{branch_name}"

        # Copy session file
        new_path = self._get_session_path(new_session_id)
        shutil.copy2(original_path, new_path)

        # Create branch metadata
        branch_meta = {
            "parent_session": session_id,
            "child_session": new_session_id,
            "branch_name": branch_name,
            "forked_at": datetime.now().isoformat(),
        }

        branch_file = self.branches_dir / f"{new_session_id}.json"
        branch_file.write_text(json.dumps(branch_meta, indent=2))

        return new_session_id

    async def create_snapshot(self, session_id: str, description: str = "") -> SessionSnapshot:
        """Create a snapshot of the current session state."""
        session_path = self._get_session_path(session_id)
        if not session_path.exists():
            raise ValueError(f"Session not found: {session_id}")

        snapshot_id = f"snap_{uuid.uuid4().hex[:8]}"
        snapshot_dir = self.snapshots_dir / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Copy session
        shutil.copy2(session_path, snapshot_dir / "session.jsonl")

        # Create snapshot record
        messages_count = self._count_messages(session_path)

        snapshot = SessionSnapshot(
            id=snapshot_id,
            session_id=session_id,
            timestamp=datetime.now().isoformat(),
            description=description or f"Snapshot at {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            messages_count=messages_count,
        )

        # Save snapshot metadata
        meta_file = snapshot_dir / "metadata.json"
        meta_file.write_text(json.dumps(snapshot.to_dict(), indent=2))

        return snapshot

    async def list_snapshots(self, session_id: str | None = None) -> list[SessionSnapshot]:
        """List available snapshots."""
        snapshots = []

        for snapshot_dir in self.snapshots_dir.iterdir():
            if snapshot_dir.is_dir():
                meta_file = snapshot_dir / "metadata.json"
                if meta_file.exists():
                    try:
                        data = json.loads(meta_file.read_text())
                        snapshot = SessionSnapshot.from_dict(data)

                        if session_id is None or snapshot.session_id == session_id:
                            snapshots.append(snapshot)
                    except (json.JSONDecodeError, KeyError):
                        continue

        # Sort by timestamp descending
        snapshots.sort(key=lambda s: s.timestamp, reverse=True)
        return snapshots

    async def restore_snapshot(self, snapshot_id: str, new_session: bool = True) -> str:
        """Restore a session from a snapshot.

        Args:
            snapshot_id: ID of the snapshot to restore
            new_session: If True, create a new session; if False, overwrite current

        Returns:
            Session ID (new or existing)
        """
        snapshot_dir = self.snapshots_dir / snapshot_id
        if not snapshot_dir.exists():
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        # Load metadata
        meta_file = snapshot_dir / "metadata.json"
        snapshot = SessionSnapshot.from_dict(json.loads(meta_file.read_text()))

        if new_session:
            # Create new session
            new_session_id = f"{snapshot.session_id}_restored_{uuid.uuid4().hex[:8]}"
        else:
            new_session_id = snapshot.session_id

        # Restore session file
        session_path = self._get_session_path(new_session_id)
        shutil.copy2(snapshot_dir / "session.jsonl", session_path)

        return new_session_id

    async def export_session(self, session_id: str, format: str = "markdown") -> Path:
        """Export a session to a file.

        Args:
            session_id: Session to export
            format: Export format (markdown, json, tar)

        Returns:
            Path to exported file
        """
        session_path = self._get_session_path(session_id)
        if not session_path.exists():
            raise ValueError(f"Session not found: {session_id}")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if format == "markdown":
            # Export as markdown
            export_file = self.exports_dir / f"{session_id}_{timestamp}.md"

            with open(session_path, "r") as f:
                with open(export_file, "w") as out:
                    out.write(f"# Session: {session_id}\n\n")

                    for line in f:
                        try:
                            msg = json.loads(line)
                            role = msg.get("role", "unknown")
                            content = msg.get("content", "")

                            out.write(f"## {role.upper()}\n\n")
                            out.write(f"{content}\n\n")
                            out.write("---\n\n")
                        except json.JSONDecodeError:
                            continue

        elif format == "json":
            # Export as single JSON
            export_file = self.exports_dir / f"{session_id}_{timestamp}.json"

            messages = []
            with open(session_path, "r") as f:
                for line in f:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            export_file.write_text(
                json.dumps(
                    {
                        "session_id": session_id,
                        "exported_at": datetime.now().isoformat(),
                        "messages": messages,
                    },
                    indent=2,
                )
            )

        elif format == "tar":
            # Export as tarball with session and metadata
            export_file = self.exports_dir / f"{session_id}_{timestamp}.tar.gz"

            with tarfile.open(export_file, "w:gz") as tar:
                tar.add(session_path, arcname="session.jsonl")

        else:
            raise ValueError(f"Unknown export format: {format}")

        return export_file

    async def import_session(self, file_path: Path, session_id: str | None = None) -> str:
        """Import a session from a file.

        Args:
            file_path: Path to import file
            session_id: Optional session ID (generated if not provided)

        Returns:
            Session ID
        """
        if not file_path.exists():
            raise ValueError(f"File not found: {file_path}")

        if session_id is None:
            session_id = f"imported_{uuid.uuid4().hex[:8]}"

        session_path = self._get_session_path(session_id)

        if file_path.suffix == ".tar.gz":
            # Extract tarball
            with tarfile.open(file_path, "r:gz") as tar:
                tar.extract("session.jsonl", self.sessions_dir)
                extracted = self.sessions_dir / "session.jsonl"
                extracted.rename(session_path)

        elif file_path.suffix == ".json":
            # Parse JSON and convert to JSONL
            data = json.loads(file_path.read_text())
            messages = data.get("messages", [])

            with open(session_path, "w") as f:
                for msg in messages:
                    f.write(json.dumps(msg) + "\n")

        else:
            # Assume JSONL
            shutil.copy2(file_path, session_path)

        return session_id

    async def teleport_session(self, session_id: str, destination: str) -> str:
        """Export a session for transfer to another machine (teleportation).

        Args:
            session_id: Session to teleport
            destination: Destination identifier (for tracking)

        Returns:
            Teleport package path
        """
        # Create portable package
        export_file = await self.export_session(session_id, format="tar")

        # Create teleport metadata
        teleport_meta = {
            "session_id": session_id,
            "teleported_at": datetime.now().isoformat(),
            "destination": destination,
            "package": str(export_file),
        }

        meta_file = self.exports_dir / f"{session_id}_teleport.json"
        meta_file.write_text(json.dumps(teleport_meta, indent=2))

        return export_file

    def get_session_info(self, session_id: str) -> dict[str, Any]:
        """Get detailed session information."""
        session_path = self._get_session_path(session_id)

        if not session_path.exists():
            return {"error": "Session not found"}

        messages_count = self._count_messages(session_path)
        file_size = session_path.stat().st_size

        # Check if has branches
        branches = []
        for branch_file in self.branches_dir.glob("*.json"):
            try:
                data = json.loads(branch_file.read_text())
                if data.get("parent_session") == session_id:
                    branches.append(data.get("child_session"))
            except json.JSONDecodeError:
                continue

        return {
            "session_id": session_id,
            "messages": messages_count,
            "file_size": file_size,
            "branches": branches,
            "has_branches": len(branches) > 0,
        }
