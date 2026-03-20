from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from io_pods import PodLifecycle, PodSpec
from io_web_ui import create_app


def test_web_ui_app_builds() -> None:
    app = create_app()
    assert any(route.path == "/healthz" for route in app.routes)


def test_web_ui_chat_endpoint(tmp_path: Path) -> None:
    client = TestClient(create_app())
    response = client.post(
        "/api/chat",
        json={
            "prompt": 'TOOL[ls] {"path": "."}',
            "cwd": str(tmp_path),
            "model": "mock/io-test",
            "provider": "mock",
            "load_extensions": False,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mock"
    assert isinstance(payload["text"], str)


def test_pods_lifecycle_constructs(tmp_path: Path) -> None:
    lifecycle = PodLifecycle(home=tmp_path / "home")
    lifecycle.create(PodSpec(name="demo"))
    assert lifecycle.list()[0].name == "demo"
    reloaded = PodLifecycle(home=tmp_path / "home")
    assert reloaded.list()[0].name == "demo"
