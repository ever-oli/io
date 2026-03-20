"""IO-style gateway session context for IO."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .gateway_models import GatewayConfig, HomeChannel, Platform


_PHONE_RE = re.compile(r"^\+?\d[\d\-\s]{6,}$")
_PII_SAFE_PLATFORMS = frozenset({Platform.WHATSAPP, Platform.SIGNAL, Platform.TELEGRAM})


def _hash_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _hash_sender_id(value: str) -> str:
    return f"user_{_hash_id(value)}"


def _hash_chat_id(value: str) -> str:
    colon = value.find(":")
    if colon > 0:
        prefix = value[:colon]
        return f"{prefix}:{_hash_id(value[colon + 1:])}"
    return _hash_id(value)


def _looks_like_phone(value: str) -> bool:
    return bool(_PHONE_RE.match(value.strip()))


@dataclass(slots=True)
class SessionSource:
    platform: Platform
    chat_id: str
    chat_name: str | None = None
    chat_type: str = "dm"
    user_id: str | None = None
    user_name: str | None = None
    thread_id: str | None = None
    chat_topic: str | None = None
    user_id_alt: str | None = None
    chat_id_alt: str | None = None

    @property
    def description(self) -> str:
        if self.platform == Platform.LOCAL:
            return "CLI terminal"
        parts: list[str] = []
        if self.chat_type == "dm":
            parts.append(f"DM with {self.user_name or self.user_id or 'user'}")
        elif self.chat_type == "group":
            parts.append(f"group: {self.chat_name or self.chat_id}")
        elif self.chat_type == "channel":
            parts.append(f"channel: {self.chat_name or self.chat_id}")
        else:
            parts.append(self.chat_name or self.chat_id)
        if self.thread_id:
            parts.append(f"thread: {self.thread_id}")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "platform": self.platform.value,
            "chat_id": self.chat_id,
            "chat_name": self.chat_name,
            "chat_type": self.chat_type,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "thread_id": self.thread_id,
            "chat_topic": self.chat_topic,
        }
        if self.user_id_alt:
            payload["user_id_alt"] = self.user_id_alt
        if self.chat_id_alt:
            payload["chat_id_alt"] = self.chat_id_alt
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionSource":
        return cls(
            platform=Platform(str(data["platform"])),
            chat_id=str(data["chat_id"]),
            chat_name=data.get("chat_name"),
            chat_type=str(data.get("chat_type", "dm")),
            user_id=data.get("user_id"),
            user_name=data.get("user_name"),
            thread_id=data.get("thread_id"),
            chat_topic=data.get("chat_topic"),
            user_id_alt=data.get("user_id_alt"),
            chat_id_alt=data.get("chat_id_alt"),
        )

    @classmethod
    def local_cli(cls) -> "SessionSource":
        return cls(platform=Platform.LOCAL, chat_id="cli", chat_name="CLI terminal", chat_type="dm")


@dataclass(slots=True)
class SessionContext:
    source: SessionSource
    connected_platforms: list[Platform]
    home_channels: dict[Platform, HomeChannel]
    session_key: str = ""
    session_id: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "connected_platforms": [platform.value for platform in self.connected_platforms],
            "home_channels": {
                platform.value: channel.to_dict()
                for platform, channel in self.home_channels.items()
            },
            "session_key": self.session_key,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(slots=True)
class SessionEntry:
    session_key: str
    session_id: str
    created_at: datetime
    updated_at: datetime
    origin: SessionSource | None = None
    display_name: str | None = None
    platform: Platform | None = None
    chat_type: str = "dm"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    cost_status: str = "unknown"
    last_prompt_tokens: int = 0
    was_auto_reset: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "session_key": self.session_key,
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "display_name": self.display_name,
            "platform": self.platform.value if self.platform else None,
            "chat_type": self.chat_type,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "cost_status": self.cost_status,
            "last_prompt_tokens": self.last_prompt_tokens,
            "was_auto_reset": self.was_auto_reset,
        }
        if self.origin:
            payload["origin"] = self.origin.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionEntry":
        origin = SessionSource.from_dict(data["origin"]) if isinstance(data.get("origin"), dict) else None
        platform = None
        if data.get("platform"):
            try:
                platform = Platform(str(data["platform"]))
            except ValueError:
                platform = None
        return cls(
            session_key=str(data["session_key"]),
            session_id=str(data["session_id"]),
            created_at=datetime.fromisoformat(str(data["created_at"])),
            updated_at=datetime.fromisoformat(str(data["updated_at"])),
            origin=origin,
            display_name=data.get("display_name"),
            platform=platform,
            chat_type=str(data.get("chat_type", "dm")),
            input_tokens=int(data.get("input_tokens", 0)),
            output_tokens=int(data.get("output_tokens", 0)),
            cache_read_tokens=int(data.get("cache_read_tokens", 0)),
            cache_write_tokens=int(data.get("cache_write_tokens", 0)),
            total_tokens=int(data.get("total_tokens", 0)),
            estimated_cost_usd=float(data.get("estimated_cost_usd", 0.0)),
            cost_status=str(data.get("cost_status", "unknown")),
            last_prompt_tokens=int(data.get("last_prompt_tokens", 0)),
            was_auto_reset=bool(data.get("was_auto_reset", False)),
        )


def build_session_key(source: SessionSource, group_sessions_per_user: bool = True) -> str:
    platform = source.platform.value
    if source.chat_type == "dm":
        if source.chat_id:
            if source.thread_id:
                return f"agent:main:{platform}:dm:{source.chat_id}:{source.thread_id}"
            return f"agent:main:{platform}:dm:{source.chat_id}"
        if source.thread_id:
            return f"agent:main:{platform}:dm:{source.thread_id}"
        return f"agent:main:{platform}:dm"

    participant_id = source.user_id_alt or source.user_id
    key_parts = ["agent:main", platform, source.chat_type]
    if source.chat_id:
        key_parts.append(source.chat_id)
    if source.thread_id:
        key_parts.append(source.thread_id)
    if group_sessions_per_user and participant_id:
        key_parts.append(str(participant_id))
    return ":".join(key_parts)


def build_session_context(
    source: SessionSource,
    config: GatewayConfig,
    session_entry: SessionEntry | None = None,
) -> SessionContext:
    connected = config.get_connected_platforms()
    home_channels = {
        platform: channel
        for platform in connected
        if (channel := config.get_home_channel(platform)) is not None
    }
    context = SessionContext(
        source=source,
        connected_platforms=connected,
        home_channels=home_channels,
    )
    if session_entry is not None:
        context.session_key = session_entry.session_key
        context.session_id = session_entry.session_id
        context.created_at = session_entry.created_at
        context.updated_at = session_entry.updated_at
    return context


def build_session_context_prompt(context: SessionContext, *, redact_pii: bool = False) -> str:
    redact_pii = redact_pii and context.source.platform in _PII_SAFE_PLATFORMS
    lines = ["## Current Session Context", ""]

    platform_name = context.source.platform.value.title()
    if context.source.platform == Platform.LOCAL:
        lines.append(f"**Source:** {platform_name} (the machine running this agent)")
    else:
        source = context.source
        if redact_pii:
            user_label = source.user_name or (_hash_sender_id(source.user_id) if source.user_id else "user")
            chat_label = source.chat_name or _hash_chat_id(source.chat_id)
            if source.chat_type == "dm":
                description = f"DM with {user_label}"
            elif source.chat_type == "group":
                description = f"group: {chat_label}"
            elif source.chat_type == "channel":
                description = f"channel: {chat_label}"
            else:
                description = chat_label
        else:
            description = source.description
        lines.append(f"**Source:** {platform_name} ({description})")

    if context.source.chat_topic:
        lines.append(f"**Channel Topic:** {context.source.chat_topic}")

    if context.source.user_name:
        lines.append(f"**User:** {context.source.user_name}")
    elif context.source.user_id:
        user_id = context.source.user_id
        if redact_pii and _looks_like_phone(user_id):
            user_id = _hash_sender_id(user_id)
        lines.append(f"**User ID:** {user_id}")

    if context.source.platform == Platform.SLACK:
        lines.extend(
            [
                "",
                "**Platform notes:** You are running inside Slack. "
                "You cannot search channel history, manage channels, or list users.",
            ]
        )
    elif context.source.platform == Platform.DISCORD:
        lines.extend(
            [
                "",
                "**Platform notes:** You are running inside Discord. "
                "You cannot search server history, manage roles, or list members.",
            ]
        )

    connected_labels = ["local (files on this machine)"]
    for platform in context.connected_platforms:
        if platform != Platform.LOCAL:
            connected_labels.append(f"{platform.value}: Connected Φ")
    lines.append(f"**Connected Platforms:** {', '.join(connected_labels)}")

    if context.home_channels:
        lines.extend(["", "**Home Channels (default destinations):**"])
        for platform, channel in context.home_channels.items():
            channel_id = _hash_chat_id(channel.chat_id) if redact_pii else channel.chat_id
            lines.append(f"  - {platform.value}: {channel.name} (ID: {channel_id})")

    lines.extend(["", "**Delivery options for scheduled tasks:**"])
    if context.source.platform == Platform.LOCAL:
        lines.append("- `\"origin\"` -> Local output (saved to files)")
    else:
        origin_label = context.source.chat_name or (
            _hash_chat_id(context.source.chat_id) if redact_pii else context.source.chat_id
        )
        lines.append(f"- `\"origin\"` -> Back to this chat ({origin_label})")
    lines.append("- `\"local\"` -> Save to local files only (~/.io/cron/output/)")
    for platform, home in context.home_channels.items():
        lines.append(f"- `\"{platform.value}\"` -> Home channel ({home.name})")
    lines.extend(
        [
            "",
            "*For explicit targeting, use `\"platform:chat_id\"` if the user provides a specific chat ID.*",
        ]
    )
    return "\n".join(lines)


class GatewaySessionStore:
    def __init__(self, sessions_dir: Path, config: GatewayConfig) -> None:
        self.sessions_dir = sessions_dir
        self.config = config
        self.index_path = sessions_dir / "sessions.json"
        self._entries: dict[str, SessionEntry] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        if self.index_path.exists():
            try:
                payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                for key, entry_data in payload.items():
                    if isinstance(entry_data, dict):
                        try:
                            self._entries[key] = SessionEntry.from_dict(entry_data)
                        except Exception:
                            continue
        self._loaded = True

    def _save(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        payload = {key: entry.to_dict() for key, entry in self._entries.items()}
        fd, tmp_path = tempfile.mkstemp(dir=str(self.sessions_dir), suffix=".tmp", prefix=".sessions_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, self.index_path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def _generate_session_key(self, source: SessionSource) -> str:
        return build_session_key(
            source,
            group_sessions_per_user=getattr(self.config, "group_sessions_per_user", True),
        )

    def _should_reset(self, entry: SessionEntry, source: SessionSource) -> bool:
        policy = self.config.get_reset_policy(platform=source.platform, session_type=source.chat_type)
        if policy.mode == "none":
            return False
        now = datetime.now().astimezone()
        updated_at = entry.updated_at.astimezone()
        if policy.mode in {"idle", "both"}:
            if now > updated_at + timedelta(minutes=policy.idle_minutes):
                return True
        if policy.mode in {"daily", "both"}:
            today_reset = now.replace(hour=policy.at_hour, minute=0, second=0, microsecond=0)
            if now.hour < policy.at_hour:
                today_reset -= timedelta(days=1)
            if updated_at < today_reset:
                return True
        return False

    def get_or_create_session(self, source: SessionSource, *, force_new: bool = False) -> SessionEntry:
        self._ensure_loaded()
        session_key = self._generate_session_key(source)
        now = datetime.now().astimezone()
        if session_key in self._entries and not force_new:
            entry = self._entries[session_key]
            if not self._should_reset(entry, source):
                entry.updated_at = now
                self._save()
                return entry
            was_auto_reset = True
        else:
            was_auto_reset = False

        entry = SessionEntry(
            session_key=session_key,
            session_id=f"{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            created_at=now,
            updated_at=now,
            origin=source,
            display_name=source.chat_name,
            platform=source.platform,
            chat_type=source.chat_type,
            was_auto_reset=was_auto_reset,
        )
        self._entries[session_key] = entry
        self._save()
        return entry

    def get_entry(self, session_key: str) -> SessionEntry | None:
        self._ensure_loaded()
        return self._entries.get(session_key)

    def list_entries(self) -> list[SessionEntry]:
        self._ensure_loaded()
        return list(self._entries.values())

    def update_session(
        self,
        session_key: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        last_prompt_tokens: int | None = None,
        estimated_cost_usd: float | None = None,
        cost_status: str | None = None,
    ) -> None:
        self._ensure_loaded()
        entry = self._entries.get(session_key)
        if entry is None:
            return
        entry.updated_at = datetime.now().astimezone()
        entry.input_tokens += input_tokens
        entry.output_tokens += output_tokens
        entry.cache_read_tokens += cache_read_tokens
        entry.cache_write_tokens += cache_write_tokens
        if last_prompt_tokens is not None:
            entry.last_prompt_tokens = last_prompt_tokens
        if estimated_cost_usd is not None:
            entry.estimated_cost_usd += estimated_cost_usd
        if cost_status:
            entry.cost_status = cost_status
        entry.total_tokens = (
            entry.input_tokens
            + entry.output_tokens
            + entry.cache_read_tokens
            + entry.cache_write_tokens
        )
        self._save()
