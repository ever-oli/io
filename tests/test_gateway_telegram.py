from __future__ import annotations

import asyncio
from pathlib import Path

from io_ai.types import Usage

from io_cli.cron import CronManager
from io_cli.config import load_config
from io_cli.gateway import GatewayManager
from io_cli.gateway_models import Platform, PlatformConfig
from io_cli.gateway_platforms.base import BasePlatformAdapter, MessageEvent, MessageType
from io_cli.gateway_platforms.telegram import TelegramAdapter
from io_cli.gateway_runner import GatewayRunner
from io_cli.gateway_session import SessionSource
from io_cli.main import PromptResult
from io_cli.session import SessionManager


def test_gateway_setup_persists_telegram_token(tmp_path: Path) -> None:
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:secret")

    config = manager.load_config()
    status = manager.status()

    assert config.platforms[Platform.TELEGRAM].token == "123:secret"
    assert status["gateway_config"]["platforms"]["telegram"]["token"] == "***"


def test_telegram_adapter_poll_once_parses_update(monkeypatch) -> None:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="123:secret"))

    async def fake_request(method: str, *, payload=None):
        assert method == "getUpdates"
        assert payload is not None
        return {
            "ok": True,
            "result": [
                {
                    "update_id": 7,
                    "message": {
                        "message_id": 99,
                        "text": "hello from telegram",
                        "chat": {"id": 456, "type": "private", "username": "ever"},
                        "from": {"id": 111, "username": "ever", "is_bot": False},
                    },
                }
            ],
        }

    monkeypatch.setattr(adapter, "_request_json", fake_request)

    events = asyncio.run(adapter.poll_once(timeout=0))

    assert len(events) == 1
    assert events[0].text == "hello from telegram"
    assert events[0].source.platform == Platform.TELEGRAM
    assert events[0].source.chat_id == "456"
    assert adapter.offset == 8
    assert events[0].attachments == []


def test_telegram_adapter_poll_once_noop_when_updater_running(monkeypatch) -> None:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="123:secret"))

    class _Updater:
        running = True

    class _App:
        updater = _Updater()

    adapter._app = _App()  # type: ignore[assignment]

    async def fake_request(method: str, *, payload=None):  # pragma: no cover - should not run
        raise AssertionError("poll_once should not call Bot API in updater push mode")

    monkeypatch.setattr(adapter, "_request_json", fake_request)
    events = asyncio.run(adapter.poll_once(timeout=0))
    assert events == []


def test_telegram_adapter_start_registers_bot_commands(monkeypatch) -> None:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="123:secret"))
    calls: list[tuple[str, dict | None]] = []

    async def fake_request(method: str, *, payload=None):
        calls.append((method, payload))
        return {"ok": True, "result": {"id": 1}}

    monkeypatch.setattr(adapter, "_request_json", fake_request)

    asyncio.run(adapter.start())

    assert calls[0][0] == "getMe"
    assert calls[1][0] == "setMyCommands"
    assert isinstance(calls[1][1], dict)
    assert calls[1][1]["commands"]


def test_telegram_adapter_webhook_connect_registers_webhook(monkeypatch) -> None:
    adapter = TelegramAdapter(
        PlatformConfig(
            enabled=True,
            token="123:secret",
            extra={
                "webhook_url": "https://example.com/tg/webhook",
                "webhook_port": "9443",
                "webhook_secret": "shared-secret",
            },
        )
    )
    calls: list[tuple[str, dict | None]] = []

    async def fake_request(method: str, *, payload=None):
        calls.append((method, payload))
        return {"ok": True, "result": {"id": 1}}

    async def fake_start_webhook_server() -> None:
        return None

    monkeypatch.setattr("io_cli.gateway_platforms.telegram.TELEGRAM_AVAILABLE", False)
    monkeypatch.setattr(adapter, "_request_json", fake_request)
    monkeypatch.setattr(adapter, "_start_webhook_server", fake_start_webhook_server)

    connected = asyncio.run(adapter.connect())

    assert connected is True
    assert calls[0][0] == "setWebhook"
    assert calls[0][1]["url"] == "https://example.com/tg/webhook"
    assert calls[0][1]["secret_token"] == "shared-secret"


