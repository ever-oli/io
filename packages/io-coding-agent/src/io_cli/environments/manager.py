"""Terminal backend request resolution and environment factory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import load_config
from .base import BaseEnvironment, EnvironmentConfigurationError
from .daytona import DaytonaEnvironment
from .docker import DockerEnvironment
from .local import LocalEnvironment
from .modal import ModalEnvironment
from .singularity import SingularityEnvironment
from .ssh import SSHEnvironment


SUPPORTED_BACKENDS = {"local", "docker", "ssh", "singularity", "modal", "daytona"}


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_workdir(base_cwd: Path, value: object) -> Path:
    if value is None:
        return base_cwd
    candidate = Path(str(value)).expanduser()
    return candidate if candidate.is_absolute() else (base_cwd / candidate).resolve()


@dataclass(slots=True)
class TerminalEnvironmentRequest:
    backend: str
    workdir: Path
    remote_cwd: str
    timeout: int
    docker_image: str
    docker_mount_cwd_to_workspace: bool
    docker_forward_env: list[str]
    ssh_host: str
    ssh_user: str
    ssh_port: int
    ssh_key: str
    singularity_image: str
    modal_image: str
    daytona_image: str
    container_cpu: int
    container_memory: int
    container_disk: int
    container_persistent: bool


def _default_remote_cwd(backend: str) -> str:
    if backend == "modal":
        return "/root"
    if backend == "daytona":
        return "/home/daytona"
    if backend == "singularity":
        return "/workspace"
    return "."


def _resolve_remote_cwd(backend: str, raw_workdir: object, resolved_workdir: Path) -> str:
    if backend in {"modal", "daytona"}:
        value = "" if raw_workdir is None else str(raw_workdir).strip()
        if not value or value in {".", "./"}:
            return _default_remote_cwd(backend)
        return value
    if backend == "singularity":
        value = "" if raw_workdir is None else str(raw_workdir).strip()
        if not value or value in {".", "./"}:
            return "/workspace"
        return value
    return str(resolved_workdir)


def resolve_terminal_environment(
    *,
    home: Path,
    cwd: Path,
    arguments: dict[str, object],
) -> TerminalEnvironmentRequest:
    config = load_config(home)
    terminal = config.get("terminal", {})
    if not isinstance(terminal, dict):
        terminal = {}

    backend = str(arguments.get("backend") or terminal.get("backend") or "local").strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        raise EnvironmentConfigurationError(
            "Unknown terminal backend "
            f"'{backend}'. Use local, docker, ssh, singularity, modal, or daytona."
        )

    timeout = _as_int(arguments.get("timeout"), _as_int(terminal.get("timeout"), 180))
    workdir_value = arguments.get("workdir")
    if workdir_value is None:
        workdir_value = terminal.get("cwd", ".")
    resolved_workdir = _resolve_workdir(cwd, workdir_value)

    forward_env = terminal.get("docker_forward_env", [])
    if not isinstance(forward_env, list):
        forward_env = []

    return TerminalEnvironmentRequest(
        backend=backend,
        workdir=resolved_workdir,
        remote_cwd=_resolve_remote_cwd(backend, workdir_value, resolved_workdir),
        timeout=max(1, timeout),
        docker_image=str(
            arguments.get("docker_image") or terminal.get("docker_image") or ""
        ).strip(),
        docker_mount_cwd_to_workspace=_as_bool(
            arguments.get("docker_mount_cwd_to_workspace"),
            _as_bool(terminal.get("docker_mount_cwd_to_workspace"), False),
        ),
        docker_forward_env=[str(item).strip() for item in forward_env if str(item).strip()],
        ssh_host=str(arguments.get("ssh_host") or terminal.get("ssh_host") or "").strip(),
        ssh_user=str(arguments.get("ssh_user") or terminal.get("ssh_user") or "").strip(),
        ssh_port=max(1, _as_int(arguments.get("ssh_port"), _as_int(terminal.get("ssh_port"), 22))),
        ssh_key=str(arguments.get("ssh_key") or terminal.get("ssh_key") or "").strip(),
        singularity_image=str(
            arguments.get("singularity_image") or terminal.get("singularity_image") or ""
        ).strip(),
        modal_image=str(arguments.get("modal_image") or terminal.get("modal_image") or "").strip(),
        daytona_image=str(
            arguments.get("daytona_image") or terminal.get("daytona_image") or ""
        ).strip(),
        container_cpu=max(
            0,
            _as_int(arguments.get("container_cpu"), _as_int(terminal.get("container_cpu"), 1)),
        ),
        container_memory=max(
            0,
            _as_int(
                arguments.get("container_memory"),
                _as_int(terminal.get("container_memory"), 5120),
            ),
        ),
        container_disk=max(
            0,
            _as_int(arguments.get("container_disk"), _as_int(terminal.get("container_disk"), 51200)),
        ),
        container_persistent=_as_bool(
            arguments.get("container_persistent"),
            _as_bool(terminal.get("container_persistent"), True),
        ),
    )


def create_environment(
    request: TerminalEnvironmentRequest,
    *,
    env: dict[str, str] | None = None,
) -> BaseEnvironment:
    if request.backend == "local":
        return LocalEnvironment(timeout=request.timeout, env=env, cwd=request.workdir)
    if request.backend == "docker":
        return DockerEnvironment(
            image=request.docker_image,
            timeout=request.timeout,
            env=env,
            cwd=request.remote_cwd,
            mount_cwd=request.docker_mount_cwd_to_workspace or request.workdir.exists(),
            forward_env=request.docker_forward_env,
        )
    if request.backend == "ssh":
        return SSHEnvironment(
            host=request.ssh_host,
            user=request.ssh_user,
            port=request.ssh_port,
            key_path=request.ssh_key,
            timeout=request.timeout,
            env=env,
            cwd=request.remote_cwd,
        )
    if request.backend == "singularity":
        return SingularityEnvironment(
            image=request.singularity_image,
            timeout=request.timeout,
            env=env,
            cwd=request.remote_cwd,
            cpu=request.container_cpu,
            memory=request.container_memory,
            disk=request.container_disk,
            persistent_filesystem=request.container_persistent,
        )
    if request.backend == "modal":
        return ModalEnvironment(
            image=request.modal_image,
            timeout=request.timeout,
            env=env,
            cwd=request.remote_cwd,
            persistent_filesystem=request.container_persistent,
            modal_sandbox_kwargs={
                "cpu": request.container_cpu,
                "memory": request.container_memory,
            },
        )
    if request.backend == "daytona":
        return DaytonaEnvironment(
            image=request.daytona_image,
            timeout=request.timeout,
            env=env,
            cwd=request.remote_cwd,
            cpu=request.container_cpu,
            memory=request.container_memory,
            disk=request.container_disk,
            persistent_filesystem=request.container_persistent,
        )
    raise EnvironmentConfigurationError(
        "Unknown terminal backend "
        f"'{request.backend}'. Use local, docker, ssh, singularity, modal, or daytona."
    )
