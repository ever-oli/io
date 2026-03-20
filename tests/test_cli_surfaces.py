from __future__ import annotations

import json
from pathlib import Path

from io_cli.cli import main
from io_cli.session import SessionManager


def test_cli_tools_list_outputs_json(capsys) -> None:
    exit_code = main(["tools", "list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert "toolsets" in payload
    assert "tools" in payload


def test_cli_commands_outputs_registry(capsys) -> None:
    exit_code = main(["commands"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert "Session" in payload
    assert "/new" in payload["Session"]


def test_cli_status_pretty_outputs_header(capsys) -> None:
    exit_code = main(["status", "--pretty"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "IO Agent Status" in captured.out


def test_cli_sessions_show_outputs_session_metadata(tmp_path: Path, capsys) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    manager = SessionManager.create(cwd, home=tmp_path / "home")
    manager.append_message({"role": "user", "content": "hello"})

    exit_code = main(["sessions", "show", str(manager.session_path())])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["session_id"] == manager.session_id


def test_cli_gateway_run_once_invokes_runner(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "io_cli.cli.run_gateway",
        lambda **kwargs: {"ok": True, "kwargs": kwargs},
    )

    exit_code = main(["gateway", "run", "--once", "--poll-interval", "0.5", "--max-loops", "2"])
    captured = capsys.readouterr()

    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["kwargs"]["once"] is True
