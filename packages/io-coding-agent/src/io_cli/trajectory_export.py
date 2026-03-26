"""Export indexed sessions to JSONL for RL / trajectory tooling (optional, lightweight)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TextIO

from io_agent import SessionDB


def export_trajectories_jsonl(
    *,
    home: Path,
    out: Path,
    limit_sessions: int = 200,
) -> int:
    """Write one JSON object per line: session metadata + messages[]. Returns lines written."""
    db_path = home / "state.db"
    if not db_path.exists():
        out.write_text("", encoding="utf-8")
        return 0
    db = SessionDB(db_path)
    lines = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        lines = _write_jsonl(db, handle, limit_sessions=limit_sessions)
    return lines


def _write_jsonl(db: SessionDB, handle: TextIO, *, limit_sessions: int) -> int:
    lines = 0
    with db.connection() as connection:
        session_rows = connection.execute(
            """
            SELECT id, source, cwd, model, title, started_at
            FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (max(1, int(limit_sessions)),),
        ).fetchall()
    for row in session_rows:
        sid = str(row["id"])
        record: dict[str, Any] = {
            "session_id": sid,
            "source": row["source"],
            "cwd": row["cwd"],
            "model": row["model"],
            "title": row["title"],
            "started_at": row["started_at"],
            "messages": db.get_messages_as_conversation(sid),
        }
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        lines += 1
    return lines


def list_exportable_sessions(*, home: Path, limit_sessions: int = 200) -> list[dict[str, Any]]:
    """Return lightweight metadata for sessions that would be exported."""
    db_path = home / "state.db"
    if not db_path.exists():
        return []
    db = SessionDB(db_path)
    out: list[dict[str, Any]] = []
    with db.connection() as connection:
        rows = connection.execute(
            """
            SELECT id, source, cwd, model, title, started_at
            FROM sessions
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (max(1, int(limit_sessions)),),
        ).fetchall()
    for row in rows:
        sid = str(row["id"])
        msgs = db.get_messages_as_conversation(sid)
        out.append(
            {
                "session_id": sid,
                "source": row["source"],
                "cwd": row["cwd"],
                "model": row["model"],
                "title": row["title"],
                "started_at": row["started_at"],
                "message_count": len(msgs),
            }
        )
    return out


def summarize_export_jsonl(path: Path) -> dict[str, Any]:
    """Summarize an exported trajectory JSONL file."""
    if not path.exists():
        return {"exists": False, "sessions": 0, "messages": 0, "models": {}}
    sessions = 0
    messages = 0
    models: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            sessions += 1
            model = str(row.get("model") or "unknown")
            models[model] = models.get(model, 0) + 1
            msgs = row.get("messages")
            if isinstance(msgs, list):
                messages += len(msgs)
    return {
        "exists": True,
        "sessions": sessions,
        "messages": messages,
        "models": models,
        "path": str(path),
    }