def test_telegram_adapter_webhook_poll_once_reads_queued_updates() -> None:
    adapter = TelegramAdapter(
        PlatformConfig(
            enabled=True,
            token="123:secret",
            extra={"webhook_url": "https://example.com/tg/webhook"},
        )
    )

    asyncio.run(
        adapter._ingest_webhook_update(
            {
                "update_id": 11,
                "message": {
                    "message_id": 77,
                    "text": "hello via webhook",
                    "chat": {"id": 456, "type": "private", "username": "ever"},
                    "from": {"id": 111, "username": "ever", "is_bot": False},
                },
            }
        )
    )

    events = asyncio.run(adapter.poll_once(timeout=0))

    assert len(events) == 1
    assert events[0].text == "hello via webhook"
    assert events[0].source.chat_id == "456"


def test_telegram_adapter_resets_offset_when_token_changes() -> None:
    cfg = PlatformConfig(
        enabled=True,
        token="new-token",
        extra={
            "offset": 707834240,
            "token_fingerprint": "oldfingerprint1234",
        },
    )
    adapter = TelegramAdapter(cfg)
    assert adapter.offset == 0
    assert cfg.extra.get("offset") == 0
    assert cfg.extra.get("token_fingerprint")


def test_telegram_adapter_resolves_document_attachment_url(monkeypatch) -> None:
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="123:secret"))

    async def fake_request(method: str, *, payload=None):
        if method == "getUpdates":
            return {
                "ok": True,
                "result": [
                    {
                        "update_id": 9,
                        "message": {
                            "message_id": 101,
                            "caption": "review this",
                            "chat": {"id": 456, "type": "private", "username": "ever"},
                            "from": {"id": 111, "username": "ever", "is_bot": False},
                            "document": {"file_id": "doc-1", "file_name": "notes.txt"},
                        },
                    }
                ],
            }
        assert method == "getFile"
        assert payload == {"file_id": "doc-1"}
        return {"ok": True, "result": {"file_path": "documents/file_1.txt"}}

    monkeypatch.setattr(adapter, "_request_json", fake_request)

    events = asyncio.run(adapter.poll_once(timeout=0))

    assert len(events) == 1
    assert events[0].message_type == MessageType.DOCUMENT
    assert events[0].attachments == [
        "document (notes.txt): https://api.telegram.org/file/bot123:secret/documents/file_1.txt"
    ]


def test_gateway_runner_processes_telegram_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("IO_TELEGRAM_ALLOW_ALL_USERS", "1")

    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="test"))
            self.sent: list[dict[str, str | None]] = []

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
                        chat_name="ever",
                        chat_type="dm",
                        user_id="111",
                        user_name="ever",
                    ),
                    text="hello gateway",
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
            self.sent.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "thread_id": thread_id,
                    "metadata": str(metadata or {}),
                }
            )
            return {"ok": True}

    fake_adapter = FakeTelegramAdapter()
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")

    monkeypatch.setattr(
        GatewayRunner,
        "_build_adapter_map",
        lambda self, config: {Platform.TELEGRAM: fake_adapter},
    )
    captured: dict[str, dict[str, str]] = {}

    async def fake_run_prompt(prompt: str, **kwargs):
        del prompt
        captured["env_overrides"] = dict(kwargs["env_overrides"])
        session_path = kwargs["session_path"]
        return PromptResult(
            text="telegram reply",
            model="mock/io-test",
            provider="mock",
            session_path=session_path,
            messages=[],
            loaded_extensions=[],
            usage=Usage(input_tokens=12, output_tokens=5, cost_usd=0.02),
        )

    monkeypatch.setattr("io_cli.gateway_runner.run_prompt", fake_run_prompt)

    result = GatewayRunner(home=manager.home, poll_interval=0.1).run_sync(once=True)

    assert result["messages_processed"] == 1
    assert fake_adapter.sent
    assert fake_adapter.sent[0]["content"] == "telegram reply"
    assert captured["env_overrides"]["IO_SESSION_PLATFORM"] == "telegram"
    assert captured["env_overrides"]["IO_SESSION_CHAT_ID"] == "456"
    entries = manager.session_store().list_entries()
    assert len(entries) == 1
    assert entries[0].input_tokens == 12
    assert entries[0].output_tokens == 5


