from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

from io_ai.types import Usage
from io_agent import SessionDB, resolve_runtime
from io_cli.approval_queue import ApprovalQueueStore
from io_cli.cli import main
from io_cli.config import (
    ensure_io_home,
    get_profile_home,
    load_config,
    resolve_io_home,
    save_config,
)
from io_cli.gateway import GatewayManager
from io_cli.gateway_models import Platform, PlatformConfig
from io_cli.gateway_platforms import SendResult
from io_cli.gateway_platforms.base import BasePlatformAdapter
from io_cli.gateway_runtime import write_runtime_status
from io_cli.gateway_session import SessionSource
from io_cli.main import PromptResult
from io_cli.mcp_serve import IOMCPBridge
from io_cli.model_router import apply_model_routing, model_router_status
from io_cli.pairing import PairingStore
from io_cli.profiles import (
    create_profile,
    delete_profile,
    export_profile,
    import_profile,
    list_profiles,
    rename_profile,
    set_active_profile,
)
from io_cli.session import SessionManager


def test_profile_lifecycle_clone_export_import_and_resolution(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("IO_HOME", raising=False)
    monkeypatch.delenv("IO_PROFILE", raising=False)

    default_home = ensure_io_home()
    config = load_config(default_home)
    config["display"]["streaming"] = True
    save_config(config, default_home)
    (default_home / "state.db").write_text("transient", encoding="utf-8")
    (default_home / "logs").mkdir(exist_ok=True)
    (default_home / "logs" / "runtime.log").write_text("skip me", encoding="utf-8")

    created = create_profile("alpha", clone_all=True)
    alpha_home = get_profile_home("alpha")
    assert created["name"] == "alpha"
    assert load_config(alpha_home)["display"]["streaming"] is True
    assert not (alpha_home / "state.db").exists()
    assert not (alpha_home / "logs" / "runtime.log").exists()

    set_active_profile("alpha")
    assert resolve_io_home() == alpha_home
    assert any(item["name"] == "alpha" and item["active"] for item in list_profiles())

    renamed = rename_profile("alpha", "beta")
    assert renamed["to"] == "beta"
    beta_home = get_profile_home("beta")
    assert beta_home.exists()

    archive = tmp_path / "beta-profile.tgz"
    exported = export_profile("beta", archive)
    assert exported["exported"] is True
    imported = import_profile("gamma", archive)
    gamma_home = get_profile_home("gamma")
    assert imported["imported"] is True
    assert load_config(gamma_home)["display"]["streaming"] is True
    assert not (gamma_home / "state.db").exists()

    deleted = delete_profile("beta")
    assert deleted["deleted"] is True
    assert not beta_home.exists()


def test_cli_profile_flag_selects_named_profile_home(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("IO_HOME", raising=False)
    monkeypatch.delenv("IO_PROFILE", raising=False)

    ensure_io_home()
    create_profile("work")
    work_home = get_profile_home("work")
    config = load_config(work_home)
    config["model"]["default"] = "mock/profile-home"
    save_config(config, work_home)

    exit_code = main(["-p", "work", "config", "get", "model.default"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.strip() == "mock/profile-home"


def test_model_router_prefers_cheap_model_for_simple_prompt_with_fallbacks(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    config = load_config(home)
    config["model"]["provider"] = "mock"
    config["model"]["default"] = "mock/strong"
    config["smart_model_routing"]["enabled"] = True
    config["smart_model_routing"]["cheap_model"] = {"provider": "mock", "model": "mock/cheap"}
    config["fallback_providers"] = [{"provider": "mock", "model": "mock/fallback"}]

    runtime = resolve_runtime(config=config, home=home, env={})
    routed = apply_model_routing(
        "summarize the last deploy",
        runtime=runtime,
        config=config,
        env={},
        home=home,
    )

    assert routed.route_kind == "smart"
    assert routed.model == "mock/cheap"
    assert [item.model for item in routed.fallback_targets] == ["mock/strong", "mock/fallback"]

    status = model_router_status(config=config, home=home, env={})
    assert status["enabled"] is True
    assert status["cheap_model"]["model"] == "mock/cheap"


def test_gateway_env_overrides_cover_telegram_and_slack(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:telegram")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_URL", "https://example.com/tg/webhook")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_PORT", "9443")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-primary")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-primary")
    monkeypatch.setenv("SLACK_TOKENS_FILE", str(tmp_path / "slack_tokens.json"))

    manager = GatewayManager(home=tmp_path / "home")
    config = manager.load_config()

    assert config.platforms[Platform.TELEGRAM].token == "123:telegram"
    assert config.platforms[Platform.TELEGRAM].extra["webhook_url"] == "https://example.com/tg/webhook"
    assert config.platforms[Platform.TELEGRAM].extra["webhook_port"] == "9443"
    assert config.platforms[Platform.SLACK].token == "xoxb-primary"
    assert config.platforms[Platform.SLACK].extra["app_token"] == "xapp-primary"
    assert config.platforms[Platform.SLACK].extra["tokens_file"] == str(tmp_path / "slack_tokens.json")


def test_remote_approval_queue_round_trips_and_persists_allow_always(tmp_path: Path) -> None:
    home = ensure_io_home(tmp_path / "home")
    store = ApprovalQueueStore(home=home)
    result: dict[str, str] = {}

    def _request() -> None:
        result["decision"] = store.request_approval(
            session_id="sess-approval",
            tool_name="bash",
            arguments={"command": "rm -rf /tmp/demo"},
            reason="Command requires approval.",
            timeout_seconds=2,
            poll_interval=0.05,
        )

    thread = threading.Thread(target=_request)
    thread.start()

    deadline = time.time() + 1.0
    pending = []
    while time.time() < deadline:
        pending = store.list_pending()
        if pending:
            break
        time.sleep(0.05)
    assert pending

    approval_id = str(pending[0]["approval_id"])
    responded = store.respond(approval_id, "allow_always")
    thread.join(timeout=2)

    assert responded is not None
    assert result["decision"] == "allow_always"
    assert store.policy_decision("bash", {"command": "rm -rf /tmp/demo"}) == "allow_always"
    assert store.request_approval(
        session_id="sess-approval-2",
        tool_name="bash",
        arguments={"command": "rm -rf /tmp/demo"},
        reason="Command requires approval.",
        timeout_seconds=0.1,
    ) == "allow_always"


def test_mcp_bridge_reads_sessions_messages_channels_and_permissions(tmp_path: Path) -> None:
    class FakeTelegramAdapter(BasePlatformAdapter):
        def __init__(self) -> None:
            super().__init__(platform=Platform.TELEGRAM, config=PlatformConfig(enabled=True, token="123:test"))
            self.sent: list[dict[str, object]] = []
            self.edits: list[dict[str, object]] = []
            self.typing: list[dict[str, object]] = []

        async def _start(self) -> None:
            return None

        async def _stop(self) -> None:
            return None

        async def poll_once(self, *, timeout: float = 0.0):
            del timeout
            return []

        async def send_message(self, chat_id: str, content: str, *, thread_id: str | None = None, metadata=None):
            self.sent.append(
                {
                    "chat_id": chat_id,
                    "content": content,
                    "thread_id": thread_id,
                    "metadata": dict(metadata or {}),
                }
            )
            return {"success": True, "message_id": "msg-1"}

        async def edit_message(self, chat_id: str, message_id: str, content: str) -> SendResult:
            self.edits.append({"chat_id": chat_id, "message_id": message_id, "content": content})
            return SendResult(success=True, message_id=message_id)

        async def send_typing(self, chat_id: str, metadata=None) -> None:
            self.typing.append({"chat_id": chat_id, "metadata": dict(metadata or {})})

    home = ensure_io_home(tmp_path / "home")
    db = SessionDB(home / "state.db")
    manager = GatewayManager(home=home)
    manager.configure(platforms=["telegram"], home_channel="ops-room", token="123:test")
    gateway_session = manager.session_store().get_or_create_session(
        SessionSource(
            platform=Platform.TELEGRAM,
            chat_id="456",
            chat_name="Ops",
            chat_type="dm",
            user_id="111",
            user_name="ever",
        )
    )
    session_id = gateway_session.session_id
    db.start_session(
        session_id,
        source="cli",
        cwd=str(tmp_path),
        model="mock/cheap",
        title="MCP test",
        model_config={"route_kind": "smart", "route_label": "cheap_model"},
    )
    db.append_message(session_id, role="user", content="hello mcp")
    db.append_message(session_id, role="assistant", content="see https://example.com/image.png")
    write_runtime_status(home, gateway_state="running", platform="telegram", platform_state="connected")

    approval_store = ApprovalQueueStore(home=home)
    result: dict[str, str] = {}

    def _request() -> None:
        result["decision"] = approval_store.request_approval(
            session_id=session_id,
            tool_name="bash",
            arguments={"command": "rm -rf /tmp/demo"},
            reason="Command requires approval.",
            timeout_seconds=2,
            poll_interval=0.05,
        )

    thread = threading.Thread(target=_request)
    thread.start()
    deadline = time.time() + 1.0
    tool_pending = []
    while time.time() < deadline:
        tool_pending = approval_store.list_pending()
        if tool_pending:
            break
        time.sleep(0.05)
    assert tool_pending

    pairing_store = PairingStore(home=home)
    code = pairing_store.generate_code("telegram", "111", "ever")
    assert code is not None

    bridge = IOMCPBridge(home=home)
    fake_adapter = FakeTelegramAdapter()
    bridge.gateway_control.adapter_overrides[Platform.TELEGRAM] = fake_adapter

    conversations = bridge.conversations_list(limit=10)
    assert conversations["conversations"][0]["session_id"] == session_id
    assert conversations["conversations"][0]["route_kind"] == "smart"

    conversation = bridge.conversation_get(session_id)
    assert conversation["model_config"]["route_label"] == "cheap_model"

    messages = bridge.messages_read(session_id)
    assert [item["role"] for item in messages["messages"]] == ["user", "assistant"]

    attachments = bridge.attachments_fetch(session_id)
    assert attachments["attachments"][0]["value"] == "https://example.com/image.png"

    channels = bridge.channels_list()
    assert channels["channels"][0]["platform"] == "telegram"
    assert channels["channels"][0]["runtime_state"] == "connected"
    assert channels["channels"][0]["capabilities"]["send"] is True
    assert channels["channels"][0]["capabilities"]["edit"] is True
    assert channels["channels"][0]["capabilities"]["typing"] is True

    skills = bridge.skills_browse(source="official")
    assert any(item["identifier"] == "official/migration/openclaw-migration" for item in skills["skills"])

    installed = bridge.skills_install("official/migration/openclaw-migration")
    assert installed["success"] is True
    installed_list = bridge.skills_list_installed()
    assert installed_list["count"] == 1

    permissions = bridge.permissions_list_open()
    assert permissions["permissions"][0]["approval_id"].startswith("approval:")
    assert permissions["permissions"][0]["kind"] == "tool"

    approved = bridge.permissions_respond(
        permissions["permissions"][0]["approval_id"],
        "allow_once",
    )
    assert approved["approved"] is True
    thread.join(timeout=2)
    assert result["decision"] == "allow_once"

    pairing_permissions = bridge.permissions_list_open()
    assert any(item["approval_id"].startswith("pairing:telegram:") for item in pairing_permissions["permissions"])

    send_result = asyncio.run(
        bridge.messages_send(
            session_id=session_id,
            platform=None,
            chat_id=None,
            content="hello from mcp",
            metadata={"thread_id": "7"},
        )
    )
    assert send_result["success"] is True
    assert fake_adapter.sent[0]["chat_id"] == "456"
    assert fake_adapter.sent[0]["metadata"]["thread_id"] == "7"

    edit_result = asyncio.run(
        bridge.messages_edit(
            session_id=session_id,
            platform=None,
            chat_id=None,
            message_id="msg-1",
            content="edited from mcp",
        )
    )
    assert edit_result["success"] is True
    assert fake_adapter.edits[0]["message_id"] == "msg-1"

    typing_result = asyncio.run(
        bridge.messages_typing(
            session_id=session_id,
            platform=None,
            chat_id=None,
            metadata={"thread_id": "7"},
        )
    )
    assert typing_result["success"] is True
    assert fake_adapter.typing[0]["chat_id"] == "456"

    set_home = bridge.channel_set_home(session_id=session_id, platform=None, chat_id=None, name="Ops Home")
    assert set_home["success"] is True
    assert manager.load_config().get_home_channel(Platform.TELEGRAM).name == "Ops Home"

    status_payload = asyncio.run(bridge.conversation_control(action="status", session_id=session_id))
    assert status_payload["success"] is True
    assert "IO session status" in status_payload["message"]

    usage_payload = asyncio.run(bridge.conversation_control(action="usage", session_id=session_id))
    assert usage_payload["success"] is True
    assert "IO session usage" in usage_payload["message"]

    session_file = home / "gateway" / "agent_sessions" / f"{session_id}.jsonl"
    session = SessionManager.create_at_path(tmp_path, session_file=session_file, session_id=session_id)
    session.append_message({"role": "user", "content": "retry me"})
    session.append_message({"role": "assistant", "content": "original reply"})

    async def fake_run_prompt(prompt: str, **kwargs):
        session = SessionManager.open(kwargs["session_path"])
        session.append_message({"role": "user", "content": prompt})
        session.append_message({"role": "assistant", "content": "retried"})
        return PromptResult(
            text="retried",
            model="mock/io-test",
            provider="mock",
            session_path=kwargs["session_path"],
            messages=[],
            loaded_extensions=[],
            usage=Usage(input_tokens=2, output_tokens=1),
        )

    from io_cli import gateway_control as gateway_control_module

    original_run_prompt = gateway_control_module.run_prompt
    gateway_control_module.run_prompt = fake_run_prompt
    try:
        retry_payload = asyncio.run(bridge.conversation_control(action="retry", session_id=session_id))
    finally:
        gateway_control_module.run_prompt = original_run_prompt

    assert retry_payload["success"] is True
    assert "Retrying the last user message" in retry_payload["message"]

    undo_payload = asyncio.run(bridge.conversation_control(action="undo", session_id=session_id))
    assert undo_payload["success"] is True
