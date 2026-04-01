from __future__ import annotations

from io import StringIO
from pathlib import Path

from rich.console import Console

from io_cli import cli
from io_cli import upgrade


def _console_buffer() -> tuple[Console, StringIO]:
    buffer = StringIO()
    return Console(file=buffer, force_terminal=False, color_system=None), buffer


def test_detect_git_install_root_prefers_home_checkout(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = home / "io"
    (repo / ".git").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    assert upgrade.detect_git_install_root(home) == repo.resolve()


def test_upgrade_io_git_checkout_runs_installer(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo = home / "io"
    (repo / ".git").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    calls: list[list[str]] = []

    class _Result:
        def __init__(self, *, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode

    def fake_run(cmd, *args, **kwargs):
        normalized = [str(part) for part in cmd]
        calls.append(normalized)
        if normalized[:4] == ["git", "-C", str(repo.resolve()), "rev-parse"]:
            return _Result(stdout="feature/test\n")
        return _Result()

    monkeypatch.setattr(upgrade.subprocess, "run", fake_run)

    console, buffer = _console_buffer()
    success = upgrade.upgrade_io(home=home, console=console)

    assert success is True
    assert calls[0][:4] == ["git", "-C", str(repo.resolve()), "rev-parse"]
    assert calls[1][0] == "bash"
    assert calls[1][1] == str((repo / "scripts" / "install.sh").resolve())
    assert "--skip-setup" in calls[1]
    assert "--dir" in calls[1]
    assert str(repo.resolve()) in calls[1]
    assert "--branch" in calls[1]
    assert "feature/test" in calls[1]
    assert "Install mode: git checkout" in buffer.getvalue()


def test_upgrade_io_git_checkout_dry_run_prints_command(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    repo = home / "io"
    (repo / ".git").mkdir(parents=True)
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts" / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")

    class _Result:
        def __init__(self, *, stdout: str = "", returncode: int = 0) -> None:
            self.stdout = stdout
            self.returncode = returncode

    def fake_run(cmd, *args, **kwargs):
        normalized = [str(part) for part in cmd]
        if normalized[:4] == ["git", "-C", str(repo.resolve()), "rev-parse"]:
            return _Result(stdout="main\n")
        raise AssertionError("installer should not run during dry-run")

    monkeypatch.setattr(upgrade.subprocess, "run", fake_run)

    console, buffer = _console_buffer()
    success = upgrade.upgrade_io(home=home, dry_run=True, console=console)

    assert success is True
    assert "Would run: bash" in buffer.getvalue()


def test_cli_update_dispatches_cmd_upgrade(tmp_path: Path, monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_cmd_upgrade(argv, *, home=None, console=None):
        seen["argv"] = list(argv)
        seen["home"] = home
        seen["console"] = console
        return 0

    monkeypatch.setattr(cli, "cmd_upgrade", fake_cmd_upgrade)

    code = cli.main(["--home", str(tmp_path / "home"), "update", "--force", "--dry-run"])

    assert code == 0
    assert seen["argv"] == ["--force", "--dry-run"]
    assert seen["home"] == (tmp_path / "home")