def test_gateway_runner_includes_tool_trace_in_reply(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("IO_TELEGRAM_ALLOW_ALL_USERS", "1")

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
                        chat_name="ever",
                        chat_type="dm",
                        user_id="111",
                        user_name="ever",
                    ),
                    text="hello gateway",
                    message_type=MessageType.TEXT,
                    message_id="m1",
                )
            ]

        async def send_message(self, chat_id: str, content: str, *, thread_id: str | None = None, metadata: dict | None = None) -> dict:
            _ = (chat_id, thread_id, metadata)
            self.sent.append(content)
            return {"ok": True}

    fake_adapter = FakeTelegramAdapter()
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")
    cfg = load_config(manager.home)
    cfg["gateway"] = {"tool_trace": True}
    from io_cli.config import save_config
    save_config(cfg, manager.home)

    monkeypatch.setattr(
        GatewayRunner,
        "_build_adapter_map",
        lambda self, config: {Platform.TELEGRAM: fake_adapter},
    )

    async def fake_run_prompt(prompt: str, **kwargs):
        on_event = kwargs.get("on_event")
        if callable(on_event):
            on_event("tool_call_start", {"tool": "search_files", "arguments": {"pattern": "x", "path": "/tmp"}})
        session_path = kwargs["session_path"]
        return PromptResult(
            text="telegram reply",
            model="mock/io-test",
            provider="mock",
            session_path=session_path,
            messages=[],
            loaded_extensions=[],
            usage=Usage(input_tokens=1, output_tokens=1, cost_usd=0.0),
        )

    monkeypatch.setattr("io_cli.gateway_runner.run_prompt", fake_run_prompt)
    _ = GatewayRunner(home=manager.home, poll_interval=0.1).run_sync(once=True)
    assert len(fake_adapter.sent) >= 2
    assert "search_files" in fake_adapter.sent[0]
    assert "telegram reply" in fake_adapter.sent[1]


def test_gateway_runner_includes_attachment_context_in_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("IO_TELEGRAM_ALLOW_ALL_USERS", "1")

    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="test"))
            self.sent: list[dict[str, str | None]] = []

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
                        chat_name="ever",
                        chat_type="dm",
                        user_id="111",
                        user_name="ever",
                    ),
                    text="please inspect this",
                    message_type=MessageType.DOCUMENT,
                    message_id="m2",
                    attachments=["document (notes.txt): https://example.test/notes.txt"],
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
            self.sent.append({"chat_id": chat_id, "content": content, "thread_id": thread_id})
            return {"ok": True}

    fake_adapter = FakeTelegramAdapter()
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")

    monkeypatch.setattr(
        GatewayRunner,
        "_build_adapter_map",
        lambda self, config: {Platform.TELEGRAM: fake_adapter},
    )
    captured: dict[str, str] = {}

    async def fake_run_prompt(prompt: str, **kwargs):
        del kwargs
        captured["prompt"] = prompt
        session_path = tmp_path / "attachment-session.jsonl"
        session_path.write_text("", encoding="utf-8")
        return PromptResult(
            text="processed attachment",
            model="mock/io-test",
            provider="mock",
            session_path=session_path,
            messages=[],
            loaded_extensions=[],
            usage=Usage(output_tokens=3),
        )

    monkeypatch.setattr("io_cli.gateway_runner.run_prompt", fake_run_prompt)

    result = GatewayRunner(home=manager.home, poll_interval=0.1).run_sync(once=True)

    assert result["messages_processed"] == 1
    assert "The user sent a document via Telegram." in captured["prompt"]
    assert "Telegram attachments:" in captured["prompt"]
    assert "document (notes.txt): https://example.test/notes.txt" in captured["prompt"]


