from __future__ import annotations

from pathlib import Path

from io_cli.skills import discover_skills, save_skill_toggle


def test_discover_skills_reads_project_skill(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    skill_dir = cwd / ".io" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo Skill\nProject-local helper.\n", encoding="utf-8")

    skills = discover_skills(home=tmp_path / "home", cwd=cwd, platform="cli")
    assert any(skill.name == "Demo Skill" for skill in skills)


def test_skill_toggle_disables_skill_for_platform(tmp_path: Path) -> None:
    home = tmp_path / "home"
    save_skill_toggle("Demo Skill", enabled=False, home=home, platform="cli")
    skill_dir = tmp_path / "repo" / ".io" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Demo Skill\nProject-local helper.\n", encoding="utf-8")

    skills = discover_skills(home=home, cwd=tmp_path / "repo", platform="cli")
    demo = next(skill for skill in skills if skill.name == "Demo Skill")
    assert demo.enabled is False
