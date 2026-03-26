"""Credential and provider metadata helpers for IO."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
NOUS_PORTAL_URL = "https://portal.nousresearch.com"
NOUS_INFERENCE_URL = "https://inference-api.nousresearch.com/v1"


@dataclass(slots=True, frozen=True)
class ProviderConfig:
    id: str
    label: str
    auth_type: str
    base_url: str = ""
    env_keys: tuple[str, ...] = ()
    base_url_env_key: str = ""
    api: str = "chat_completions"


PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "mock": ProviderConfig("mock", "Mock", "none", api="mock"),
    "openrouter": ProviderConfig(
        "openrouter",
        "OpenRouter",
        "api_key",
        base_url=OPENROUTER_BASE_URL,
        env_keys=("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
        base_url_env_key="OPENROUTER_BASE_URL",
    ),
    "openai": ProviderConfig(
        "openai",
        "OpenAI",
        "api_key",
        base_url=OPENAI_BASE_URL,
        env_keys=("OPENAI_API_KEY",),
        base_url_env_key="OPENAI_BASE_URL",
    ),
    "anthropic": ProviderConfig(
        "anthropic",
        "Anthropic",
        "api_key",
        base_url=ANTHROPIC_BASE_URL,
        env_keys=("ANTHROPIC_API_KEY", "ANTHROPIC_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"),
        base_url_env_key="ANTHROPIC_BASE_URL",
        api="anthropic_messages",
    ),
    "nous": ProviderConfig(
        "nous",
        "Nous Portal",
        "oauth_device_code",
        base_url=NOUS_INFERENCE_URL,
        env_keys=("NOUS_API_KEY",),
        base_url_env_key="NOUS_BASE_URL",
    ),
    "openai-codex": ProviderConfig(
        "openai-codex",
        "OpenAI Codex",
        "oauth_external",
        base_url="https://chatgpt.com/backend-api/codex",
        env_keys=("OPENAI_API_KEY",),
        base_url_env_key="OPENAI_CODEX_BASE_URL",
        api="codex_responses",
    ),
    "copilot": ProviderConfig(
        "copilot",
        "GitHub Copilot",
        "api_key",
        base_url="https://api.githubcopilot.com",
        env_keys=("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"),
        base_url_env_key="COPILOT_BASE_URL",
    ),
    "copilot-acp": ProviderConfig(
        "copilot-acp",
        "GitHub Copilot ACP",
        "external_process",
        base_url="acp://copilot",
        base_url_env_key="COPILOT_ACP_BASE_URL",
    ),
    "zai": ProviderConfig(
        "zai",
        "Z.AI / GLM",
        "api_key",
        base_url="https://api.z.ai/api/paas/v4",
        env_keys=("GLM_API_KEY", "ZAI_API_KEY", "Z_AI_API_KEY"),
        base_url_env_key="GLM_BASE_URL",
    ),
    "kimi-coding": ProviderConfig(
        "kimi-coding",
        "Kimi / Moonshot",
        "api_key",
        base_url="https://api.moonshot.ai/v1",
        env_keys=("KIMI_API_KEY",),
        base_url_env_key="KIMI_BASE_URL",
    ),
    "minimax": ProviderConfig(
        "minimax",
        "MiniMax",
        "api_key",
        base_url="https://api.minimax.io/v1",
        env_keys=("MINIMAX_API_KEY",),
        base_url_env_key="MINIMAX_BASE_URL",
    ),
    "minimax-cn": ProviderConfig(
        "minimax-cn",
        "MiniMax (China)",
        "api_key",
        base_url="https://api.minimaxi.com/v1",
        env_keys=("MINIMAX_CN_API_KEY",),
        base_url_env_key="MINIMAX_CN_BASE_URL",
    ),
    "deepseek": ProviderConfig(
        "deepseek",
        "DeepSeek",
        "api_key",
        base_url="https://api.deepseek.com/v1",
        env_keys=("DEEPSEEK_API_KEY",),
        base_url_env_key="DEEPSEEK_BASE_URL",
    ),
    "ai-gateway": ProviderConfig(
        "ai-gateway",
        "AI Gateway",
        "api_key",
        base_url="https://ai-gateway.vercel.sh/v1",
        env_keys=("AI_GATEWAY_API_KEY",),
        base_url_env_key="AI_GATEWAY_BASE_URL",
    ),
    "opencode-zen": ProviderConfig(
        "opencode-zen",
        "OpenCode Zen",
        "api_key",
        base_url="https://opencode.ai/zen/v1",
        env_keys=("OPENCODE_ZEN_API_KEY",),
        base_url_env_key="OPENCODE_ZEN_BASE_URL",
    ),
    "opencode-go": ProviderConfig(
        "opencode-go",
        "OpenCode Go",
        "api_key",
        base_url="https://opencode.ai/zen/go/v1",
        env_keys=("OPENCODE_GO_API_KEY",),
        base_url_env_key="OPENCODE_GO_BASE_URL",
    ),
    "kilocode": ProviderConfig(
        "kilocode",
        "Kilo Code",
        "api_key",
        base_url="https://api.kilo.ai/api/gateway",
        env_keys=("KILOCODE_API_KEY",),
        base_url_env_key="KILOCODE_BASE_URL",
    ),
    "alibaba": ProviderConfig(
        "alibaba",
        "Alibaba Cloud (DashScope)",
        "api_key",
        base_url="https://dashscope-intl.aliyuncs.com/apps/anthropic",
        env_keys=("DASHSCOPE_API_KEY",),
        base_url_env_key="DASHSCOPE_BASE_URL",
        api="anthropic_messages",
    ),
    "custom": ProviderConfig(
        "custom",
        "Custom Endpoint",
        "api_key",
        env_keys=("OPENAI_API_KEY", "OPENROUTER_API_KEY"),
        base_url_env_key="OPENAI_BASE_URL",
    ),
}

PROVIDER_ALIASES = {
    "glm": "zai",
    "z-ai": "zai",
    "z.ai": "zai",
    "zhipu": "zai",
    "github": "copilot",
    "github-copilot": "copilot",
    "github-models": "copilot",
    "github-copilot-acp": "copilot-acp",
    "moonshot": "kimi-coding",
    "kimi": "kimi-coding",
    "claude": "anthropic",
    "claude-code": "anthropic",
    "deep-seek": "deepseek",
    "opencode": "opencode-zen",
    "zen": "opencode-zen",
    "aigateway": "ai-gateway",
    "vercel": "ai-gateway",
    "vercel-ai-gateway": "ai-gateway",
    "kilo": "kilocode",
    "kilo-code": "kilocode",
    "dashscope": "alibaba",
    "aliyun": "alibaba",
    "qwen": "alibaba",
}

AUTH_TOKEN_FIELDS = (
    "api_key",
    "token",
    "access_token",
    "agent_api_key",
    "minted_api_key",
    "refresh_token",
)


def normalize_provider_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized:
        return None
    if normalized.startswith("custom:"):
        return normalized
    return PROVIDER_ALIASES.get(normalized, normalized)


def canonical_provider_name(value: str | None) -> str | None:
    normalized = normalize_provider_name(value)
    if normalized is None:
        return None
    if normalized.startswith("custom:"):
        return "custom"
    return normalized


def provider_label(value: str | None) -> str:
    normalized = normalize_provider_name(value)
    if normalized is None:
        return "Unknown"
    if normalized.startswith("custom:"):
        return f"Custom ({normalized.partition(':')[2]})"
    config = PROVIDER_REGISTRY.get(normalized)
    return config.label if config else normalized


@dataclass
class AuthStore:
    home: Path | None = None
    env: dict[str, str] = field(default_factory=lambda: dict(os.environ))

    def __post_init__(self) -> None:
        self.home = self.home or Path(os.getenv("IO_HOME", Path.home() / ".io"))

    @property
    def resolved_home(self) -> Path:
        assert self.home is not None
        return self.home

    @property
    def auth_path(self) -> Path:
        return self.resolved_home / "auth.json"

    @property
    def env_path(self) -> Path:
        return self.resolved_home / ".env"

    @property
    def config_path(self) -> Path:
        return self.resolved_home / "config.yaml"

    def load_auth(self) -> dict[str, Any]:
        if not self.auth_path.exists():
            return {}
        return json.loads(self.auth_path.read_text(encoding="utf-8"))

    def save_auth(self, payload: dict[str, Any]) -> None:
        self.resolved_home.mkdir(parents=True, exist_ok=True)
        self.auth_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def dotenv_values(self) -> dict[str, str]:
        if not self.env_path.exists():
            return {}
        return {key: value for key, value in dotenv_values(self.env_path).items() if value is not None}

    def provider_config(self, provider: str | None) -> ProviderConfig:
        normalized = canonical_provider_name(provider) or "mock"
        return PROVIDER_REGISTRY.get(normalized, PROVIDER_REGISTRY["custom"])

    def list_known_providers(self) -> list[str]:
        return sorted(PROVIDER_REGISTRY)

    def lookup_custom_provider(
        self,
        provider: str | None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized = normalize_provider_name(provider)
        if normalized is None or normalized in PROVIDER_REGISTRY:
            return None
        requested_name = normalized.partition(":")[2] if normalized.startswith("custom:") else normalized
        custom_providers = config.get("custom_providers", []) if isinstance(config, dict) else []
        if not isinstance(custom_providers, list):
            return None
        for entry in custom_providers:
            if not isinstance(entry, dict):
                continue
            name = normalize_provider_name(str(entry.get("name", "")))
            if name != requested_name:
                continue
            return {
                "name": requested_name,
                "base_url": str(entry.get("base_url", "") or "").strip(),
                "api_key": str(entry.get("api_key", "") or "").strip(),
                "api_mode": str(entry.get("api_mode", "chat_completions") or "chat_completions").strip(),
            }
        return None

    def active_provider(self) -> str | None:
        payload = self.load_auth()
        return normalize_provider_name(payload.get("active_provider"))

    def set_active_provider(self, provider: str) -> None:
        payload = self.load_auth()
        payload["active_provider"] = normalize_provider_name(provider) or provider
        self.save_auth(payload)

    def _auth_provider_payload(self, provider: str) -> dict[str, Any]:
        payload = self.load_auth()
        direct = payload.get(provider)
        if isinstance(direct, dict):
            return direct
        canonical = canonical_provider_name(provider)
        nested = payload.get(canonical or "")
        if isinstance(nested, dict):
            return nested
        return {}

    def _token_from_auth_payload(self, provider: str) -> str | None:
        payload = self._auth_provider_payload(provider)
        for field_name in AUTH_TOKEN_FIELDS:
            value = payload.get(field_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
        runtime = payload.get("runtime")
        if isinstance(runtime, dict):
            for field_name in AUTH_TOKEN_FIELDS:
                value = runtime.get(field_name)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def get_stored_provider_token(self, provider: str) -> str | None:
        """Return API key from ``~/.io/auth.json`` only (no environment variables)."""
        return self._token_from_auth_payload(provider)

    def get_api_key(self, provider: str | None, config: dict[str, Any] | None = None) -> str | None:
        normalized = normalize_provider_name(provider)
        if normalized is None or normalized == "mock":
            return None

        custom = self.lookup_custom_provider(normalized, config)
        if custom:
            if custom["api_key"]:
                return custom["api_key"]
            normalized = "custom"

        if normalized == "copilot":
            from .copilot_auth import resolve_copilot_api_key

            return resolve_copilot_api_key(self, config=config)

        provider_cfg = self.provider_config(normalized)
        dotenv_map = self.dotenv_values()
        for env_key in provider_cfg.env_keys:
            value = self.env.get(env_key) or dotenv_map.get(env_key)
            if value:
                return value
        return self._token_from_auth_payload(normalized)

    def get_base_url(self, provider: str | None, config: dict[str, Any] | None = None) -> str | None:
        normalized = normalize_provider_name(provider)
        if normalized is None or normalized == "mock":
            return None

        custom = self.lookup_custom_provider(normalized, config)
        if custom:
            return custom["base_url"] or None

        provider_cfg = self.provider_config(normalized)
        dotenv_map = self.dotenv_values()
        if provider_cfg.base_url_env_key:
            value = self.env.get(provider_cfg.base_url_env_key) or dotenv_map.get(provider_cfg.base_url_env_key)
            if value:
                return value.rstrip("/")

        auth_payload = self._auth_provider_payload(normalized)
        base_url = auth_payload.get("base_url")
        if isinstance(base_url, str) and base_url.strip():
            return base_url.rstrip("/")

        return provider_cfg.base_url or None

    def resolve_provider(
        self,
        requested: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        candidates: list[str | None] = [requested]
        if isinstance(config, dict):
            model_cfg = config.get("model")
            if isinstance(model_cfg, dict):
                candidates.append(model_cfg.get("provider"))
        candidates.append(self.env.get("IO_INFERENCE_PROVIDER"))
        for candidate in candidates:
            normalized = normalize_provider_name(candidate)
            if normalized is None or normalized == "auto":
                continue
            if normalized in PROVIDER_REGISTRY:
                return normalized
            if self.lookup_custom_provider(normalized, config):
                return f"custom:{normalized.partition(':')[2] if normalized.startswith('custom:') else normalized}"

        active_provider = self.active_provider()
        if active_provider:
            if self.lookup_custom_provider(active_provider, config):
                return active_provider
            status = self.provider_status(active_provider, config=config)
            if status.get("logged_in"):
                return active_provider

        if self.env.get("OPENAI_BASE_URL") or self.dotenv_values().get("OPENAI_BASE_URL"):
            return "custom"

        ordered_providers = [
            "nous",
            "openrouter",
            "openai",
            "anthropic",
            "copilot",
            "zai",
            "kimi-coding",
            "minimax",
            "minimax-cn",
            "deepseek",
            "ai-gateway",
            "opencode-zen",
            "opencode-go",
            "kilocode",
            "alibaba",
        ]
        for provider_id in ordered_providers:
            if self.get_api_key(provider_id, config=config):
                return provider_id

        return "mock"

    def provider_status(self, provider: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = normalize_provider_name(provider) or "mock"
        custom = self.lookup_custom_provider(normalized, config)
        if custom:
            return {
                "provider": f"custom:{custom['name']}",
                "label": f"Custom ({custom['name']})",
                "logged_in": bool(custom["base_url"] or custom["api_key"]),
                "base_url": custom["base_url"],
                "api_mode": custom["api_mode"],
            }
        provider_cfg = self.provider_config(normalized)
        token = self.get_api_key(normalized, config=config)
        base_url = self.get_base_url(normalized, config=config)
        logged_in = normalized == "mock" or bool(token) or bool(base_url and normalized == "custom")
        return {
            "provider": normalized,
            "label": provider_cfg.label,
            "logged_in": logged_in,
            "base_url": base_url,
            "api_mode": provider_cfg.api,
        }

    def headers_for(self, provider: str | None) -> dict[str, str]:
        normalized = canonical_provider_name(provider) or "mock"
        token = self.get_api_key(normalized)
        if not token:
            return {}
        if normalized in {"anthropic", "alibaba"}:
            return {"x-api-key": token, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {token}"}
