"""SQLite session index and transcript storage."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  cwd TEXT,
  model TEXT,
  started_at REAL NOT NULL,
  ended_at REAL,
  end_reason TEXT,
  title TEXT
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  role TEXT NOT NULL,
  content TEXT,
  tool_name TEXT,
  tool_call_id TEXT,
  timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content=messages, content_rowid=id);
CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


@dataclass
class SessionDB:
    path: Path

    def __post_init__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connection() as connection:
            connection.executescript(SCHEMA_SQL)
            connection.executescript(FTS_SQL)

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def start_session(self, session_id: str, *, source: str, cwd: str, model: str, title: str = "") -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO sessions (id, source, cwd, model, started_at, title) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, source, cwd, model, time.time(), title),
            )
            connection.commit()

    def end_session(self, session_id: str, reason: str = "completed") -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? WHERE id = ?",
                (time.time(), reason, session_id),
            )
            connection.commit()

    def index_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "INSERT INTO messages (session_id, role, content, tool_name, tool_call_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, content, tool_name, tool_call_id, time.time()),
            )
            connection.commit()

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT messages.session_id, messages.role, messages.content, sessions.title, sessions.cwd
                FROM messages_fts
                JOIN messages ON messages.id = messages_fts.rowid
                JOIN sessions ON sessions.id = messages.session_id
                WHERE messages_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [dict(row) for row in rows]


@dataclass
class SessionStore:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, session_id: str, message: dict[str, Any]) -> Path:
        path = self.root / f"{session_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message, sort_keys=True) + "\n")
        return path

    def load(self, session_id: str) -> list[dict[str, Any]]:
        path = self.root / f"{session_id}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

