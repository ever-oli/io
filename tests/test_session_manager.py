from __future__ import annotations

from pathlib import Path

from io_cli.session import SessionManager


def test_session_manager_branch_and_compaction(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    home = tmp_path / "home"
    manager = SessionManager.create(cwd, home=home)
    first = manager.append_message({"role": "user", "content": "first"})
    manager.append_message({"role": "assistant", "content": "second"})
    manager.append_compaction("summary text", first, 1234)
    manager.append_message({"role": "assistant", "content": "after summary"})

    context = manager.build_session_context()
    assert context[0]["role"] == "system"
    assert "summary text" in context[0]["content"]
    assert context[-1]["content"] == "after summary"

    manager.branch(first)
    manager.append_message({"role": "user", "content": "side branch"})
    tree = manager.get_tree()
    assert len(tree[first]) >= 2

