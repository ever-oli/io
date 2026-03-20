"""Pi-style JSONL session manager."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ensure_io_home


def _entry_id() -> str:
    return uuid.uuid4().hex[:8]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _bucket_name(cwd: Path) -> str:
    return cwd.resolve().as_posix().strip("/").replace("/", "-") or "root"


@dataclass
class SessionManager:
    cwd: Path
    session_file: Path
    session_id: str
    header: dict[str, Any]
    entries: list[dict[str, Any]] = field(default_factory=list)
    leaf_id: str | None = None

    @classmethod
    def create(cls, cwd: Path, *, home: Path | None = None) -> "SessionManager":
        home = ensure_io_home(home)
        session_dir = home / "agent" / "sessions" / _bucket_name(cwd)
        session_dir.mkdir(parents=True, exist_ok=True)
        session_id = uuid.uuid4().hex
        session_file = session_dir / f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{session_id[:8]}.jsonl"
        header = {
            "type": "session",
            "version": 3,
            "id": session_id,
            "timestamp": _timestamp(),
            "cwd": str(cwd.resolve()),
        }
        manager = cls(cwd=cwd.resolve(), session_file=session_file, session_id=session_id, header=header)
        manager._write_header()
        return manager

    @classmethod
    def open(cls, session_file: Path) -> "SessionManager":
        lines = [json.loads(line) for line in session_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines or lines[0].get("type") != "session":
            raise ValueError(f"Invalid session file: {session_file}")
        header = lines[0]
        entries = lines[1:]
        leaf_id = entries[-1]["id"] if entries else None
        return cls(
            cwd=Path(header["cwd"]),
            session_file=session_file,
            session_id=header["id"],
            header=header,
            entries=entries,
            leaf_id=leaf_id,
        )

    @classmethod
    def continue_recent(cls, cwd: Path, *, home: Path | None = None) -> "SessionManager":
        home = ensure_io_home(home)
        session_dir = home / "agent" / "sessions" / _bucket_name(cwd)
        session_dir.mkdir(parents=True, exist_ok=True)
        candidates = sorted(session_dir.glob("*.jsonl"))
        if not candidates:
            return cls.create(cwd, home=home)
        return cls.open(candidates[-1])

    @staticmethod
    def list_for_cwd(cwd: Path, *, home: Path | None = None) -> list[Path]:
        home = ensure_io_home(home)
        session_dir = home / "agent" / "sessions" / _bucket_name(cwd)
        session_dir.mkdir(parents=True, exist_ok=True)
        return sorted(session_dir.glob("*.jsonl"))

    def _write_header(self) -> None:
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        self.session_file.write_text(json.dumps(self.header, sort_keys=True) + "\n", encoding="utf-8")

    def _append(self, entry: dict[str, Any]) -> str:
        if not self.session_file.exists():
            self._write_header()
        with self.session_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        self.entries.append(entry)
        self.leaf_id = entry.get("id", self.leaf_id)
        return str(entry.get("id"))

    def _entry(self, entry_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": entry_type,
            "id": _entry_id(),
            "parentId": self.leaf_id,
            "timestamp": _timestamp(),
            **payload,
        }

    def append_message(self, message: dict[str, Any]) -> str:
        return self._append(self._entry("message", {"message": message}))

    def append_compaction(
        self,
        summary: str,
        first_kept_entry_id: str | None,
        tokens_before: int,
        details: dict[str, Any] | None = None,
        from_hook: bool = False,
    ) -> str:
        payload = {
            "summary": summary,
            "firstKeptEntryId": first_kept_entry_id,
            "tokensBefore": tokens_before,
        }
        if details:
            payload["details"] = details
        if from_hook:
            payload["fromHook"] = True
        return self._append(self._entry("compaction", payload))

    def append_branch_summary(
        self,
        from_id: str,
        summary: str,
        details: dict[str, Any] | None = None,
        from_hook: bool = False,
    ) -> str:
        payload = {"fromId": from_id, "summary": summary}
        if details:
            payload["details"] = details
        if from_hook:
            payload["fromHook"] = True
        return self._append(self._entry("branch_summary", payload))

    def append_custom_message_entry(
        self,
        custom_type: str,
        content: Any,
        display: bool = True,
        details: dict[str, Any] | None = None,
    ) -> str:
        payload = {"customType": custom_type, "content": content, "display": display}
        if details:
            payload["details"] = details
        return self._append(self._entry("custom_message", payload))

    def append_session_info(self, name: str) -> str:
        return self._append(self._entry("session_info", {"name": name}))

    def get_session_name(self) -> str | None:
        for entry in reversed(self.entries):
            if entry.get("type") == "session_info":
                return entry.get("name")
        return None

    def get_entries(self) -> list[dict[str, Any]]:
        return list(self.entries)

    def get_entry(self, entry_id: str) -> dict[str, Any] | None:
        for entry in self.entries:
            if entry.get("id") == entry_id:
                return entry
        return None

    def get_branch(self, from_id: str | None = None) -> list[dict[str, Any]]:
        current_id = from_id or self.leaf_id
        by_id = {entry["id"]: entry for entry in self.entries}
        branch = []
        while current_id:
            entry = by_id[current_id]
            branch.append(entry)
            current_id = entry.get("parentId")
        branch.reverse()
        return branch

    def branch(self, entry_id: str) -> None:
        if self.get_entry(entry_id) is None:
            raise KeyError(f"Unknown entry: {entry_id}")
        self.leaf_id = entry_id

    def get_tree(self) -> dict[str | None, list[str]]:
        tree: dict[str | None, list[str]] = {}
        for entry in self.entries:
            tree.setdefault(entry.get("parentId"), []).append(entry["id"])
        return tree

    def build_session_context(self) -> list[dict[str, Any]]:
        context: list[dict[str, Any]] = []
        for entry in self.get_branch():
            entry_type = entry.get("type")
            if entry_type == "message":
                context.append(entry["message"])
            elif entry_type == "compaction":
                context = [{"role": "system", "content": f"Conversation summary:\n{entry['summary']}"}]
            elif entry_type == "branch_summary":
                context.append({"role": "system", "content": f"Branch summary:\n{entry['summary']}"})
            elif entry_type == "custom_message":
                context.append(
                    {
                        "role": "custom",
                        "content": entry.get("content", ""),
                        "custom_type": entry.get("customType"),
                        "display": entry.get("display", True),
                    }
                )
        return context

    def session_path(self) -> Path:
        return self.session_file