def test_gateway_runner_handles_slash_commands_and_updates_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("IO_TELEGRAM_ALLOW_ALL_USERS", "1")

    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="test"))
            self.sent: list[dict[str, str | None]] = []

        async def _start(self) -> None:
            return None

        async def _stop(self) -> None:
            return None

        async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
            del timeout
            source = SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="456",
                chat_name="Ops",
                chat_type="dm",
                user_id="111",
                user_name="ever",
            )
            return [
                MessageEvent(source=source, text="/start", message_type=MessageType.COMMAND, message_id="c1"),
                MessageEvent(source=source, text="/model openai/gpt-4.1", message_type=MessageType.COMMAND, message_id="c2"),
                MessageEvent(source=source, text="/provider anthropic", message_type=MessageType.COMMAND, message_id="c3"),
                MessageEvent(source=source, text="/sethome", message_type=MessageType.COMMAND, message_id="c4"),
                MessageEvent(source=source, text="/status", message_type=MessageType.COMMAND, message_id="c5"),
                MessageEvent(source=source, text="/usage", message_type=MessageType.COMMAND, message_id="c6"),
                MessageEvent(source=source, text="/platforms", message_type=MessageType.COMMAND, message_id="c7"),
                MessageEvent(
                    source=source,
                    text="/skills browse --source official",
                    message_type=MessageType.COMMAND,
                    message_id="c8",
                ),
            ]

        async def send_message(
            self,
            chat_id: str,
            content: str,
            *,
            thread_id: str | None = None,
            metadata: dict | None = None,
        ) -> dict:
            self.sent.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "thread_id": thread_id,
                    "metadata": str(metadata or {}),
                }
            )
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
        raise AssertionError(f"run_prompt should not be called for slash commands: {prompt!r} {kwargs!r}")

    monkeypatch.setattr("io_cli.gateway_runner.run_prompt", should_not_run)

    result = GatewayRunner(home=manager.home, poll_interval=0.1).run_sync(once=True)

    assert result["messages_processed"] == 8
    config = load_config(manager.home)
    assert config["model"]["default"] == "openai/gpt-4.1"
    assert config["model"]["provider"] == "anthropic"
    gateway_config = manager.load_config()
    assert gateway_config.get_home_channel(Platform.TELEGRAM).chat_id == "456"
    assert len(fake_adapter.sent) == 8
    assert "IO gateway commands:" in fake_adapter.sent[0]["content"]
    assert "Default model set to openai/gpt-4.1." in fake_adapter.sent[1]["content"]
    assert "Default provider set to anthropic." in fake_adapter.sent[2]["content"]
    assert "Home channel for telegram set to 456." in fake_adapter.sent[3]["content"]
    assert "IO session status" in fake_adapter.sent[4]["content"]
    assert "IO session usage" in fake_adapter.sent[5]["content"]
    assert "Gateway platforms" in fake_adapter.sent[6]["content"]
    assert "telegram: active, home=456" in fake_adapter.sent[6]["content"]
    assert "Available skills:" in fake_adapter.sent[7]["content"]
    assert "official/migration/openclaw-migration" in fake_adapter.sent[7]["content"]


def test_gateway_runner_delivers_due_cron_job_to_telegram_home_channel(tmp_path: Path, monkeypatch) -> None:
    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="test"))
            self.sent: list[dict[str, str | None]] = []

        async def _start(self) -> None:
            return None

        async def _stop(self) -> None:
            return None

        async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
            del timeout
            return []

        async def send_message(
            self,
            chat_id: str,
            content: str,
            *,
            thread_id: str | None = None,
            metadata: dict | None = None,
        ) -> dict:
            self.sent.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "thread_id": thread_id,
                    "metadata": str(metadata or {}),
                }
            )
            return {"ok": True}

    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    fake_adapter = FakeTelegramAdapter()
    manager = GatewayManager(home=home)
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")
    cron = CronManager(home=home)
    job = cron.create_job(
        prompt="summarize the repo state",
        schedule="every 30m",
        cwd=cwd,
        name="Ops summary",
        deliver="telegram",
    )
    cron.trigger_job(job["id"])

    monkeypatch.setattr(
        GatewayRunner,
        "_build_adapter_map",
        lambda self, config: {Platform.TELEGRAM: fake_adapter},
    )

    async def fake_run_prompt(prompt: str, **kwargs):
        del prompt, kwargs
        session_path = home / "cron-session.jsonl"
        session_path.write_text("", encoding="utf-8")
        return PromptResult(
            text="all clear",
            model="mock/io-test",
            provider="mock",
            session_path=session_path,
            messages=[],
            loaded_extensions=[],
            usage=Usage(output_tokens=7),
        )

    monkeypatch.setattr("io_cli.main.run_prompt", fake_run_prompt)

    result = GatewayRunner(home=home, poll_interval=0.1).run_sync(once=True)

    assert result["cron_jobs_run"] == 1
    assert fake_adapter.sent
    assert fake_adapter.sent[0]["chat_id"] == "ops-room"
    assert "Cron job 'Ops summary' completed." in fake_adapter.sent[0]["content"]
    assert "all clear" in fake_adapter.sent[0]["content"]
    delivery = result["results"][0]["delivery"]
    assert delivery["telegram:ops-room"]["success"] is True
    assert delivery["local"]["success"] is True


