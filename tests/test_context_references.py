from __future__ import annotations

from pathlib import Path

from io_cli.commands import SlashCommandCompleter
from io_cli.context_references import expand_at_references


def test_expand_at_references_includes_file_content(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello ref", encoding="utf-8")
    out = expand_at_references("please read @README.md", cwd=tmp_path)
    assert "BEGIN @README.md" in out
    assert "hello ref" in out
    assert "END @README.md" in out


def test_expand_at_references_blocks_paths_outside_cwd(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    out = expand_at_references(f"read @{outside}", cwd=tmp_path)
    assert "BEGIN @" not in out
    assert out == f"read @{outside}"


def test_expand_at_references_supports_quoted_paths_with_spaces(tmp_path: Path) -> None:
    p = tmp_path / "my notes.md"
    p.write_text("space path", encoding="utf-8")
    out = expand_at_references('read @"my notes.md"', cwd=tmp_path)
    assert "BEGIN @my notes.md" in out
    assert "space path" in out


def test_expand_at_references_blocks_git_dir_and_reports_ignored(tmp_path: Path) -> None:
    git_file = tmp_path / ".git" / "config"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("secret", encoding="utf-8")
    out = expand_at_references("read @.git/config", cwd=tmp_path)
    assert "BEGIN @" not in out
    assert out == "read @.git/config"


def test_expand_at_references_reports_ignored_when_partial_success(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("ok", encoding="utf-8")
    out = expand_at_references("read @a.txt @missing.txt", cwd=tmp_path)
    assert "BEGIN @a.txt" in out
    assert "Ignored @refs:" in out


def test_at_path_completion_for_plain_filename(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "notes.md").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    completions = list(SlashCommandCompleter._path_completions("@not", limit=20))
    texts = [c.text for c in completions]
    assert "@notes.md" in texts

