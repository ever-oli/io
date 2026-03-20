from __future__ import annotations

from pathlib import Path

from io_mom import SlackBotService, Workspace
from io_pods import PodLifecycle, PodSpec
from io_web_ui import create_app


def test_web_ui_app_builds() -> None:
    app = create_app()
    assert any(route.path == "/healthz" for route in app.routes)


def test_mom_service_constructs(tmp_path: Path) -> None:
    service = SlackBotService(workspace=Workspace(channel_id="demo", cwd=tmp_path))
    assert service.workspace.channel_id == "demo"


def test_pods_lifecycle_constructs() -> None:
    lifecycle = PodLifecycle()
    lifecycle.create(PodSpec(name="demo"))
    assert lifecycle.list()[0].name == "demo"