def test_gateway_runner_handles_reasoning_personality_retry_undo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("IO_TELEGRAM_ALLOW_ALL_USERS", "1")

    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="test"))
            self.sent: list[dict[str, str | None]] = []
            self._calls = 0

        async def _start(self) -> None:
            return None

        async def _stop(self) -> None:
            return None

        async def poll_once(self, *, timeout: float = 0.0) -> list[MessageEvent]:
            del timeout
            source = SessionSource(
                platform=Platform.TELEGRAM,
                chat_id="456",
                chat_name="Ops",
                chat_type="dm",
                user_id="111",
                user_name="ever",
            )
            if self._calls == 0:
                self._calls += 1
                return [
                    MessageEvent(source=source, text="hello there", message_type=MessageType.TEXT, message_id="m1"),
                    MessageEvent(source=source, text="/reasoning high", message_type=MessageType.COMMAND, message_id="c1"),
                    MessageEvent(source=source, text="/personality pirate", message_type=MessageType.COMMAND, message_id="c2"),
                    MessageEvent(source=source, text="/retry", message_type=MessageType.COMMAND, message_id="c3"),
                    MessageEvent(source=source, text="/undo", message_type=MessageType.COMMAND, message_id="c4"),
                ]
            return []

        async def send_message(
            self,
            chat_id: str,
            content: str,
            *,
            thread_id: str | None = None,
            metadata: dict | None = None,
        ) -> dict:
            self.sent.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "thread_id": thread_id,
                    "metadata": str(metadata or {}),
                }
            )
            return {"ok": True}

    fake_adapter = FakeTelegramAdapter()
    manager = GatewayManager(home=tmp_path / "home")
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")

    monkeypatch.setattr(
        GatewayRunner,
        "_build_adapter_map",
        lambda self, config: {Platform.TELEGRAM: fake_adapter},
    )

    calls: list[str] = []

    async def fake_run_prompt(prompt: str, **kwargs):
        calls.append(prompt)
        session_path = kwargs["session_path"]
        session = SessionManager.open(session_path)
        session.append_message({"role": "user", "content": prompt})
        session.append_message({"role": "assistant", "content": "ok"})
        return PromptResult(
            text="ok",
            model="mock/io-test",
            provider="mock",
            session_path=session_path,
            messages=[],
            loaded_extensions=[],
            usage=Usage(input_tokens=3, output_tokens=2),
        )

    monkeypatch.setattr("io_cli.gateway_runner.run_prompt", fake_run_prompt)
    monkeypatch.setattr("io_cli.gateway_control.run_prompt", fake_run_prompt)

    result = GatewayRunner(home=manager.home, poll_interval=0.1, max_loops=2).run_sync(once=False)

    assert result["messages_processed"] == 0
    config = load_config(manager.home)
    assert config["model"]["reasoning_effort"] == "high"
    assert config["display"]["personality"] == "pirate"
    assert any("Reasoning effort set to high." in item["content"] for item in fake_adapter.sent)
    assert any("Personality set to pirate." in item["content"] for item in fake_adapter.sent)
    assert any("Undid the last user/assistant exchange" in item["content"] for item in fake_adapter.sent)
    assert any("Retrying the last user message..." in item["content"] for item in fake_adapter.sent)
    assert calls.count("hello there") == 2
