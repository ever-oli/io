from __future__ import annotations

from pathlib import Path

from io_agent import SessionDB


def test_session_db_indexes_and_searches(tmp_path: Path) -> None:
    db = SessionDB(tmp_path / "state.db")
    db.start_session("session-1", source="cli", cwd=str(tmp_path), model="mock/io-test", title="demo")
    db.index_message("session-1", role="user", content="hello world")
    db.index_message("session-1", role="assistant", content="world building")
    rows = db.search("world")
    assert len(rows) >= 1
    assert any("world" in row["content"] for row in rows)

