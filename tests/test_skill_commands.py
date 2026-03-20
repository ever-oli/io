from __future__ import annotations

from pathlib import Path

from io_cli.agent.skill_commands import build_skill_invocation_message
from io_cli.config import save_config


def test_build_skill_invocation_message_by_slug(tmp_path: Path) -> None:
    home = tmp_path / "h"
    home.mkdir()
    cwd = tmp_path / "w"
    d = cwd / ".io" / "skills" / "acme"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: Acme Skill\n---\n# Acme\nBody line.\n", encoding="utf-8")
    save_config({"model": {}, "display": {}}, home)
    msg = build_skill_invocation_message("/acme-skill", home=home, cwd=cwd, platform="cli")
    assert msg is not None
    assert "Acme Skill" in msg
    assert "Body line." in msg


def test_build_skill_invocation_message_unknown_returns_none(tmp_path: Path) -> None:
    home = tmp_path / "h"
    home.mkdir()
    cwd = tmp_path / "w"
    cwd.mkdir()
    save_config({"model": {}, "display": {}}, home)
    assert build_skill_invocation_message("/nope-nope-skill", home=home, cwd=cwd, platform="cli") is None
