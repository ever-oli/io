"""IO lean / Aristotle bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from io_cli.lean import (
    default_project_dir,
    format_submit_result,
    parse_lean_slash_arguments,
    prove_argv_from_config,
    run_lean_draft,
    run_lean_prove,
    run_lean_submit,
    submit_argv_from_config,
)
from io_cli.lean_projects import cmd_project_add, cmd_project_use, resolve_effective_project_dir


def test_submit_argv_defaults() -> None:
    assert submit_argv_from_config({}) == ["uv", "run", "aristotle", "submit"]


def test_submit_argv_string() -> None:
    cfg = {"lean": {"submit_argv": "uv run aristotle submit"}}
    assert submit_argv_from_config(cfg) == ["uv", "run", "aristotle", "submit"]


def test_default_project_dir() -> None:
    cwd = Path("/tmp/ws")
    cfg = {"lean": {"default_project_dir": "math"}}
    assert default_project_dir(cfg, cwd) == (cwd / "math").resolve()


def test_parse_lean_slash() -> None:
    assert parse_lean_slash_arguments("doctor") == ("doctor", "", [], None)
    assert parse_lean_slash_arguments("submit Prove p") == ("submit", "Prove p", [], None)
    assert parse_lean_slash_arguments("prove scope lemma1") == ("prove", "scope lemma1", [], None)
    assert parse_lean_slash_arguments("prove @gauss show this") == ("prove", "show this", [], "gauss")
    assert parse_lean_slash_arguments("project list") == ("project", "list", [], None)
    assert parse_lean_slash_arguments("project use myproj") == ("project", "use myproj", [], None)
    assert parse_lean_slash_arguments("draft outline theorem") == ("draft", "outline theorem", [], None)
    assert parse_lean_slash_arguments("formalize Nat.add_comm") == ("formalize", "Nat.add_comm", [], None)
    assert parse_lean_slash_arguments("swarm parallel goals") == ("swarm", "parallel goals", [], None)
    with pytest.raises(ValueError):
        parse_lean_slash_arguments("submit")
    with pytest.raises(ValueError):
        parse_lean_slash_arguments("prove")
    with pytest.raises(ValueError):
        parse_lean_slash_arguments("draft")
    with pytest.raises(ValueError):
        parse_lean_slash_arguments("project")
    with pytest.raises(ValueError):
        parse_lean_slash_arguments("preset show")
    with pytest.raises(ValueError):
        parse_lean_slash_arguments("")


def test_run_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = {"lean": {"enabled": False}}
    r = run_lean_submit("x", config=cfg, cwd=tmp_path, home=tmp_path)
    assert r.exit_code == 2
    assert "enabled" in r.stderr


def test_dry_run_argv(tmp_path: Path) -> None:
    cfg = {}
    r = run_lean_submit(
        "Prove 1+1=2",
        config=cfg,
        cwd=tmp_path,
        home=tmp_path,
        dry_run=True,
    )
    assert r.exit_code == 0
    assert "Prove 1+1=2" in r.stdout
    assert "--project-dir" in r.stdout
    assert '"mode": "submit"' in r.stdout


def test_registry_named_project_dry_run(tmp_path: Path) -> None:
    home = tmp_path / "iohome"
    ws = tmp_path / "workspace"
    ws.mkdir()
    cmd_project_add(home, "math", str(ws), cwd=tmp_path, set_current=False)
    r = run_lean_submit(
        "Prove 1+1=2",
        config={},
        cwd=tmp_path,
        home=home,
        project_name="math",
        dry_run=True,
    )
    assert r.exit_code == 0
    assert str(ws.resolve()) in r.stdout


def test_project_dir_and_name_conflict(tmp_path: Path) -> None:
    home = tmp_path / "h"
    ws = tmp_path / "w"
    ws.mkdir()
    cmd_project_add(home, "math", str(ws), cwd=tmp_path)
    r = run_lean_submit(
        "x",
        config={},
        cwd=tmp_path,
        home=home,
        project_dir=ws,
        project_name="math",
        dry_run=True,
    )
    assert r.exit_code == 2
    assert "not both" in r.stderr


def test_prefer_registry_current(tmp_path: Path) -> None:
    home = tmp_path / "h"
    ws = tmp_path / "w"
    ws.mkdir()
    cmd_project_add(home, "math", str(ws), cwd=tmp_path)
    cmd_project_use(home, "math")
    cfg = {"lean": {"prefer_registry_current": True}}
    resolved, err = resolve_effective_project_dir(
        home=home,
        cwd=ws,
        config=cfg,
        project_dir=None,
        project_name=None,
    )
    assert err is None
    assert resolved == ws.resolve()


def test_prove_argv_default() -> None:
    assert prove_argv_from_config({}) == ["uv", "run", "aristotle", "prove"]


def test_prove_argv_per_backend() -> None:
    cfg = {
        "lean": {
            "backends": {
                "aristotle": {"prove_argv": ["echo", "ari"]},
                "gauss": {"prove_argv": ["echo", "gss"]},
            },
            "default_backend": "aristotle",
            "prove_argv": ["echo", "fallback"],
        }
    }
    assert prove_argv_from_config(cfg, "gauss") == ["echo", "gss"]
    assert prove_argv_from_config(cfg, "aristotle") == ["echo", "ari"]
    cfg2 = {"lean": {"backends": {"gauss": {}}, "prove_argv": ["echo", "x"]}}
    assert prove_argv_from_config(cfg2, "gauss") == ["echo", "x"]


def test_backend_without_config_errors(tmp_path: Path) -> None:
    r = run_lean_prove(
        "x",
        config={},
        cwd=tmp_path,
        home=tmp_path,
        backend="gauss",
        dry_run=True,
    )
    assert r.exit_code == 2
    assert "backends" in r.stderr.lower()


def test_prove_dry_run_respects_default_backend(tmp_path: Path) -> None:
    cfg = {
        "lean": {
            "backends": {"gauss": {"prove_argv": ["echo", "G"]}},
            "default_backend": "gauss",
        }
    }
    r = run_lean_prove("lemma", config=cfg, cwd=tmp_path, home=tmp_path, dry_run=True)
    assert r.exit_code == 0
    assert '"backend": "gauss"' in r.stdout
    assert "G" in r.stdout


def test_prove_dry_run_mode(tmp_path: Path) -> None:
    r = run_lean_prove(
        "lemma A",
        config={},
        cwd=tmp_path,
        home=tmp_path,
        dry_run=True,
    )
    assert r.exit_code == 0
    assert '"mode": "prove"' in r.stdout


def test_draft_requires_argv(tmp_path: Path) -> None:
    r = run_lean_draft("x", config={}, cwd=tmp_path, home=tmp_path, dry_run=True)
    assert r.exit_code == 2
    assert "draft_argv" in r.stderr


def test_draft_dry_run(tmp_path: Path) -> None:
    cfg = {"lean": {"draft_argv": ["echo", "gauss-draft"]}}
    r = run_lean_draft("goal", config=cfg, cwd=tmp_path, home=tmp_path, dry_run=True)
    assert r.exit_code == 0
    assert '"mode": "draft"' in r.stdout
    assert "gauss-draft" in r.stdout


def test_format_submit_result() -> None:
    from io_cli.lean import LeanSubmitResult

    text = format_submit_result(
        LeanSubmitResult(0, "ok\n", "", ["uv", "run", "aristotle", "submit", "x", "--project-dir", "."])
    )
    assert "exit_code: 0" in text
    assert "ok" in text
