"""Gateway management surface."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import atomic_write_json, ensure_io_home, load_env
from .gateway_models import (
    GatewayConfig,
    HomeChannel,
    Platform,
    PlatformConfig,
    default_gateway_config,
)
from .gateway_runtime import gateway_runtime_snapshot
from .gateway_session import GatewaySessionStore, SessionContext, SessionSource, build_session_context


KNOWN_GATEWAY_PLATFORMS = tuple(
    platform.value for platform in Platform if platform is not Platform.LOCAL
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _redact_gateway_config(config: GatewayConfig) -> dict[str, Any]:
    payload = config.to_dict()
    platforms = payload.get("platforms", {})
    if isinstance(platforms, dict):
        for platform_payload in platforms.values():
            if not isinstance(platform_payload, dict):
                continue
            if platform_payload.get("token"):
                platform_payload["token"] = "***"
            if platform_payload.get("api_key"):
                platform_payload["api_key"] = "***"
    return payload


def _first_env(env: dict[str, str], *names: str) -> str:
    for name in names:
        value = str(env.get(name, "") or "").strip()
        if value:
            return value
    return ""


def _apply_platform_env_overrides(config: GatewayConfig, *, home: Path) -> GatewayConfig:
    env = {**load_env(home), **os.environ}
    specs = {
        Platform.TELEGRAM: {
            "token": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_TOKEN"),
            "home_channel": ("TELEGRAM_HOME_CHANNEL",),
            "extra": {
                "webhook_url": ("TELEGRAM_WEBHOOK_URL",),
                "webhook_port": ("TELEGRAM_WEBHOOK_PORT",),
                "webhook_secret": ("TELEGRAM_WEBHOOK_SECRET",),
                "webhook_host": ("TELEGRAM_WEBHOOK_HOST",),
            },
        },
        Platform.SLACK: {
            "token": ("SLACK_BOT_TOKEN",),
            "home_channel": ("SLACK_HOME_CHANNEL",),
            "extra": {
                "app_token": ("SLACK_APP_TOKEN",),
                "tokens_file": ("SLACK_TOKENS_FILE",),
            },
        },
    }
    for platform, spec in specs.items():
        token_value = _first_env(env, *spec.get("token", ()))
        home_channel = _first_env(env, *spec.get("home_channel", ()))
        extra_values = {
            key: _first_env(env, *names)
            for key, names in spec.get("extra", {}).items()
        }
        if not token_value and not home_channel and not any(extra_values.values()):
            continue
        current = config.platforms.get(platform) or PlatformConfig()
        current.enabled = True
        if token_value:
            current.token = token_value
        if home_channel:
            current.home_channel = HomeChannel(platform=platform, chat_id=home_channel, name="Home")
        for key, value in extra_values.items():
            if value:
                current.extra[key] = value
        config.platforms[platform] = current
    return config


@dataclass(slots=True)
class GatewayManager:
    home: Path | None = None

    def __post_init__(self) -> None:
        self.home = ensure_io_home(self.home)

    @property
    def gateway_dir(self) -> Path:
        assert self.home is not None
        return self.home / "gateway"

    @property
    def state_path(self) -> Path:
        return self.gateway_dir / "state.json"

    @property
    def config_path(self) -> Path:
        return self.gateway_dir / "config.json"

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "installed_scopes": [],
                "desired_state": "stopped",
                "runtime_available": False,
                "updated_at": None,
            }
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save_state(self, payload: dict[str, Any]) -> None:
        self.gateway_dir.mkdir(parents=True, exist_ok=True)
        payload["updated_at"] = _now()
        atomic_write_json(self.state_path, payload, indent=2, sort_keys=True, chmod=0o600)

    def load_config(self) -> GatewayConfig:
        default = default_gateway_config(self.home)
        if not self.config_path.exists():
            return _apply_platform_env_overrides(default, home=self.home)
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return _apply_platform_env_overrides(default, home=self.home)
        if not isinstance(payload, dict):
            return _apply_platform_env_overrides(default, home=self.home)
        return _apply_platform_env_overrides(
            GatewayConfig.from_dict(payload, default_sessions_dir=default.sessions_dir),
            home=self.home,
        )

    def save_config(self, config: GatewayConfig) -> None:
        self.gateway_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(self.config_path, config.to_dict(), indent=2, sort_keys=True, chmod=0o600)

    def session_store(self) -> GatewaySessionStore:
        config = self.load_config()
        return GatewaySessionStore(config.sessions_dir, config)

    def configure(
        self,
        *,
        platforms: list[str] | None = None,
        home_channel: str | None = None,
        token: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        config = self.load_config()
        if platforms is not None:
            invalid = sorted({item for item in platforms if item not in KNOWN_GATEWAY_PLATFORMS})
            if invalid:
                raise KeyError(", ".join(invalid))
            for platform_name in platforms:
                platform = Platform(platform_name)
                current = config.platforms.get(platform) or PlatformConfig()
                current.enabled = True
                config.platforms[platform] = current
        if home_channel is not None:
            target_platforms = platforms or [platform.value for platform in config.platforms if config.platforms[platform].enabled]
            for platform_name in target_platforms:
                platform = Platform(platform_name)
                current = config.platforms.get(platform) or PlatformConfig(enabled=True)
                current.enabled = True
                current.home_channel = HomeChannel(platform=platform, chat_id=home_channel, name="Home")
                config.platforms[platform] = current
        if token is not None or api_key is not None:
            target_platforms = platforms or [platform.value for platform in config.platforms]
            for platform_name in target_platforms:
                platform = Platform(platform_name)
                current = config.platforms.get(platform) or PlatformConfig(enabled=True)
                current.enabled = True
                if token is not None:
                    current.token = token.strip() or None
                if api_key is not None:
                    current.api_key = api_key.strip() or None
                config.platforms[platform] = current
        self.save_config(config)
        return self.status()

    def install(self, *, scope: str = "user") -> dict[str, Any]:
        state = self.load_state()
        scopes = list(state.get("installed_scopes", []))
        if scope not in scopes:
            scopes.append(scope)
        state["installed_scopes"] = sorted(scopes)
        self.save_state(state)
        return self.status()

    def uninstall(self, *, scope: str | None = None) -> dict[str, Any]:
        state = self.load_state()
        scopes = list(state.get("installed_scopes", []))
        if scope is None:
            scopes = []
        else:
            scopes = [item for item in scopes if item != scope]
        state["installed_scopes"] = scopes
        if not scopes:
            state["desired_state"] = "stopped"
        self.save_state(state)
        return self.status()

    def start(self) -> dict[str, Any]:
        state = self.load_state()
        state["desired_state"] = "running"
        self.save_state(state)
        return self.status()

    def stop(self) -> dict[str, Any]:
        state = self.load_state()
        state["desired_state"] = "stopped"
        self.save_state(state)
        return self.status()

    def build_session_context(self, source: SessionSource, *, force_new: bool = False) -> SessionContext:
        config = self.load_config()
        store = GatewaySessionStore(config.sessions_dir, config)
        entry = store.get_or_create_session(source, force_new=force_new)
        return build_session_context(source, config, entry)

    def status(self) -> dict[str, Any]:
        state = self.load_state()
        config = self.load_config()
        runtime = gateway_runtime_snapshot(self.home)
        connected_platforms = config.get_connected_platforms()
        home_channels = {
            platform.value: channel.to_dict()
            for platform in connected_platforms
            if (channel := config.get_home_channel(platform)) is not None
        }
        primary_home_channel = None
        if home_channels:
            primary_home_channel = next(iter(home_channels.values())).get("chat_id")
        return {
            **state,
            "configured_platforms": [platform.value for platform in connected_platforms],
            "home_channel": primary_home_channel,
            "home_channels": home_channels,
            "gateway_config": _redact_gateway_config(config),
            "known_platforms": list(KNOWN_GATEWAY_PLATFORMS),
            "runtime_available": bool(runtime["running"]),
            "runtime": runtime,
            "implemented": True,
            "message": "Gateway runtime uses the shared IO multi-platform adapter stack.",
        }
