from __future__ import annotations

from pathlib import Path

from io_tui.terminal_title import format_io_window_title, set_terminal_title


def test_format_io_window_title_uses_tilde(tmp_path: Path, monkeypatch) -> None:
    fake_home = tmp_path / "h"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    proj = fake_home / "repo" / "nested"
    proj.mkdir(parents=True)
    title = format_io_window_title(proj)
    assert "φ io" in title
    assert "~/repo/nested" in title


def test_format_io_window_title_outside_home(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    other = tmp_path / "other" / "x"
    other.mkdir(parents=True)
    title = format_io_window_title(other)
    assert "φ io" in title
    assert str(other.resolve()) in title


def test_set_terminal_title_skips_when_disabled(monkeypatch, capsys) -> None:
    monkeypatch.setenv("IO_TERMINAL_TITLE", "0")
    set_terminal_title("should-not-emit")
    assert capsys.readouterr().out == ""
