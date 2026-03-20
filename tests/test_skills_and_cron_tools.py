from __future__ import annotations

import asyncio
import json
from pathlib import Path

from io_agent import ToolContext
from io_cli.tools.registry import get_tool_registry


def _context(tmp_path: Path, *, cwd: Path | None = None) -> ToolContext:
    home = tmp_path / "home"
    return ToolContext(cwd=cwd or tmp_path, home=home, env={})


def _run_tool(tmp_path: Path, tool_name: str, arguments: dict[str, object], *, cwd: Path | None = None) -> dict[str, object]:
    registry = get_tool_registry()
    context = _context(tmp_path, cwd=cwd)
    result = asyncio.run(registry.get(tool_name).execute(context, arguments))
    return json.loads(result.content)


def test_skills_list_and_view_tools(tmp_path: Path) -> None:
    home = tmp_path / "home"
    skill_name = "tmp-deploy-checklist"
    skill_dir = home / "skills" / "devops" / skill_name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        f"name: {skill_name}\n"
        "description: Release checklist for shipping safely.\n"
        "---\n\n"
        "# Deploy Checklist\n\n"
        "Run tests before deploy.\n",
        encoding="utf-8",
    )
    references = skill_dir / "references"
    references.mkdir()
    (references / "runbook.md").write_text("Step 1: verify staging.\n", encoding="utf-8")

    skills_list_result = _run_tool(tmp_path, "skills_list", {})
    assert skills_list_result["success"] is True
    assert any(skill["name"] == skill_name for skill in skills_list_result["skills"])
    assert "devops" in skills_list_result["categories"]

    skill_view_result = _run_tool(tmp_path, "skill_view", {"name": skill_name})
    assert skill_view_result["success"] is True
    assert skill_view_result["name"] == skill_name
    assert "references/runbook.md" in skill_view_result["linked_files"]["references"]

    file_view_result = _run_tool(
        tmp_path,
        "skill_view",
        {"name": skill_name, "file_path": "references/runbook.md"},
    )
    assert file_view_result["success"] is True
    assert file_view_result["file"] == "references/runbook.md"
    assert "verify staging" in file_view_result["content"]


def test_skill_manage_tool_mutates_skill_files(tmp_path: Path) -> None:
    skill_name = "tmp-manage-skill"
    content = (
        "---\n"
        f"name: {skill_name}\n"
        "description: Temporary skill for tool tests.\n"
        "---\n\n"
        "# Temporary Skill\n\n"
        "Initial procedure.\n"
    )

    create_result = _run_tool(
        tmp_path,
        "skill_manage",
        {"action": "create", "name": skill_name, "content": content},
    )
    assert create_result["success"] is True

    write_result = _run_tool(
        tmp_path,
        "skill_manage",
        {
            "action": "write_file",
            "name": skill_name,
            "file_path": "references/checklist.md",
            "file_content": "Check services before rollout.\n",
        },
    )
    assert write_result["success"] is True

    patch_result = _run_tool(
        tmp_path,
        "skill_manage",
        {
            "action": "patch",
            "name": skill_name,
            "old_string": "Initial procedure.",
            "new_string": "Updated procedure.",
        },
    )
    assert patch_result["success"] is True

    skill_md = tmp_path / "home" / "skills" / skill_name / "SKILL.md"
    assert "Updated procedure." in skill_md.read_text(encoding="utf-8")

    remove_file_result = _run_tool(
        tmp_path,
        "skill_manage",
        {
            "action": "remove_file",
            "name": skill_name,
            "file_path": "references/checklist.md",
        },
    )
    assert remove_file_result["success"] is True
    assert not (tmp_path / "home" / "skills" / skill_name / "references" / "checklist.md").exists()

    delete_result = _run_tool(
        tmp_path,
        "skill_manage",
        {"action": "delete", "name": skill_name},
    )
    assert delete_result["success"] is True
    assert not (tmp_path / "home" / "skills" / skill_name).exists()


def test_cronjob_tool_create_run_pause_resume_and_remove(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "alpha.txt").write_text("hello\n", encoding="utf-8")

    create_result = _run_tool(
        tmp_path,
        "cronjob",
        {
            "action": "create",
            "prompt": 'TOOL[ls] {"path":"."}',
            "schedule": "manual",
            "name": "List repo",
            "model": "mock/io-test",
            "provider": "mock",
        },
        cwd=cwd,
    )
    assert create_result["success"] is True
    job_id = create_result["job_id"]

    list_result = _run_tool(
        tmp_path,
        "cronjob",
        {"action": "list", "include_disabled": True},
        cwd=cwd,
    )
    assert list_result["success"] is True
    assert any(job["job_id"] == job_id for job in list_result["jobs"])

    run_result = _run_tool(
        tmp_path,
        "cronjob",
        {"action": "run", "job_id": job_id},
        cwd=cwd,
    )
    assert run_result["success"] is True
    assert "alpha.txt" in str(run_result["result"])

    pause_result = _run_tool(
        tmp_path,
        "cronjob",
        {"action": "pause", "job_id": job_id, "reason": "maintenance"},
        cwd=cwd,
    )
    assert pause_result["success"] is True
    assert pause_result["job"]["state"] == "paused"

    resume_result = _run_tool(
        tmp_path,
        "cronjob",
        {"action": "resume", "job_id": job_id},
        cwd=cwd,
    )
    assert resume_result["success"] is True
    assert resume_result["job"]["state"] == "scheduled"

    remove_result = _run_tool(
        tmp_path,
        "cronjob",
        {"action": "remove", "job_id": job_id},
        cwd=cwd,
    )
    assert remove_result["success"] is True
