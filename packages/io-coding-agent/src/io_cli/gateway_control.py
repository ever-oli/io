"""Shared gateway control operations for slash handlers and MCP."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from io_agent import resolve_runtime

from .config import ensure_io_home, load_config, load_env
from .gateway import GatewayManager
from .gateway_models import HomeChannel, Platform, PlatformConfig
from .gateway_platforms import BasePlatformAdapter, SendResult
from .gateway_runtime import gateway_runtime_snapshot
from .gateway_session import (
    SessionContext,
    SessionEntry,
    SessionSource,
    build_session_context,
    build_session_context_prompt,
)
from .main import run_prompt
from .session import SessionManager
from .toolsets import enabled_toolsets_for_platform


@dataclass(slots=True)
class ResolvedGatewayTarget:
    platform: Platform
    chat_id: str
    thread_id: str | None
    metadata: dict[str, Any]
    source: SessionSource | None
    session_id: str | None


_THREAD_CAPABLE_PLATFORMS = {
    Platform.DISCORD,
    Platform.MATTERMOST,
    Platform.MATRIX,
    Platform.SLACK,
    Platform.TELEGRAM,
}


class GatewayControlService:
    def __init__(
        self,
        *,
        home: Path | None = None,
        adapter_overrides: dict[Platform, BasePlatformAdapter] | None = None,
    ) -> None:
        self.home = ensure_io_home(home)
        self.manager = GatewayManager(home=self.home)
        self.adapter_overrides = adapter_overrides or {}

    def _gateway_entries(self) -> list[SessionEntry]:
        return self.manager.session_store().list_entries()

    def _find_session_entry(self, session_id: str) -> SessionEntry | None:
        wanted = str(session_id or "").strip()
        if not wanted:
            return None
        for entry in self._gateway_entries():
            if entry.session_id == wanted:
                return entry
        return None

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

    def _record_session_usage(self, context: SessionContext, *, result: Any) -> None:
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

    def _last_user_message_content(self, session_file: Path) -> str | None:
        session = SessionManager.open(session_file)
        for entry in reversed(session.get_branch()):
            if entry.get("type") != "message":
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "") != "user":
                continue
            text = str(message.get("content") or "").strip()
            if text:
                return text
        return None

    def _undo_last_exchange(self, session_file: Path) -> tuple[bool, str]:
        session = SessionManager.open(session_file)
        branch = session.get_branch()
        message_entries = [
            entry
            for entry in branch
            if entry.get("type") == "message" and isinstance(entry.get("message"), dict)
        ]
        if not message_entries:
            return False, "Nothing to undo in this session yet."

        last_assistant_idx = -1
        for idx in range(len(message_entries) - 1, -1, -1):
            role = str(message_entries[idx]["message"].get("role") or "")
            if role == "assistant":
                last_assistant_idx = idx
                break
        if last_assistant_idx <= 0:
            return False, "No completed user/assistant exchange to undo yet."

        user_idx = -1
        for idx in range(last_assistant_idx - 1, -1, -1):
            role = str(message_entries[idx]["message"].get("role") or "")
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

    def _resolve_runtime_state(self) -> tuple[dict[str, Any], Any]:
        config = load_config(self.home)
        env = {**load_env(self.home), **os.environ}
        runtime = resolve_runtime(config=config, home=self.home, env=env)
        return config, runtime

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

    def _adapter_capabilities(self, platform: Platform) -> dict[str, bool]:
        from .gateway_platforms.base import BasePlatformAdapter as _BaseAdapter
        from .gateway_runner import ADAPTER_TYPES

        adapter_cls = ADAPTER_TYPES.get(platform)
        if adapter_cls is None:
            return {"send": False, "edit": False, "typing": False, "threads": False}
        edit_supported = adapter_cls.edit_message is not _BaseAdapter.edit_message
        typing_supported = adapter_cls.send_typing is not _BaseAdapter.send_typing
        send_supported = platform not in {Platform.API_SERVER}
        return {
            "send": send_supported,
            "edit": edit_supported,
            "typing": typing_supported,
            "threads": platform in _THREAD_CAPABLE_PLATFORMS,
        }

    def channels_list(self) -> dict[str, Any]:
        config = self.manager.load_config()
        runtime = gateway_runtime_snapshot(self.home)
        runtime_platforms = runtime.get("platforms", {}) if isinstance(runtime.get("platforms"), dict) else {}
        rows = []
        for platform, platform_config in config.platforms.items():
            capabilities = self._adapter_capabilities(platform)
            runtime_state = None
            if isinstance(runtime_platforms, dict):
                runtime_state = runtime_platforms.get(platform.value, {}).get("state")
            row = {
                "platform": platform.value,
                "enabled": platform_config.enabled,
                "home_channel": platform_config.home_channel.to_dict() if platform_config.home_channel else None,
                "runtime_state": runtime_state,
                "capabilities": capabilities,
            }
            rows.append(row)
        return {"success": True, "channels": rows}

    def _build_adapter(self, platform: Platform) -> tuple[BasePlatformAdapter, bool]:
        override = self.adapter_overrides.get(platform)
        if override is not None:
            return override, False
        from .gateway_runner import ADAPTER_TYPES

        config = self.manager.load_config()
        platform_config = config.platforms.get(platform)
        if platform_config is None or not platform_config.enabled:
            raise RuntimeError(f"Platform '{platform.value}' is not enabled in the gateway config.")
        adapter_cls = ADAPTER_TYPES.get(platform)
        if adapter_cls is None:
            raise RuntimeError(f"Adapter missing for platform '{platform.value}'.")
        return adapter_cls(platform_config), True

    def _resolve_target(
        self,
        *,
        session_id: str | None = None,
        platform: str | None = None,
        chat_id: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ResolvedGatewayTarget:
        merged_metadata = dict(metadata or {})
        resolved_platform = str(platform or "").strip().lower() or None
        resolved_chat_id = str(chat_id or "").strip() or None
        resolved_thread_id = str(thread_id or "").strip() or None
        source: SessionSource | None = None
        resolved_session_id = str(session_id or "").strip() or None
        if resolved_session_id:
            entry = self._find_session_entry(resolved_session_id)
            if entry and entry.origin:
                source = entry.origin
                resolved_platform = resolved_platform or source.platform.value
                resolved_chat_id = resolved_chat_id or source.chat_id
                resolved_thread_id = resolved_thread_id or source.thread_id
                if source.chat_topic:
                    merged_metadata.setdefault("chat_topic", source.chat_topic)
                if source.chat_id_alt:
                    merged_metadata.setdefault("chat_id_alt", source.chat_id_alt)
                if source.user_id_alt:
                    merged_metadata.setdefault("user_id_alt", source.user_id_alt)
        if resolved_platform is None:
            raise RuntimeError("platform is required when no session origin is available.")
        platform_enum = Platform(resolved_platform)
        if resolved_chat_id is None:
            home_channel = self.manager.load_config().get_home_channel(platform_enum)
            if home_channel is None:
                raise RuntimeError("chat_id is required when no home channel is configured.")
            resolved_chat_id = home_channel.chat_id
        if resolved_thread_id:
            merged_metadata.setdefault("thread_id", resolved_thread_id)
        return ResolvedGatewayTarget(
            platform=platform_enum,
            chat_id=resolved_chat_id,
            thread_id=resolved_thread_id,
            metadata=merged_metadata,
            source=source,
            session_id=resolved_session_id,
        )

    async def _send_via_adapter(
        self,
        target: ResolvedGatewayTarget,
        content: str,
        *,
        reply_to: str | None = None,
    ) -> SendResult:
        adapter, should_cleanup = self._build_adapter(target.platform)
        connected = False
        try:
            result = await adapter.send(
                target.chat_id,
                content,
                reply_to=reply_to,
                metadata=target.metadata or None,
            )
            if not result.success and str(result.error or "").lower() == "not connected" and should_cleanup:
                await adapter.connect()
                connected = True
                result = await adapter.send(
                    target.chat_id,
                    content,
                    reply_to=reply_to,
                    metadata=target.metadata or None,
                )
            return result
        finally:
            if should_cleanup and connected:
                await adapter.disconnect()

    async def _edit_via_adapter(
        self,
        target: ResolvedGatewayTarget,
        *,
        message_id: str,
        content: str,
    ) -> SendResult:
        adapter, should_cleanup = self._build_adapter(target.platform)
        connected = False
        try:
            result = await adapter.edit_message(target.chat_id, message_id, content)
            if not result.success and str(result.error or "").lower() == "not connected" and should_cleanup:
                await adapter.connect()
                connected = True
                result = await adapter.edit_message(target.chat_id, message_id, content)
            return result
        finally:
            if should_cleanup and connected:
                await adapter.disconnect()

    async def _typing_via_adapter(self, target: ResolvedGatewayTarget) -> None:
        adapter, should_cleanup = self._build_adapter(target.platform)
        connected = False
        try:
            if should_cleanup:
                await adapter.connect()
                connected = True
            await adapter.send_typing(target.chat_id, metadata=target.metadata or None)
        finally:
            if should_cleanup and connected:
                await adapter.disconnect()

    async def messages_send(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        content: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = self._resolve_target(
            session_id=session_id,
            platform=platform,
            chat_id=chat_id,
            thread_id=thread_id,
            metadata=metadata,
        )
        result = await self._send_via_adapter(target, content, reply_to=reply_to)
        return {
            "success": result.success,
            "platform": target.platform.value,
            "chat_id": target.chat_id,
            "thread_id": target.thread_id,
            "message_id": result.message_id,
            "error": result.error,
        }

    async def messages_edit(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        message_id: str,
        content: str,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = self._resolve_target(
            session_id=session_id,
            platform=platform,
            chat_id=chat_id,
            thread_id=thread_id,
            metadata=metadata,
        )
        result = await self._edit_via_adapter(target, message_id=message_id, content=content)
        return {
            "success": result.success,
            "platform": target.platform.value,
            "chat_id": target.chat_id,
            "message_id": result.message_id,
            "error": result.error,
        }

    async def messages_typing(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = self._resolve_target(
            session_id=session_id,
            platform=platform,
            chat_id=chat_id,
            thread_id=thread_id,
            metadata=metadata,
        )
        await self._typing_via_adapter(target)
        return {
            "success": True,
            "platform": target.platform.value,
            "chat_id": target.chat_id,
            "thread_id": target.thread_id,
        }

    def channel_set_home(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        name: str | None = None,
    ) -> dict[str, Any]:
        target = self._resolve_target(
            session_id=session_id,
            platform=platform,
            chat_id=chat_id,
        )
        config = self.manager.load_config()
        platform_config = config.platforms.get(target.platform) or PlatformConfig(enabled=True)
        platform_config.enabled = True
        platform_config.home_channel = HomeChannel(
            platform=target.platform,
            chat_id=target.chat_id,
            name=str(name or "Home"),
        )
        config.platforms[target.platform] = platform_config
        self.manager.save_config(config)
        return {
            "success": True,
            "platform": target.platform.value,
            "home_channel": platform_config.home_channel.to_dict(),
        }

    def _resolve_context(
        self,
        *,
        action: str,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        chat_type: str | None = None,
        chat_name: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        thread_id: str | None = None,
    ) -> tuple[SessionSource, SessionContext, Path]:
        config = self.manager.load_config()
        entry = self._find_session_entry(str(session_id or "").strip()) if session_id else None
        if entry and entry.origin:
            source = entry.origin
            if action == "new":
                context = self.manager.build_session_context(source, force_new=True)
            else:
                context = build_session_context(source, config, entry)
        else:
            if not platform or not chat_id:
                raise RuntimeError("session_id or explicit platform/chat_id is required.")
            source = SessionSource(
                platform=Platform(str(platform).strip().lower()),
                chat_id=str(chat_id),
                chat_name=str(chat_name or "") or None,
                chat_type=str(chat_type or "dm"),
                user_id=str(user_id or "") or None,
                user_name=str(user_name or "") or None,
                thread_id=str(thread_id or "") or None,
            )
            context = self.manager.build_session_context(source, force_new=action == "new")
        session_file = self._ensure_gateway_session_file(context, self._resolve_gateway_cwd())
        return source, context, session_file

    async def conversation_control(
        self,
        *,
        action: str,
        session_id: str | None = None,
        platform: str | None = None,
        chat_id: str | None = None,
        chat_type: str | None = None,
        chat_name: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        normalized = str(action or "").strip().lower()
        if normalized not in {"new", "retry", "undo", "status", "usage"}:
            raise RuntimeError(f"Unsupported conversation action: {action}")
        source, context, session_file = self._resolve_context(
            action=normalized,
            session_id=session_id,
            platform=platform,
            chat_id=chat_id,
            chat_type=chat_type,
            chat_name=chat_name,
            user_id=user_id,
            user_name=user_name,
            thread_id=thread_id,
        )
        if normalized == "new":
            return {
                "success": True,
                "action": "new",
                "session_id": context.session_id,
                "message": f"Started a new session for this chat.\nSession ID: {context.session_id}",
            }
        if normalized == "status":
            return {
                "success": True,
                "action": "status",
                "session_id": context.session_id,
                "message": self._format_session_status(source=source, context=context, session_file=session_file),
            }
        if normalized == "usage":
            return {
                "success": True,
                "action": "usage",
                "session_id": context.session_id,
                "message": self._format_usage_status(context=context),
            }
        if normalized == "undo":
            ok, message = self._undo_last_exchange(session_file)
            return {
                "success": ok,
                "action": "undo",
                "session_id": context.session_id,
                "message": message,
            }

        prompt = self._last_user_message_content(session_file)
        if not prompt:
            return {
                "success": False,
                "action": "retry",
                "session_id": context.session_id,
                "message": "No previous user message available to retry.",
            }
        runtime_config = load_config(self.home)
        redact_pii = bool(runtime_config.get("privacy", {}).get("redact_pii", False))
        system_prompt_suffix = build_session_context_prompt(context, redact_pii=redact_pii)
        result = await run_prompt(
            prompt,
            cwd=self._resolve_gateway_cwd(),
            home=self.home,
            session_path=session_file,
            toolsets=self._resolve_toolsets(source.platform),
            system_prompt_suffix=system_prompt_suffix,
            env_overrides=self._build_session_env(context, session_file),
        )
        self._record_session_usage(context, result=result)
        response = result.text.strip() or "(no response)"
        return {
            "success": True,
            "action": "retry",
            "session_id": context.session_id,
            "message": f"Retrying the last user message...\n\n{response}",
        }


def format_gateway_control_output(payload: dict[str, Any]) -> str:
    if payload.get("message"):
        return str(payload["message"])
    if "channels" in payload:
        channels = payload.get("channels", [])
        if not channels:
            return "No gateway channels are configured."
        lines = ["Gateway channels:"]
        for item in channels:
            if not isinstance(item, dict):
                continue
            capabilities = item.get("capabilities", {})
            caps = ", ".join(
                name for name, enabled in capabilities.items() if enabled
            ) or "none"
            home_channel = item.get("home_channel")
            home_label = home_channel.get("chat_id") if isinstance(home_channel, dict) else "-"
            runtime_state = item.get("runtime_state") or "inactive"
            lines.append(f"- {item.get('platform')}: state={runtime_state}, home={home_label}, capabilities={caps}")
        return "\n".join(lines)
    if payload.get("success") and payload.get("platform") and payload.get("home_channel"):
        return f"Home channel for {payload['platform']} set to {payload['home_channel']['chat_id']}."
    return str(payload)
