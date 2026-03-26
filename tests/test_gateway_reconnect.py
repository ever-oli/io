from __future__ import annotations

from pathlib import Path

from io_cli.gateway import GatewayManager
from io_cli.gateway_models import Platform
from io_cli.gateway_platforms.base import BasePlatformAdapter, MessageEvent
from io_cli.gateway_runner import ADAPTER_TYPES, GatewayRunner


class _FlakyTelegramAdapter(BasePlatformAdapter):
    starts = 0

    def __init__(self, config) -> None:
        super().__init__(config, Platform.TELEGRAM)

    async def _start(self) -> None:
        type(self).starts += 1
        if type(self).starts == 1:
            raise RuntimeError("startup failed once")
        self._mark_connected()

    async def _stop(self) -> None:
        self._mark_disconnected()

    async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
        _ = timeout
        return []

    async def send_message(self, chat_id: str, content: str, *, thread_id: str | None = None, metadata=None):
        _ = (chat_id, content, thread_id, metadata)
        return {"success": True}


class _PollFailsAdapter(_FlakyTelegramAdapter):
    async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
        _ = timeout
        raise RuntimeError("poll failed")


def test_gateway_runner_reconnects_after_startup_failure(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    manager = GatewayManager(home=home)
    manager.configure(platforms=["telegram"])

    _FlakyTelegramAdapter.starts = 0
    monkeypatch.setitem(ADAPTER_TYPES, Platform.TELEGRAM, _FlakyTelegramAdapter)

    runner = GatewayRunner(
        home=home,
        poll_interval=0.01,
        reconnect_base_delay=0.0,
        reconnect_max_delay=0.0,
    )
    result = runner.run_sync(once=True)

    assert result["configured_platforms"] == ["telegram"]
    assert _FlakyTelegramAdapter.starts >= 2


def test_gateway_runner_schedules_reconnect_after_poll_failure(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    manager = GatewayManager(home=home)
    manager.configure(platforms=["telegram"])

    _PollFailsAdapter.starts = 0
    monkeypatch.setitem(ADAPTER_TYPES, Platform.TELEGRAM, _PollFailsAdapter)

    runner = GatewayRunner(
        home=home,
        poll_interval=0.01,
        reconnect_base_delay=0.0,
        reconnect_max_delay=0.0,
        max_loops=2,
    )
    result = runner.run_sync(once=False)
    assert result["configured_platforms"] == ["telegram"]
    assert runner._reconnect_attempts.get(Platform.TELEGRAM, 0) >= 1

