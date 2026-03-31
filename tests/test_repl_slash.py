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


def test_repl_slash_gateway_start(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {}, "display": {}}, home)
    monkeypatch.setattr("io_cli.config.ensure_io_home", lambda _p=None: home)
    monkeypatch.setattr(
        "io_cli.gateway_spawn.spawn_gateway_run_detached",
        lambda _h: (999, str(home / "gateway" / "run.log"), "Started test pid."),
    )
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/gateway start",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is True
    assert "Started test pid" in msg


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


def test_repl_slash_model_interactive_picker(tmp_path: Path, monkeypatch) -> None:
    """Bare `/model` with repl_interactive runs the TUI picker (mocked)."""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {"provider": "mock", "default": "mock/io-test"}, "display": {}}, home)
    monkeypatch.setattr(
        "io_cli.model_picker.run_model_picker_dialog",
        lambda **kwargs: ("mock/io-test", ""),
    )
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/model",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
            repl_interactive=True,
        )
    )
    assert handled is True
    assert "mock/io-test" in msg


def test_repl_slash_provider_interactive_picker(tmp_path: Path, monkeypatch) -> None:
    """Bare `/provider` with repl_interactive runs the picker (mocked)."""
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {"provider": "mock", "default": "mock/io-test"}, "display": {}}, home)
    monkeypatch.setattr(
        "io_cli.provider_picker.run_provider_picker_dialog",
        lambda **kwargs: ("openrouter", ""),
    )
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/provider",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
            repl_interactive=True,
        )
    )
    assert handled is True
    assert "openrouter" in msg
    cfg = load_config(home)
    assert cfg["model"]["provider"] == "openrouter"


def test_repl_slash_provider_no_args_non_interactive_shows_status(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {"provider": "mock"}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/provider",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
            repl_interactive=False,
        )
    )
    assert handled is True
    assert "Active provider:" in msg


def test_repl_slash_model_no_args_non_interactive_shows_status(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {"provider": "mock", "default": "mock/io-test"}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/model",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
            repl_interactive=False,
        )
    )
    assert handled is True
    assert "Current model:" in msg


def test_repl_slash_skills_browse_official(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"model": {}, "display": {}}, home)
    ns = argparse.Namespace(model=None, provider=None, cwd=cwd)
    handled, msg = asyncio.run(
        handle_repl_slash_command(
            "/skills browse --source official",
            home=home,
            cwd=cwd,
            repl_args=ns,
            load_extensions=False,
            on_event=None,
        )
    )
    assert handled is True
    assert "Available skills:" in msg
    assert "official/migration/openclaw-migration" in msg


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
