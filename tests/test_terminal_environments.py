from __future__ import annotations

import asyncio
import json
from pathlib import Path

from io_agent import ToolContext
from io_cli.config import ensure_io_home, load_config, save_config
from io_cli.doctor import doctor_report
from io_cli.environments import TerminalEnvironmentRequest, create_environment, resolve_terminal_environment
from io_cli.tools.registry import get_tool_registry


def test_resolve_terminal_environment_prefers_overrides(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    config = load_config(home)
    config["terminal"]["backend"] = "local"
    config["terminal"]["ssh_host"] = "config-host"
    config["terminal"]["ssh_user"] = "config-user"
    save_config(config, home)

    request = resolve_terminal_environment(
        home=home,
        cwd=tmp_path,
        arguments={
            "backend": "ssh",
            "workdir": "repo",
            "ssh_host": "override-host",
            "ssh_user": "override-user",
            "ssh_port": 2200,
        },
    )

    assert request.backend == "ssh"
    assert request.workdir == (tmp_path / "repo").resolve()
    assert request.ssh_host == "override-host"
    assert request.ssh_user == "override-user"
    assert request.ssh_port == 2200


async def _run_terminal_tool(
    tmp_path: Path,
    arguments: dict[str, object],
    *,
    monkeypatch,
) -> dict[str, object]:
    context = ToolContext(cwd=tmp_path, home=tmp_path / "home", env={})
    result = await get_tool_registry().get("terminal").execute(context, arguments)
    return json.loads(result.content)


def test_terminal_tool_uses_environment_factory_for_overrides(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeEnvironment:
        backend = "docker"

        def execute(self, command: str, *, cwd: Path, timeout: int | None = None, stdin_data: str | None = None):
            captured["command"] = command
            captured["cwd"] = cwd
            captured["timeout"] = timeout
            return {"output": "ok", "returncode": 0, "timed_out": False}

        def spawn_background(self, *, registry, command: str, cwd: Path, task_id: str):
            del registry, task_id
            captured["background_command"] = command
            captured["background_cwd"] = cwd

            class Session:
                id = "proc_fake"

            return Session()

    monkeypatch.setattr(
        "io_cli.tools.compat.create_environment",
        lambda request, *, env=None: FakeEnvironment(),
    )

    payload = asyncio.run(
        _run_terminal_tool(
            tmp_path,
            {
                "command": "echo hi",
                "backend": "docker",
                "docker_image": "python:3.11",
                "workdir": ".",
                "timeout": 33,
            },
            monkeypatch=monkeypatch,
        )
    )

    assert payload["backend"] == "docker"
    assert payload["exit_code"] == 0
    assert captured["command"] == "echo hi"
    assert captured["timeout"] == 33


def test_terminal_tool_local_backend_reports_backend(tmp_path: Path) -> None:
    payload = asyncio.run(
        _run_terminal_tool(
            tmp_path,
            {
                "command": "pwd",
                "backend": "local",
                "workdir": ".",
            },
            monkeypatch=None,
        )
    )

    assert payload["backend"] == "local"
    assert payload["exit_code"] == 0


def test_resolve_terminal_environment_modal_defaults(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    config = load_config(home)
    config["terminal"]["backend"] = "modal"
    config["terminal"]["modal_image"] = "debian_slim"
    config["terminal"]["container_cpu"] = 2
    save_config(config, home)

    request = resolve_terminal_environment(
        home=home,
        cwd=tmp_path,
        arguments={"backend": "modal"},
    )

    assert request.backend == "modal"
    assert request.remote_cwd == "/root"
    assert request.modal_image == "debian_slim"
    assert request.container_cpu == 2


def test_create_environment_selects_modal_backend(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeModalEnvironment:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("io_cli.environments.manager.ModalEnvironment", FakeModalEnvironment)

    request = TerminalEnvironmentRequest(
        backend="modal",
        workdir=tmp_path,
        remote_cwd="/root",
        timeout=45,
        docker_image="",
        docker_mount_cwd_to_workspace=False,
        docker_forward_env=[],
        ssh_host="",
        ssh_user="",
        ssh_port=22,
        ssh_key="",
        singularity_image="",
        modal_image="debian_slim",
        daytona_image="",
        container_cpu=2,
        container_memory=4096,
        container_disk=10240,
        container_persistent=True,
    )

    create_environment(request, env={"OPENAI_API_KEY": "test"})

    assert captured["image"] == "debian_slim"
    assert captured["cwd"] == "/root"
    assert captured["timeout"] == 45
    assert captured["persistent_filesystem"] is True


def test_terminal_tool_daytona_backend_uses_remote_cwd(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeEnvironment:
        backend = "daytona"

        def execute(self, command: str, *, cwd: Path | str, timeout: int | None = None, stdin_data: str | None = None):
            captured["command"] = command
            captured["cwd"] = cwd
            captured["timeout"] = timeout
            captured["stdin_data"] = stdin_data
            return {"output": "ok", "returncode": 0, "timed_out": False}

        def cleanup(self) -> None:
            captured["cleaned"] = True

        def spawn_background(self, *, registry, command: str, cwd: Path | str, task_id: str):
            del registry, command, cwd, task_id
            raise AssertionError("background path should not be used")

    monkeypatch.setattr(
        "io_cli.tools.compat.create_environment",
        lambda request, *, env=None: FakeEnvironment(),
    )

    payload = asyncio.run(
        _run_terminal_tool(
            tmp_path,
            {
                "command": "pwd",
                "backend": "daytona",
                "daytona_image": "python:3.11",
            },
            monkeypatch=monkeypatch,
        )
    )

    assert payload["backend"] == "daytona"
    assert payload["cwd"] == "/home/daytona"
    assert payload["exit_code"] == 0
    assert captured["cwd"] == "/home/daytona"
    assert captured["cleaned"] is True


def test_doctor_warns_for_missing_singularity_binary(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    config = load_config(home)
    config["terminal"]["backend"] = "singularity"
    save_config(config, home)

    report = doctor_report(home=home, cwd=tmp_path)

    assert any("Singularity terminal backend selected" in warning for warning in report["warnings"])
