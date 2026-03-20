from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from io_cli.config import load_config, save_config
from io_cli.repl_slash import handle_repl_slash_command


def test_repl_slash_reasoning_sets_config(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/reasoning high",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is True
    assert "Reasoning effort set to high" in msg
    cfg = load_config(home)
    assert cfg["model"]["reasoning_effort"] == "high"


def test_repl_slash_non_slash_not_handled() -> None:
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "hello world",
            home=Path("/tmp"),
            cwd=Path("/tmp"),
            repl_args=argparse.Namespace(model=None, provider=None),
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is False
    assert msg == ""


def test_repl_slash_skill_slug_expands_skill_body(tmp_path: Path) -> None:
    """`/skill-slug` expands to a Hermes-style message with full SKILL.md."""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    skill_dir = cwd / ".io" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Demo Skill\n---\n# Demo\nDoes things.\n",
        encoding="utf-8",
    )
    save_config({"model": {}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/demo-skill",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is False
    assert "BEGIN SKILL.md" in msg
    assert "Does things." in msg
    assert "### User request" in msg


def test_repl_slash_skill_slug_passes_trailing_args(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    skill_dir = cwd / ".io" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: Demo Skill\n---\n# X\n", encoding="utf-8")
    save_config({"model": {}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/demo-skill hello there",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is False
    assert "hello there" in msg


def test_repl_slash_unknown_still_error(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/not-a-real-command-xyz",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is True
    assert "Unknown command" in msg
