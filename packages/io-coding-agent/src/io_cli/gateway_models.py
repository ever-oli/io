"""IO-style gateway config models for IO."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return bool(value)


def _normalize_unauthorized_dm_behavior(value: Any, default: str = "pair") -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"pair", "ignore"}:
            return normalized
    return default


class Platform(Enum):
    LOCAL = "local"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    SIGNAL = "signal"
    MATTERMOST = "mattermost"
    MATRIX = "matrix"
    HOMEASSISTANT = "homeassistant"
    EMAIL = "email"
    SMS = "sms"
    DINGTALK = "dingtalk"
    API_SERVER = "api-server"


@dataclass(slots=True)
class HomeChannel:
    platform: Platform
    chat_id: str
    name: str = "Home"

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform.value,
            "chat_id": self.chat_id,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HomeChannel":
        return cls(
            platform=Platform(str(data["platform"])),
            chat_id=str(data["chat_id"]),
            name=str(data.get("name", "Home")),
        )


@dataclass(slots=True)
class SessionResetPolicy:
    mode: str = "both"
    at_hour: int = 4
    idle_minutes: int = 1440

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "at_hour": self.at_hour,
            "idle_minutes": self.idle_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionResetPolicy":
        return cls(
            mode=str(data.get("mode") or "both"),
            at_hour=int(data.get("at_hour") if data.get("at_hour") is not None else 4),
            idle_minutes=int(
                data.get("idle_minutes") if data.get("idle_minutes") is not None else 1440
            ),
        )


@dataclass(slots=True)
class PlatformConfig:
    enabled: bool = False
    token: str | None = None
    api_key: str | None = None
    home_channel: HomeChannel | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "enabled": self.enabled,
            "extra": dict(self.extra),
        }
        if self.token:
            payload["token"] = self.token
        if self.api_key:
            payload["api_key"] = self.api_key
        if self.home_channel:
            payload["home_channel"] = self.home_channel.to_dict()
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlatformConfig":
        home_channel = None
        if isinstance(data.get("home_channel"), dict):
            home_channel = HomeChannel.from_dict(data["home_channel"])
        extra = data.get("extra", {})
        return cls(
            enabled=bool(data.get("enabled", False)),
            token=data.get("token"),
            api_key=data.get("api_key"),
            home_channel=home_channel,
            extra=extra if isinstance(extra, dict) else {},
        )


@dataclass(slots=True)
class StreamingConfig:
    enabled: bool = False
    transport: str = "edit"
    edit_interval: float = 0.3
    buffer_threshold: int = 40
    cursor: str = " Φ"

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "transport": self.transport,
            "edit_interval": self.edit_interval,
            "buffer_threshold": self.buffer_threshold,
            "cursor": self.cursor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StreamingConfig":
        return cls(
            enabled=bool(data.get("enabled", False)),
            transport=str(data.get("transport", "edit")),
            edit_interval=float(data.get("edit_interval", 0.3)),
            buffer_threshold=int(data.get("buffer_threshold", 40)),
            cursor=str(data.get("cursor", " Φ")),
        )


@dataclass(slots=True)
class GatewayConfig:
    platforms: dict[Platform, PlatformConfig] = field(default_factory=dict)
    default_reset_policy: SessionResetPolicy = field(default_factory=SessionResetPolicy)
    reset_by_type: dict[str, SessionResetPolicy] = field(default_factory=dict)
    reset_by_platform: dict[Platform, SessionResetPolicy] = field(default_factory=dict)
    reset_triggers: list[str] = field(default_factory=lambda: ["/new", "/reset"])
    quick_commands: dict[str, Any] = field(default_factory=dict)
    sessions_dir: Path = field(default_factory=lambda: Path.home() / ".io" / "gateway" / "sessions")
    always_log_local: bool = True
    stt_enabled: bool = True
    group_sessions_per_user: bool = True
    unauthorized_dm_behavior: str = "pair"
    streaming: StreamingConfig = field(default_factory=StreamingConfig)

    def get_connected_platforms(self) -> list[Platform]:
        # Until the live gateway runners are wired in, "connected" tracks the
        # user's enabled platform intent rather than verified remote auth state.
        return [platform for platform, config in self.platforms.items() if config.enabled]

    def get_home_channel(self, platform: Platform) -> HomeChannel | None:
        config = self.platforms.get(platform)
        return config.home_channel if config else None

    def get_reset_policy(
        self,
        platform: Platform | None = None,
        session_type: str | None = None,
    ) -> SessionResetPolicy:
        if platform and platform in self.reset_by_platform:
            return self.reset_by_platform[platform]
        if session_type and session_type in self.reset_by_type:
            return self.reset_by_type[session_type]
        return self.default_reset_policy

    def get_unauthorized_dm_behavior(self, platform: Platform | None = None) -> str:
        if platform:
            config = self.platforms.get(platform)
            if config and "unauthorized_dm_behavior" in config.extra:
                return _normalize_unauthorized_dm_behavior(
                    config.extra.get("unauthorized_dm_behavior"),
                    self.unauthorized_dm_behavior,
                )
        return self.unauthorized_dm_behavior

    def to_dict(self) -> dict[str, Any]:
        return {
            "platforms": {platform.value: config.to_dict() for platform, config in self.platforms.items()},
            "default_reset_policy": self.default_reset_policy.to_dict(),
            "reset_by_type": {name: policy.to_dict() for name, policy in self.reset_by_type.items()},
            "reset_by_platform": {
                platform.value: policy.to_dict()
                for platform, policy in self.reset_by_platform.items()
            },
            "reset_triggers": list(self.reset_triggers),
            "quick_commands": dict(self.quick_commands),
            "sessions_dir": str(self.sessions_dir),
            "always_log_local": self.always_log_local,
            "stt_enabled": self.stt_enabled,
            "group_sessions_per_user": self.group_sessions_per_user,
            "unauthorized_dm_behavior": self.unauthorized_dm_behavior,
            "streaming": self.streaming.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, default_sessions_dir: Path | None = None) -> "GatewayConfig":
        platforms: dict[Platform, PlatformConfig] = {}
        for platform_name, platform_data in (data.get("platforms", {}) or {}).items():
            try:
                platform = Platform(str(platform_name))
            except ValueError:
                continue
            if isinstance(platform_data, dict):
                platforms[platform] = PlatformConfig.from_dict(platform_data)

        reset_by_type: dict[str, SessionResetPolicy] = {}
        for type_name, policy_data in (data.get("reset_by_type", {}) or {}).items():
            if isinstance(policy_data, dict):
                reset_by_type[str(type_name)] = SessionResetPolicy.from_dict(policy_data)

        reset_by_platform: dict[Platform, SessionResetPolicy] = {}
        for platform_name, policy_data in (data.get("reset_by_platform", {}) or {}).items():
            try:
                platform = Platform(str(platform_name))
            except ValueError:
                continue
            if isinstance(policy_data, dict):
                reset_by_platform[platform] = SessionResetPolicy.from_dict(policy_data)

        sessions_dir = default_sessions_dir or (Path.home() / ".io" / "gateway" / "sessions")
        if data.get("sessions_dir"):
            sessions_dir = Path(str(data["sessions_dir"]))

        quick_commands = data.get("quick_commands", {})
        if not isinstance(quick_commands, dict):
            quick_commands = {}

        return cls(
            platforms=platforms,
            default_reset_policy=SessionResetPolicy.from_dict(
                data.get("default_reset_policy", {}) if isinstance(data.get("default_reset_policy"), dict) else {}
            ),
            reset_by_type=reset_by_type,
            reset_by_platform=reset_by_platform,
            reset_triggers=[
                str(item).strip()
                for item in data.get("reset_triggers", ["/new", "/reset"])
                if str(item).strip()
            ],
            quick_commands=quick_commands,
            sessions_dir=sessions_dir,
            always_log_local=_coerce_bool(data.get("always_log_local"), True),
            stt_enabled=_coerce_bool(data.get("stt_enabled"), True),
            group_sessions_per_user=_coerce_bool(data.get("group_sessions_per_user"), True),
            unauthorized_dm_behavior=_normalize_unauthorized_dm_behavior(
                data.get("unauthorized_dm_behavior"),
                "pair",
            ),
            streaming=StreamingConfig.from_dict(
                data.get("streaming", {}) if isinstance(data.get("streaming"), dict) else {}
            ),
        )


def default_gateway_config(home: Path) -> GatewayConfig:
    return GatewayConfig(sessions_dir=home / "gateway" / "sessions")
