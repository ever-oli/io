"""``.gauss/project.yaml`` lean root hints (OpenGauss-style)."""

from __future__ import annotations

from pathlib import Path

from io_cli.gauss_project import resolve_lean_root_with_gauss
from io_cli.lean import run_lean_draft


def test_gauss_yaml_top_level_lean_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    lean = repo / "math"
    lean.mkdir(parents=True)
    gauss = repo / ".gauss"
    gauss.mkdir()
    (gauss / "project.yaml").write_text("lean_root: math\n", encoding="utf-8")
    cfg = {"lean": {"respect_gauss_project_yaml": True}}
    assert resolve_lean_root_with_gauss(repo, cfg) == lean.resolve()


def test_gauss_respect_flag_off(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".gauss").mkdir(parents=True)
    (repo / ".gauss" / "project.yaml").write_text("lean_root: nowhere\n", encoding="utf-8")
    cfg = {"lean": {"respect_gauss_project_yaml": False}}
    assert resolve_lean_root_with_gauss(repo, cfg) == repo.resolve()


def test_gauss_paths_block(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    lean = repo / "l" / "lean"
    lean.mkdir(parents=True)
    (repo / ".gauss").mkdir()
    (repo / ".gauss" / "project.yml").write_text(
        "paths:\n  lean: l/lean\n",
        encoding="utf-8",
    )
    cfg = {"lean": {"respect_gauss_project_yaml": True}}
    assert resolve_lean_root_with_gauss(repo, cfg) == lean.resolve()


def test_run_lean_uses_gauss_overlay(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    lean = repo / "nested"
    lean.mkdir(parents=True)
    (repo / ".gauss").mkdir()
    (repo / ".gauss" / "project.yaml").write_text("lean_root: nested\n", encoding="utf-8")
    cfg = {"lean": {"draft_argv": ["echo", "x"], "respect_gauss_project_yaml": True}}
    r = run_lean_draft("hi", config=cfg, cwd=repo, home=tmp_path, dry_run=True)
    assert r.exit_code == 0
    assert str(lean.resolve()) in r.stdout
