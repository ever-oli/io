from __future__ import annotations

from pathlib import Path

from io_agent import SessionDB
from io_cli.trajectory_export import (
    export_trajectories_jsonl,
    list_exportable_sessions,
    summarize_export_jsonl,
)


def test_research_export_list_summary(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    db = SessionDB(home / "state.db")
    db.create_session(session_id="s1", source="cli", model="mock/io-test", cwd=str(tmp_path))
    db.append_message("s1", role="user", content="hello")
    db.append_message("s1", role="assistant", content="hi")

    rows = list_exportable_sessions(home=home, limit_sessions=10)
    assert rows
    assert rows[0]["session_id"] == "s1"
    assert rows[0]["message_count"] == 2

    out = tmp_path / "traj.jsonl"
    lines = export_trajectories_jsonl(home=home, out=out, limit_sessions=10)
    assert lines == 1
    summary = summarize_export_jsonl(out)
    assert summary["exists"] is True
    assert summary["sessions"] == 1
    assert summary["messages"] == 2
    assert summary["models"]["mock/io-test"] == 1

