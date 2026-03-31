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
  model_config TEXT,
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
  payload_json TEXT,
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
            self._migrate(connection)

    def _migrate(self, connection: sqlite3.Connection) -> None:
        self._ensure_column(connection, "sessions", "model_config", "TEXT")
        self._ensure_column(connection, "messages", "payload_json", "TEXT")
        connection.commit()

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        column_type: str,
    ) -> None:
        rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
        if any(str(row["name"]) == column for row in rows):
            return
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def create_session(
        self,
        *,
        session_id: str,
        source: str,
        model: str = "",
        cwd: str = "",
        title: str = "",
        model_config: dict[str, Any] | None = None,
    ) -> None:
        config_json = json.dumps(model_config or {"cwd": cwd}, sort_keys=True)
        with self._lock, self.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO sessions (
                  id, source, cwd, model, model_config, started_at, ended_at, end_reason, title
                ) VALUES (
                  ?, ?, ?, ?, ?, COALESCE((SELECT started_at FROM sessions WHERE id = ?), ?),
                  (SELECT ended_at FROM sessions WHERE id = ?),
                  (SELECT end_reason FROM sessions WHERE id = ?),
                  ?
                )
                """,
                (
                    session_id,
                    source,
                    cwd,
                    model,
                    config_json,
                    session_id,
                    time.time(),
                    session_id,
                    session_id,
                    title,
                ),
            )
            connection.commit()

    def start_session(
        self,
        session_id: str,
        *,
        source: str,
        cwd: str,
        model: str,
        title: str = "",
        model_config: dict[str, Any] | None = None,
    ) -> None:
        self.create_session(
            session_id=session_id,
            source=source,
            cwd=cwd,
            model=model,
            title=title,
            model_config=model_config or {"cwd": cwd},
        )

    def end_session(self, session_id: str, reason: str = "completed") -> None:
        with self._lock, self.connection() as connection:
            connection.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? WHERE id = ?",
                (time.time(), reason, session_id),
            )
            connection.commit()

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str | None,
        tool_name: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        tool_call_id: str | None = None,
        payload: dict[str, Any] | None = None,
        timestamp: float | None = None,
    ) -> None:
        message_payload = payload or {
            "role": role,
            "content": content,
        }
        if tool_name:
            message_payload.setdefault("name", tool_name)
        if tool_calls:
            message_payload["tool_calls"] = tool_calls
        if tool_call_id:
            message_payload["tool_call_id"] = tool_call_id
        with self._lock, self.connection() as connection:
            connection.execute(
                """
                INSERT INTO messages (
                  session_id, role, content, tool_name, tool_call_id, payload_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    role,
                    content,
                    tool_name,
                    tool_call_id,
                    json.dumps(message_payload, sort_keys=True),
                    timestamp or time.time(),
                ),
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
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.append_message(
            session_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            payload=payload,
        )

    def clear_messages(self, session_id: str) -> None:
        with self._lock, self.connection() as connection:
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self.connection() as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return dict(row) if row is not None else None

    def delete_session(self, session_id: str) -> bool:
        with self._lock, self.connection() as connection:
            existed = connection.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            connection.commit()
        return existed is not None

    def get_messages_as_conversation(self, session_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT role, content, tool_name, tool_call_id, payload_json
                FROM messages
                WHERE session_id = ?
                ORDER BY timestamp ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        conversation: list[dict[str, Any]] = []
        for row in rows:
            payload_json = row["payload_json"]
            if payload_json:
                try:
                    payload = json.loads(payload_json)
                    if isinstance(payload, dict):
                        conversation.append(payload)
                        continue
                except json.JSONDecodeError:
                    pass
            message = {
                "role": row["role"],
                "content": row["content"],
            }
            if row["tool_name"]:
                message["name"] = row["tool_name"]
            if row["tool_call_id"]:
                message["tool_call_id"] = row["tool_call_id"]
            conversation.append(message)
        return conversation

    def search_sessions(self, source: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        query = """
            SELECT
              sessions.*,
              COUNT(messages.id) AS message_count
            FROM sessions
            LEFT JOIN messages ON messages.session_id = sessions.id
        """
        params: list[Any] = []
        if source:
            query += " WHERE sessions.source = ?"
            params.append(source)
        query += " GROUP BY sessions.id ORDER BY sessions.started_at DESC LIMIT ?"
        params.append(limit)
        with self.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def search_messages(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        return self.search(query, limit=limit)

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
