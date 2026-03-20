from __future__ import annotations

from pathlib import Path

from io_cli.cli import main
from io_cli.pairing import PairingStore
from io_cli.gateway import GatewayManager
from io_cli.gateway_models import Platform, PlatformConfig
from io_cli.gateway_platforms.base import BasePlatformAdapter, MessageEvent, MessageType
from io_cli.gateway_runner import GatewayRunner
from io_cli.gateway_session import SessionSource


def test_pairing_store_generates_and_approves_code(tmp_path: Path) -> None:
    store = PairingStore(home=tmp_path / "home")

    code = store.generate_code("telegram", "111", "ever")

    assert code is not None
    pending = store.list_pending("telegram")
    assert len(pending) == 1
    approved = store.approve_code("telegram", code)
    assert approved == {"user_id": "111", "user_name": "ever"}
    assert store.is_approved("telegram", "111") is True


def test_cli_pairing_lists_and_approves_codes(tmp_path: Path, monkeypatch, capsys) -> None:
    home = tmp_path / "home"
    store = PairingStore(home=home)
    code = store.generate_code("telegram", "111", "ever")
    assert code is not None

    monkeypatch.setenv("IO_HOME", str(home))

    exit_code = main(["pairing", "list"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Pending Pairing Requests" in captured.out
    assert code in captured.out

    exit_code = main(["pairing", "approve", "telegram", code])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Approved! User ever (111) on telegram can now use the bot~" in captured.out


def test_gateway_runner_offers_pairing_code_to_unauthorized_dm(tmp_path: Path, monkeypatch) -> None:
    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="test"))
            self.sent: list[str] = []

        async def _start(self) -> None:
            return None

        async def _stop(self) -> None:
            return None

        async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
            del timeout
            return [
                MessageEvent(
                    source=SessionSource(
                        platform=Platform.TELEGRAM,
                        chat_id="456",
                        chat_name="Ops",
                        chat_type="dm",
                        user_id="111",
                        user_name="ever",
                    ),
                    text="hello",
                    message_type=MessageType.TEXT,
                    message_id="m1",
                )
            ]

        async def send_message(
            self,
            chat_id: str,
            content: str,
            *,
            thread_id: str | None = None,
            metadata: dict | None = None,
        ) -> dict:
            del chat_id, thread_id, metadata
            self.sent.append(content)
            return {"ok": True}

    fake_adapter = FakeTelegramAdapter()
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")

    monkeypatch.setattr(
        GatewayRunner,
        "_build_adapter_map",
        lambda self, config: {Platform.TELEGRAM: fake_adapter},
    )

    async def should_not_run(prompt: str, **kwargs):
        raise AssertionError(f"Unauthorized message should not reach run_prompt: {prompt!r} {kwargs!r}")

    monkeypatch.setattr("io_cli.gateway_runner.run_prompt", should_not_run)

    result = GatewayRunner(home=manager.home, poll_interval=0.1).run_sync(once=True)

    assert result["messages_processed"] == 1
    assert fake_adapter.sent
    assert "Here's your pairing code:" in fake_adapter.sent[0]
    pending = PairingStore(home=manager.home).list_pending("telegram")
    assert len(pending) == 1
    assert pending[0]["user_id"] == "111"
