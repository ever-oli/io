from __future__ import annotations

import pytest

from io_cli.environments.manager import SUPPORTED_BACKENDS
from io_cli.environments.modal import ModalEnvironment
from io_cli.environments.base import EnvironmentConfigurationError


def test_supported_backends_include_modal_daytona() -> None:
    assert "modal" in SUPPORTED_BACKENDS
    assert "daytona" in SUPPORTED_BACKENDS


def test_modal_spawn_background_is_unsupported() -> None:
    try:
        env = ModalEnvironment(
            image="debian_slim",
            timeout=60,
            cwd="/root",
            persistent_filesystem=False,
        )
    except EnvironmentConfigurationError as exc:
        if "modal" in str(exc).lower() or "minisweagent" in str(exc).lower():
            pytest.skip("Modal stack not installed")
        raise
    with pytest.raises(EnvironmentConfigurationError, match="background"):
        env.spawn_background(registry=object(), command="sleep 1", cwd="/root", task_id="t1")
