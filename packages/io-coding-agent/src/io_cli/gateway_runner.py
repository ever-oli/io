"""Foreground gateway runner for IO."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path
from typing import Any

from io_agent import resolve_runtime

from .auth import auth_status
from .commands import GATEWAY_KNOWN_COMMANDS, gateway_help_lines, resolve_command
from .config import ensure_io_home, load_config, load_env, save_config
from .cron import CronManager
from .gateway import GatewayManager
from .gateway_delivery import DeliveryRouter
from .gateway_models import GatewayConfig, HomeChannel, Platform, PlatformConfig
from .gateway_platforms import (
    APIServerAdapter,
    BasePlatformAdapter,
    DingTalkAdapter,
    DiscordAdapter,
    EmailAdapter,
    HomeAssistantAdapter,
    MatrixAdapter,
    MattermostAdapter,
    MessageEvent,
    MessageType,
    SignalAdapter,
    SlackAdapter,
    SmsAdapter,
    TelegramAdapter,
    WebhookAdapter,
    WhatsAppAdapter,
)
from .gateway_runtime import remove_pid_file, write_pid_file, write_runtime_status
from .gateway_session import (
    SessionContext,
    SessionSource,
    build_session_context_prompt,
)
from .agent.skill_commands import build_skill_invocation_message
from .main import run_prompt
from .pairing import PairingStore
from .session import SessionManager
from .toolsets import enabled_toolsets_for_platform


logger = logging.getLogger(__name__)

ADAPTER_TYPES: dict[Platform, type[BasePlatformAdapter]] = {
    Platform.TELEGRAM: TelegramAdapter,
    Platform.DISCORD: DiscordAdapter,
    Platform.WHATSAPP: WhatsAppAdapter,
    Platform.SLACK: SlackAdapter,
    Platform.SIGNAL: SignalAdapter,
    Platform.MATTERMOST: MattermostAdapter,
    Platform.MATRIX: MatrixAdapter,
    Platform.HOMEASSISTANT: HomeAssistantAdapter,
    Platform.EMAIL: EmailAdapter,
    Platform.SMS: SmsAdapter,
    Platform.DINGTALK: DingTalkAdapter,
    Platform.API_SERVER: APIServerAdapter,
    Platform.WEBHOOK: WebhookAdapter,
}


class GatewayRunner:
    def __init__(
        self,
        *,
        home: Path | None = None,
        poll_interval: float = 2.0,
        max_loops: int | None = None,
        cron_interval: float = 60.0,
    ) -> None:
        self.home = ensure_io_home(home)
        self.poll_interval = max(0.1, float(poll_interval))
        self.max_loops = max_loops if max_loops is None or max_loops > 0 else 1
        self.cron_interval = max(self.poll_interval, float(cron_interval))
        self.manager = GatewayManager(home=self.home)
        self.stop_event = asyncio.Event()
        self.loop_count = 0
        self.adapters: dict[Platform, BasePlatformAdapter] = {}
        self.delivery_router: DeliveryRouter | None = None
        self.gateway_config: GatewayConfig | None = None
        self._next_cron_tick_at: float | None = None
        self._active_sessions: set[str] = set()
        self.pairing_store = PairingStore(home=self.home)

    def request_stop(self) -> None:
        self.stop_event.set()

    def _install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, lambda *_args: self.request_stop())
            except Exception:
                continue

    def _build_adapter_map(self, config: GatewayConfig) -> dict[Platform, BasePlatformAdapter]:
        adapters: dict[Platform, BasePlatformAdapter] = {}
        for platform, platform_config in config.platforms.items():
            if platform == Platform.LOCAL or not platform_config.enabled:
                continue
            adapter_type = ADAPTER_TYPES.get(platform)
            if adapter_type is None:
                continue
            adapter = adapter_type(platform_config)
            if hasattr(adapter, "gateway_runner"):
                setattr(adapter, "gateway_runner", self)
            adapters[platform] = adapter
        return adapters

    def _desired_state(self) -> str:
        return str(self.manager.load_state().get("desired_state", "stopped"))

    def _resolve_gateway_cwd(self) -> Path:
        config = load_config(self.home)
        terminal = config.get("terminal", {})
        if not isinstance(terminal, dict):
            terminal = {}
        raw = str(terminal.get("cwd", "") or "").strip()
        if not raw or raw in {".", "./", "auto", "cwd"}:
            return Path.home().resolve()
        path = Path(raw).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (Path.home() / path).resolve()

    def _resolve_toolsets(self, platform: Platform) -> list[str]:
        config = load_config(self.home)
        return enabled_toolsets_for_platform(config, platform=platform.value)

    def _ensure_gateway_session_file(self, context: SessionContext, cwd: Path) -> Path:
        session_dir = self.home / "gateway" / "agent_sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        session_file = session_dir / f"{context.session_id}.jsonl"
        if not session_file.exists():
            SessionManager.create_at_path(cwd, session_file=session_file, session_id=context.session_id)
        return session_file

    def _build_session_env(self, context: SessionContext, session_file: Path) -> dict[str, str]:
        source = context.source
        env: dict[str, str] = {
            "IO_GATEWAY_SESSION": "1",
            "IO_SESSION_PLATFORM": source.platform.value,
            "IO_SESSION_CHAT_ID": source.chat_id,
            "IO_SESSION_CHAT_TYPE": source.chat_type,
            "IO_SESSION_ID": context.session_id,
            "IO_SESSION_KEY": context.session_key,
            "IO_SESSION_PATH": str(session_file),
        }
        if source.chat_name:
            env["IO_SESSION_CHAT_NAME"] = source.chat_name
        if source.thread_id:
            env["IO_SESSION_THREAD_ID"] = source.thread_id
        if source.user_id:
            env["IO_SESSION_USER_ID"] = source.user_id
        if source.user_name:
            env["IO_SESSION_USER_NAME"] = source.user_name
        return env

    def _record_session_usage(self, context: SessionContext, *, result) -> None:
        usage = getattr(result, "usage", None)
        if usage is None:
            return
        self.manager.session_store().update_session(
            context.session_key,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_tokens", 0) or 0),
            cache_write_tokens=int(getattr(usage, "cache_write_tokens", 0) or 0),
            last_prompt_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            estimated_cost_usd=float(getattr(usage, "cost_usd", 0.0) or 0.0),
            cost_status="estimated" if float(getattr(usage, "cost_usd", 0.0) or 0.0) else "unknown",
        )

    def _resolve_runtime_state(self) -> tuple[dict[str, Any], Any]:
        config = load_config(self.home)
        env = {**load_env(self.home), **os.environ}
        runtime = resolve_runtime(config=config, home=self.home, env=env)
        return config, runtime

    def _env_truthy(self, *names: str) -> bool:
        env = {**load_env(self.home), **os.environ}
        return any(str(env.get(name, "")).strip().lower() in {"1", "true", "yes", "on"} for name in names)

    def _env_csv_values(self, *names: str) -> set[str]:
        env = {**load_env(self.home), **os.environ}
        values: set[str] = set()
        for name in names:
            raw = str(env.get(name, "") or "").strip()
            if not raw:
                continue
            values.update(item.strip() for item in raw.split(",") if item.strip())
        return values

    def _is_user_authorized(self, source: SessionSource) -> bool:
        if source.platform in {Platform.HOMEASSISTANT, Platform.WEBHOOK}:
            return True
        user_id = str(source.user_id or "").strip()
        if not user_id:
            return False

        platform_key = source.platform.value.upper().replace("-", "_")
        if self._env_truthy(f"IO_{platform_key}_ALLOW_ALL_USERS", f"{platform_key}_ALLOW_ALL_USERS"):
            return True
        if self.pairing_store.is_approved(source.platform.value, user_id):
            return True

        allowed_ids = self._env_csv_values(
            f"IO_{platform_key}_ALLOWED_USERS",
            f"{platform_key}_ALLOWED_USERS",
            "IO_GATEWAY_ALLOWED_USERS",
            "GATEWAY_ALLOWED_USERS",
        )
        if not allowed_ids:
            return self._env_truthy("IO_GATEWAY_ALLOW_ALL_USERS", "GATEWAY_ALLOW_ALL_USERS")

        candidates = {user_id}
        if "@" in user_id:
            candidates.add(user_id.split("@", 1)[0])
        return bool(candidates & allowed_ids)

    def _get_unauthorized_dm_behavior(self, platform: Platform | None) -> str:
        config = self.gateway_config or self.manager.load_config()
        return config.get_unauthorized_dm_behavior(platform)

    def _origin_source(self, payload: dict[str, Any] | None) -> SessionSource | None:
        if not isinstance(payload, dict):
            return None
        try:
            return SessionSource.from_dict(payload)
        except Exception:
            return None

    def _format_cron_delivery_message(self, job_result: dict[str, Any]) -> str:
        name = str(job_result.get("name") or job_result.get("id") or "cron job")
        schedule = str(job_result.get("schedule_display") or "")
        output_path = str(job_result.get("output_path") or "")
        session_path = str(job_result.get("session_path") or "")
        if job_result.get("error"):
            lines = [
                f"Cron job '{name}' failed.",
                "",
                str(job_result["error"]),
            ]
        else:
            lines = [
                f"Cron job '{name}' completed.",
            ]
            if schedule:
                lines.append(f"Schedule: {schedule}")
            if job_result.get("next_run_at"):
                lines.append(f"Next run: {job_result['next_run_at']}")
            result_text = str(job_result.get("result") or "").strip()
            if result_text:
                lines.extend(["", result_text])
        if output_path:
            lines.extend(["", f"Output log: {output_path}"])
        if session_path:
            lines.append(f"Session: {session_path}")
        return "\n".join(lines).strip()

    async def _deliver_cron_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.delivery_router is None:
            return results
        delivered: list[dict[str, Any]] = []
        for item in results:
            updated = dict(item)
            origin = self._origin_source(updated.get("origin"))
            targets = self.delivery_router.resolve_targets(
                updated.get("deliver", "local"),
                origin=origin,
            )
            delivery = await self.delivery_router.deliver(
                self._format_cron_delivery_message(updated),
                targets,
                job_id=str(updated.get("id") or ""),
                job_name=str(updated.get("name") or "Cron Job"),
                metadata={
                    "status": updated.get("last_status") or ("failed" if updated.get("error") else "completed"),
                    "session_path": updated.get("session_path"),
                },
                existing_local_path=str(updated.get("output_path") or "") or None,
            )
            updated["delivery"] = delivery
            updated["delivery_targets"] = [target.to_string() for target in targets]
            delivered.append(updated)
        return delivered

    async def _send_platform_message(
        self,
        platform: Platform,
        chat_id: str,
        content: str,
        *,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        adapter = self.adapters.get(platform)
        if adapter is None:
            return
        await adapter.send_message(chat_id, content, thread_id=thread_id, metadata=metadata)

    def _build_event_prompt(self, event: MessageEvent) -> str:
        prompt = event.text.strip() or "(no text)"
        notes: list[str] = []
        platform_label = event.source.platform.value.replace("-", " ").title()
        if event.message_type in {MessageType.IMAGE, MessageType.PHOTO}:
            notes.append(f"The user sent an image via {platform_label}.")
        elif event.message_type == MessageType.AUDIO:
            notes.append(f"The user sent audio via {platform_label}.")
        elif event.message_type == MessageType.VOICE:
            notes.append(f"The user sent a voice note via {platform_label}.")
        elif event.message_type == MessageType.VIDEO:
            notes.append(f"The user sent a video via {platform_label}.")
        elif event.message_type == MessageType.DOCUMENT:
            notes.append(f"The user sent a document via {platform_label}.")
        elif event.message_type == MessageType.STICKER:
            notes.append(f"The user sent a sticker via {platform_label}.")
        attachments = list(event.attachments)
        if event.media_urls:
            attachments.extend(path for path in event.media_urls if path not in attachments)
        if attachments:
            notes.extend([f"{platform_label} attachments:"])
            notes.extend(f"- {item}" for item in attachments)
        if not notes:
            return prompt
        return f"{prompt}\n\n" + "\n".join(notes)

    def _parse_command_text(self, text: str) -> tuple[str, str] | None:
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None
        first, _, remainder = stripped.partition(" ")
        name = first[1:]
        if "@" in name:
            name = name.split("@", 1)[0]
        name = name.replace("_", "-").lower()
        return name, remainder.strip()

    def _format_session_status(
        self,
        *,
        source: SessionSource,
        context: SessionContext,
        session_file: Path,
    ) -> str:
        config, runtime = self._resolve_runtime_state()
        session = SessionManager.open(session_file)
        toolsets = self._resolve_toolsets(source.platform)
        home_channel = self.manager.load_config().get_home_channel(source.platform)
        lines = [
            "IO session status",
            f"Session ID: {context.session_id}",
            f"Source: {source.description}",
            f"Model: {runtime.model}",
            f"Provider: {runtime.provider}",
            f"Toolsets: {', '.join(toolsets) if toolsets else '(none)'}",
            f"Messages: {len(session.entries)}",
            f"Session file: {session_file}",
        ]
        if home_channel is not None:
            lines.append(f"Home channel: {home_channel.chat_id}")
        terminal = config.get("terminal", {})
        if isinstance(terminal, dict):
            lines.append(f"Terminal backend: {terminal.get('backend', 'local')}")
        return "\n".join(lines)

    def _format_usage_status(self, *, context: SessionContext) -> str:
        entry = self.manager.session_store().get_entry(context.session_key)
        if entry is None:
            return "No usage is recorded for this chat yet."
        lines = [
            "IO session usage",
            f"Input tokens: {entry.input_tokens}",
            f"Output tokens: {entry.output_tokens}",
            f"Cache read: {entry.cache_read_tokens}",
            f"Cache write: {entry.cache_write_tokens}",
            f"Total tokens: {entry.total_tokens}",
            f"Estimated cost: ${entry.estimated_cost_usd:.4f}",
            f"Cost status: {entry.cost_status}",
        ]
        return "\n".join(lines)

    def _format_provider_status(self) -> str:
        status = auth_status(self.home)
        providers = status.get("providers", {})
        active = str(status.get("active_provider") or "none")
        lines = [f"Active provider: {active}"]
        if isinstance(providers, dict):
            for provider_name in sorted(providers):
                provider = providers[provider_name]
                label = str(provider.get("label", provider_name))
                logged_in = "configured" if provider.get("logged_in") else "not configured"
                lines.append(f"- {label}: {logged_in}")
        return "\n".join(lines)

    def _format_platform_status(self) -> str:
        status = self.manager.status()
        lines = [
            "Gateway platforms",
            f"Desired state: {status.get('desired_state', 'stopped')}",
            f"Runtime: {status.get('runtime', {}).get('gateway_state') or 'stopped'}",
        ]
        configured = list(status.get("configured_platforms", []))
        if not configured:
            lines.append("Configured platforms: (none)")
            return "\n".join(lines)
        lines.append("Configured platforms:")
        runtime_platforms = status.get("runtime", {}).get("platforms", {})
        home_channels = status.get("home_channels", {})
        for platform_name in configured:
            runtime_state = "inactive"
            if isinstance(runtime_platforms, dict):
                runtime_state = str(runtime_platforms.get(platform_name, {}).get("state", "inactive"))
            home_channel = None
            if isinstance(home_channels, dict):
                home_channel = home_channels.get(platform_name, {}).get("chat_id")
            suffix = f", home={home_channel}" if home_channel else ""
            lines.append(f"- {platform_name}: {runtime_state}{suffix}")
        return "\n".join(lines)

    def _collect_message_entries(self, session_file: Path) -> list[dict[str, Any]]:
        try:
            session = SessionManager.open(session_file)
        except Exception:
            return []
        entries: list[dict[str, Any]] = []
        for entry in session.get_branch():
            if entry.get("type") != "message":
                continue
            message = entry.get("message")
            if isinstance(message, dict):
                entries.append(entry)
        return entries

    def _last_user_message_content(self, session_file: Path) -> str | None:
        for entry in reversed(self._collect_message_entries(session_file)):
            message = entry.get("message", {})
            if str(message.get("role", "")) == "user":
                text = str(message.get("content", "")).strip()
                if text:
                    return text
        return None

    def _undo_last_exchange(self, session_file: Path) -> tuple[bool, str]:
        try:
            session = SessionManager.open(session_file)
        except Exception as exc:
            return False, f"Unable to open session: {exc}"
        branch = session.get_branch()
        message_entries = [entry for entry in branch if entry.get("type") == "message" and isinstance(entry.get("message"), dict)]
        if not message_entries:
            return False, "Nothing to undo in this session yet."

        last_assistant_idx = -1
        for idx in range(len(message_entries) - 1, -1, -1):
            role = str(message_entries[idx]["message"].get("role", ""))
            if role == "assistant":
                last_assistant_idx = idx
                break
        if last_assistant_idx <= 0:
            return False, "No completed user/assistant exchange to undo yet."

        user_idx = -1
        for idx in range(last_assistant_idx - 1, -1, -1):
            role = str(message_entries[idx]["message"].get("role", ""))
            if role == "user":
                user_idx = idx
                break
        if user_idx < 0:
            return False, "No completed user/assistant exchange to undo yet."

        parent_id = message_entries[user_idx].get("parentId")
        if parent_id:
            session.branch(parent_id)
        else:
            session.leaf_id = None
        return True, "Undid the last user/assistant exchange for this chat."

    async def _dispatch_gateway_command(
        self,
        event: MessageEvent,
        *,
        context: SessionContext | None,
        session_file: Path | None,
    ) -> bool:
        parsed = self._parse_command_text(event.text)
        if parsed is None:
            return False
        raw_name, arguments = parsed
        if raw_name == "start":
            help_lines = ["IO gateway commands:", *gateway_help_lines(), "", "Send a normal message to chat with IO."]
            await self._send_platform_message(
                event.source.platform,
                event.source.chat_id,
                "\n".join(help_lines),
                thread_id=event.source.thread_id,
            )
            return True
        command = resolve_command(raw_name)
        if command is None:
            cwd = self._resolve_gateway_cwd()
            plat = event.source.platform.value
            expanded = build_skill_invocation_message(
                f"/{raw_name}",
                user_instruction=arguments,
                home=self.home,
                cwd=cwd,
                platform=plat,
            )
            if expanded:
                event.text = expanded
                return False
            await self._send_platform_message(
                event.source.platform,
                event.source.chat_id,
                f"Unknown command '/{raw_name}'. Send /help to see the available gateway commands.",
                thread_id=event.source.thread_id,
            )
            return True
        source = event.source
        canonical = command.name

        if canonical == "platforms":
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                self._format_platform_status(),
                thread_id=source.thread_id,
            )
            return True

        if command.cli_only:
            await self._send_platform_message(
                event.source.platform,
                event.source.chat_id,
                f"/{command.name} is only available in the local IO CLI.",
                thread_id=event.source.thread_id,
            )
            return True

        if canonical in {"help", "start"}:
            help_lines = ["IO gateway commands:", *gateway_help_lines(), "", "Send a normal message to chat with IO."]
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                "\n".join(help_lines),
                thread_id=source.thread_id,
            )
            return True

        if canonical == "new":
            new_context = self.manager.build_session_context(source, force_new=True)
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"Started a new session for this chat.\nSession ID: {new_context.session_id}",
                thread_id=source.thread_id,
            )
            return True

        if canonical == "sethome":
            gateway_config = self.manager.load_config()
            platform_config = gateway_config.platforms.get(source.platform) or PlatformConfig(enabled=True)
            platform_config.enabled = True
            platform_config.home_channel = HomeChannel(
                platform=source.platform,
                chat_id=source.chat_id,
                name=source.chat_name or "Home",
            )
            gateway_config.platforms[source.platform] = platform_config
            self.manager.save_config(gateway_config)
            self.gateway_config = gateway_config
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"This chat is now the home channel for {source.platform.value}.",
                thread_id=source.thread_id,
            )
            return True

        if canonical == "provider":
            if arguments:
                selected = arguments.strip()
                known = {"auto"}
                providers = auth_status(self.home).get("providers", {})
                if isinstance(providers, dict):
                    known.update(str(name) for name in providers)
                if selected not in known and not selected.startswith("custom:"):
                    await self._send_platform_message(
                        source.platform,
                        source.chat_id,
                        f"Unknown provider '{selected}'. Known providers: {', '.join(sorted(known))}",
                        thread_id=source.thread_id,
                    )
                    return True
                config, _runtime = self._resolve_runtime_state()
                config.setdefault("model", {})
                config["model"]["provider"] = selected
                save_config(config, self.home)
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    f"Default provider set to {selected}.",
                    thread_id=source.thread_id,
                )
                return True
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                self._format_provider_status(),
                thread_id=source.thread_id,
            )
            return True

        if canonical == "reasoning":
            config, runtime = self._resolve_runtime_state()
            model_cfg = config.setdefault("model", {})
            display_cfg = config.setdefault("display", {})
            effort_values = {"none", "minimal", "low", "medium", "high", "xhigh"}
            flag_values = {"on", "show", "off", "hide"}
            selected = arguments.strip().lower()
            if selected:
                if selected in effort_values:
                    model_cfg["reasoning_effort"] = selected
                    save_config(config, self.home)
                    await self._send_platform_message(
                        source.platform,
                        source.chat_id,
                        f"Reasoning effort set to {selected}.",
                        thread_id=source.thread_id,
                    )
                    return True
                if selected in flag_values:
                    show = selected in {"on", "show"}
                    display_cfg["show_reasoning"] = show
                    save_config(config, self.home)
                    await self._send_platform_message(
                        source.platform,
                        source.chat_id,
                        "Reasoning display is now visible." if show else "Reasoning display is now hidden.",
                        thread_id=source.thread_id,
                    )
                    return True
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    "Usage: /reasoning [none|minimal|low|medium|high|xhigh|show|hide|on|off]",
                    thread_id=source.thread_id,
                )
                return True
            effort = str(model_cfg.get("reasoning_effort", "(default)"))
            show = bool(display_cfg.get("show_reasoning", False))
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"Reasoning effort: {effort}\nReasoning display: {'visible' if show else 'hidden'}\nModel: {runtime.model}",
                thread_id=source.thread_id,
            )
            return True

        if canonical == "personality":
            config, _runtime = self._resolve_runtime_state()
            display_cfg = config.setdefault("display", {})
            selected = arguments.strip()
            if selected:
                display_cfg["personality"] = selected
                save_config(config, self.home)
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    f"Personality set to {selected}.",
                    thread_id=source.thread_id,
                )
                return True
            current = str(display_cfg.get("personality", "operator"))
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"Current personality: {current}",
                thread_id=source.thread_id,
            )
            return True

        if canonical == "model":
            if arguments:
                selected = arguments.strip()
                config, _runtime = self._resolve_runtime_state()
                config.setdefault("model", {})
                config["model"]["default"] = selected
                save_config(config, self.home)
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    f"Default model set to {selected}.",
                    thread_id=source.thread_id,
                )
                return True
            _config, runtime = self._resolve_runtime_state()
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"Current model: {runtime.model}\nCurrent provider: {runtime.provider}",
                thread_id=source.thread_id,
            )
            return True

        if canonical in {"status", "usage"}:
            current_context = context or self.manager.build_session_context(source, force_new=False)
            cwd = self._resolve_gateway_cwd()
            current_session_file = session_file or self._ensure_gateway_session_file(current_context, cwd)
            payload = (
                self._format_session_status(
                    source=source,
                    context=current_context,
                    session_file=current_session_file,
                )
                if canonical == "status"
                else self._format_usage_status(context=current_context)
            )
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                payload,
                thread_id=source.thread_id,
            )
            return True

        if canonical == "undo":
            if session_file is None:
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    "No active session file for this chat yet.",
                    thread_id=source.thread_id,
                )
                return True
            ok, message = self._undo_last_exchange(session_file)
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                message,
                thread_id=source.thread_id,
            )
            return True

        if canonical == "retry":
            if session_file is None:
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    "No active session file for this chat yet.",
                    thread_id=source.thread_id,
                )
                return True
            prompt = self._last_user_message_content(session_file)
            if not prompt:
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    "No previous user message available to retry.",
                    thread_id=source.thread_id,
                )
                return True
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                "Retrying the last user message...",
                thread_id=source.thread_id,
            )
            runtime_config = load_config(self.home)
            redact_pii = bool(runtime_config.get("privacy", {}).get("redact_pii", False))
            system_prompt_suffix = build_session_context_prompt(context, redact_pii=redact_pii) if context else ""
            toolsets = self._resolve_toolsets(source.platform)
            env_overrides = self._build_session_env(context, session_file) if context else {}
            cwd = self._resolve_gateway_cwd()
            try:
                result = await run_prompt(
                    prompt,
                    cwd=cwd,
                    home=self.home,
                    session_path=session_file,
                    toolsets=toolsets,
                    system_prompt_suffix=system_prompt_suffix,
                    env_overrides=env_overrides,
                )
                if context is not None:
                    self._record_session_usage(context, result=result)
                response = result.text.strip() or "(no response)"
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    response,
                    thread_id=source.thread_id,
                    metadata={"session_path": str(result.session_path)},
                )
            except Exception as exc:
                logger.exception("Gateway retry handling failed")
                await self._send_platform_message(
                    source.platform,
                    source.chat_id,
                    f"IO hit an error while retrying that message:\n{exc}",
                    thread_id=source.thread_id,
                )
            return True

        if raw_name in GATEWAY_KNOWN_COMMANDS:
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"/{command.name} is available in the local IO CLI. Use /help for gateway-supported commands.",
                thread_id=source.thread_id,
            )
            return True
        return False

    async def _handle_message(self, event: MessageEvent) -> None:
        source = event.source
        text = event.text.strip()

        if not self._is_user_authorized(source):
            if source.chat_type == "dm" and self._get_unauthorized_dm_behavior(source.platform) == "pair":
                code = self.pairing_store.generate_code(
                    source.platform.value,
                    str(source.user_id or ""),
                    source.user_name or "",
                )
                if code:
                    await self._send_platform_message(
                        source.platform,
                        source.chat_id,
                        "Hi~ I don't recognize you yet!\n\n"
                        f"Here's your pairing code: `{code}`\n\n"
                        "Ask the bot owner to run:\n"
                        f"`io pairing approve {source.platform.value} {code}`",
                        thread_id=source.thread_id,
                    )
                else:
                    await self._send_platform_message(
                        source.platform,
                        source.chat_id,
                        "Too many pairing requests right now~ Please try again later!",
                        thread_id=source.thread_id,
                    )
            return

        context = self.manager.build_session_context(source, force_new=False)
        session_key = context.session_key
        if session_key in self._active_sessions:
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                "Still working on the previous message for this chat. Send another message in a moment.",
                thread_id=source.thread_id,
            )
            return

        cwd = self._resolve_gateway_cwd()
        session_file = self._ensure_gateway_session_file(context, cwd)
        command_handled = False
        if text.startswith("/"):
            command_handled = await self._dispatch_gateway_command(event, context=context, session_file=session_file)
        if command_handled:
            return
        runtime_config = load_config(self.home)
        redact_pii = bool(runtime_config.get("privacy", {}).get("redact_pii", False))
        system_prompt_suffix = build_session_context_prompt(context, redact_pii=redact_pii)
        toolsets = self._resolve_toolsets(source.platform)
        env_overrides = self._build_session_env(context, session_file)
        prompt = self._build_event_prompt(event)

        self._active_sessions.add(session_key)
        try:
            result = await run_prompt(
                prompt,
                cwd=cwd,
                home=self.home,
                session_path=session_file,
                toolsets=toolsets,
                system_prompt_suffix=system_prompt_suffix,
                env_overrides=env_overrides,
            )
            self._record_session_usage(context, result=result)
            response = result.text.strip() or "(no response)"
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                response,
                thread_id=source.thread_id,
                metadata={"session_path": str(result.session_path)},
            )
        except Exception as exc:
            logger.exception("Gateway message handling failed")
            await self._send_platform_message(
                source.platform,
                source.chat_id,
                f"IO hit an error while processing that message:\n{exc}",
                thread_id=source.thread_id,
            )
        finally:
            self._active_sessions.discard(session_key)

    async def _start_runtime(self) -> None:
        self.manager.start()
        self._install_signal_handlers()
        write_pid_file(self.home)
        write_runtime_status(self.home, gateway_state="starting", exit_reason=None)
        self.gateway_config = self.manager.load_config()
        self.adapters = {}
        self.delivery_router = DeliveryRouter(home=self.home, config=self.gateway_config, adapters=self.adapters)

        for platform, adapter in self._build_adapter_map(self.gateway_config).items():
            try:
                adapter.set_message_handler(self._handle_message)
                await adapter.start()
                self.adapters[platform] = adapter
                write_runtime_status(
                    self.home,
                    platform=platform.value,
                    platform_state="running",
                    error_code=None,
                    error_message=None,
                )
            except Exception as exc:
                write_runtime_status(
                    self.home,
                    platform=platform.value,
                    platform_state="error",
                    error_code="startup_failed",
                    error_message=str(exc),
                )

        for platform in self.gateway_config.get_connected_platforms():
            if platform in self.adapters:
                continue
            write_runtime_status(
                self.home,
                platform=platform.value,
                platform_state="unavailable",
                error_code="adapter_unavailable",
                error_message="Platform adapter is unavailable in the current environment.",
            )

        write_runtime_status(self.home, gateway_state="running", exit_reason=None)
        self._next_cron_tick_at = None

    async def _shutdown_runtime(self, *, exit_reason: str = "stopped") -> None:
        for platform, adapter in list(self.adapters.items()):
            try:
                await adapter.stop()
            except Exception as exc:
                logger.debug("Failed to stop adapter %s: %s", platform.value, exc)
        self.adapters.clear()
        if self.gateway_config is not None:
            self.manager.save_config(self.gateway_config)
        self.manager.stop()
        write_runtime_status(self.home, gateway_state="stopped", exit_reason=exit_reason)
        remove_pid_file(self.home)

    async def _tick_cron_if_due(self, *, force: bool = False) -> list[dict[str, Any]]:
        loop = asyncio.get_running_loop()
        now = loop.time()
        if not force and self._next_cron_tick_at is not None and now < self._next_cron_tick_at:
            return []
        cron = CronManager(home=self.home)
        results = await asyncio.to_thread(cron.tick_sync)
        self._next_cron_tick_at = now + self.cron_interval
        if results:
            return await self._deliver_cron_results(results)
        return results

    async def _poll_platforms(self, *, timeout: float) -> list[MessageEvent]:
        events: list[MessageEvent] = []
        for platform, adapter in list(self.adapters.items()):
            try:
                polled = await adapter.poll_once(timeout=timeout)
                if polled:
                    write_runtime_status(
                        self.home,
                        platform=platform.value,
                        platform_state="active",
                        error_code=None,
                        error_message=None,
                    )
                for event in polled:
                    await self._handle_message(event)
                events.extend(polled)
            except Exception as exc:
                write_runtime_status(
                    self.home,
                    platform=platform.value,
                    platform_state="error",
                    error_code="poll_failed",
                    error_message=str(exc),
                )
        return events

    async def _tick_once(self, *, force_cron: bool = False, poll_timeout: float = 0.0) -> dict[str, Any]:
        cron_results = await self._tick_cron_if_due(force=force_cron)
        events = await self._poll_platforms(timeout=poll_timeout)
        configured = self.gateway_config.get_connected_platforms() if self.gateway_config else []
        return {
            "cron_jobs_run": len(cron_results),
            "results": cron_results,
            "messages_processed": len(events),
            "configured_platforms": [platform.value for platform in configured],
        }

    async def run(self, *, once: bool = False) -> dict[str, Any]:
        await self._start_runtime()
        try:
            result = await self._tick_once(
                force_cron=True,
                poll_timeout=0.0 if once else min(self.poll_interval, 2.0),
            )
            self.loop_count = 1
            if once:
                return result

            while not self.stop_event.is_set():
                if self._desired_state() == "stopped":
                    break
                if self.max_loops is not None and self.loop_count >= self.max_loops:
                    break
                result = await self._tick_once(
                    force_cron=False,
                    poll_timeout=min(self.poll_interval, 2.0),
                )
                self.loop_count += 1
                if self.stop_event.is_set() or self._desired_state() == "stopped":
                    break
                if not self.adapters:
                    try:
                        await asyncio.wait_for(self.stop_event.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
            return result
        finally:
            await self._shutdown_runtime(
                exit_reason="interrupted" if self.stop_event.is_set() else "stopped",
            )

    def run_sync(self, *, once: bool = False) -> dict[str, Any]:
        return asyncio.run(self.run(once=once))


def run_gateway(
    *,
    home: Path | None = None,
    once: bool = False,
    poll_interval: float = 2.0,
    max_loops: int | None = None,
) -> dict[str, Any]:
    runner = GatewayRunner(home=home, poll_interval=poll_interval, max_loops=max_loops)
    return runner.run_sync(once=once)
