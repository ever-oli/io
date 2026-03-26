"""Canonical model catalogs and lightweight validation helpers for IO."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .auth import (
    OPENROUTER_BASE_URL,
    AuthStore,
    PROVIDER_REGISTRY,
    canonical_provider_name,
    normalize_provider_name,
)
from .codex_models import get_codex_model_ids
from .types import ModelRef


COPILOT_BASE_URL = "https://api.githubcopilot.com"
COPILOT_MODELS_URL = f"{COPILOT_BASE_URL}/models"
COPILOT_EDITOR_VERSION = "vscode/1.104.1"

OPENROUTER_MODELS: list[tuple[str, str]] = [
    ("anthropic/claude-opus-4.6", "recommended"),
    ("anthropic/claude-sonnet-4.5", ""),
    ("anthropic/claude-haiku-4.5", ""),
    ("openai/gpt-5.4", ""),
    ("openai/gpt-5.4-mini", ""),
    ("openrouter/hunter-alpha", "free"),
    ("openrouter/healer-alpha", "free"),
    ("openai/gpt-5.3-codex", ""),
    ("google/gemini-3-pro-preview", ""),
    ("google/gemini-3-flash-preview", ""),
    ("qwen/qwen3.5-plus-02-15", ""),
    ("qwen/qwen3.5-35b-a3b", ""),
    ("stepfun/step-3.5-flash", ""),
    ("minimax/minimax-m2.5", ""),
    ("z-ai/glm-5", ""),
    ("z-ai/glm-5-turbo", ""),
    ("moonshotai/kimi-k2.5", ""),
    ("x-ai/grok-4.20-beta", ""),
    ("nvidia/nemotron-3-super-120b-a12b:free", "free"),
    ("arcee-ai/trinity-large-preview:free", "free"),
    ("openai/gpt-5.4-pro", ""),
    ("openai/gpt-5.4-nano", ""),
]

PROVIDER_MODELS: dict[str, list[str]] = {
    "mock": ["io-test"],
    "openai": ["gpt-5.4", "gpt-5.4-mini", "gpt-5.3-codex", "gpt-4.1", "gpt-4o"],
    "nous": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "gpt-5.4",
        "gemini-3-flash",
        "gemini-3.0-pro-preview",
        "deepseek-v3.2",
    ],
    "openai-codex": [
        "gpt-5.3-codex",
        "gpt-5.2-codex",
        "gpt-5.1-codex-mini",
        "gpt-5.1-codex-max",
    ],
    "copilot-acp": ["copilot-acp"],
    "copilot": [
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5-mini",
        "gpt-5.3-codex",
        "gpt-5.2-codex",
        "gpt-4.1",
        "gpt-4o",
        "gpt-4o-mini",
        "claude-opus-4.6",
        "claude-sonnet-4.6",
        "claude-sonnet-4.5",
        "claude-haiku-4.5",
        "gemini-2.5-pro",
        "grok-code-fast-1",
    ],
    "zai": ["glm-5", "glm-4.7", "glm-4.5", "glm-4.5-flash"],
    "kimi-coding": [
        "kimi-for-coding",
        "kimi-k2.5",
        "kimi-k2-thinking",
        "kimi-k2-thinking-turbo",
        "kimi-k2-turbo-preview",
        "kimi-k2-0905-preview",
    ],
    "minimax": [
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.1",
    ],
    "minimax-cn": [
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.1",
    ],
    "anthropic": [
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-5-20250929",
        "claude-opus-4-20250514",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
    ],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "opencode-zen": [
        "gpt-5.4-pro",
        "gpt-5.4",
        "gpt-5.3-codex",
        "gpt-5.3-codex-spark",
        "gpt-5.2",
        "gpt-5.2-codex",
        "gpt-5.1",
        "gpt-5.1-codex",
        "gpt-5.1-codex-max",
        "gpt-5.1-codex-mini",
        "gpt-5",
        "gpt-5-codex",
        "gpt-5-nano",
        "claude-opus-4-6",
        "claude-opus-4-5",
        "claude-opus-4-1",
        "claude-sonnet-4-6",
        "claude-sonnet-4-5",
        "claude-sonnet-4",
        "claude-haiku-4-5",
        "claude-3-5-haiku",
        "gemini-3.1-pro",
        "gemini-3-pro",
        "gemini-3-flash",
        "minimax-m2.5",
        "minimax-m2.5-free",
        "minimax-m2.1",
        "glm-5",
        "glm-4.7",
        "glm-4.6",
        "kimi-k2.5",
        "kimi-k2-thinking",
        "kimi-k2",
        "qwen3-coder",
        "big-pickle",
    ],
    "opencode-go": ["glm-5", "kimi-k2.5", "minimax-m2.5"],
    "ai-gateway": [
        "anthropic/claude-opus-4.6",
        "anthropic/claude-sonnet-4.6",
        "anthropic/claude-sonnet-4.5",
        "anthropic/claude-haiku-4.5",
        "openai/gpt-5",
        "openai/gpt-4.1",
        "openai/gpt-4.1-mini",
        "google/gemini-3-pro-preview",
        "google/gemini-3-flash",
        "google/gemini-2.5-pro",
        "google/gemini-2.5-flash",
        "deepseek/deepseek-v3.2",
    ],
    "kilocode": [
        "anthropic/claude-opus-4.6",
        "anthropic/claude-sonnet-4.6",
        "openai/gpt-5.4",
        "google/gemini-3-pro-preview",
        "google/gemini-3-flash-preview",
    ],
    "alibaba": [
        "qwen3.5-plus",
        "qwen3-max",
        "qwen3-coder-plus",
        "qwen3-coder-next",
        "qwen-plus-latest",
        "qwen3.5-flash",
        "qwen-vl-max",
    ],
    "custom": [],
}

PROVIDER_LABELS: dict[str, str] = {
    "mock": "Mock",
    "openrouter": "OpenRouter",
    "openai": "OpenAI",
    "openai-codex": "OpenAI Codex",
    "copilot-acp": "GitHub Copilot ACP",
    "nous": "Nous Portal",
    "copilot": "GitHub Copilot",
    "zai": "Z.AI / GLM",
    "kimi-coding": "Kimi / Moonshot",
    "minimax": "MiniMax",
    "minimax-cn": "MiniMax (China)",
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "opencode-zen": "OpenCode Zen",
    "opencode-go": "OpenCode Go",
    "ai-gateway": "AI Gateway",
    "kilocode": "Kilo Code",
    "alibaba": "Alibaba Cloud (DashScope)",
    "custom": "Custom Endpoint",
}

PROVIDER_ALIASES: dict[str, str] = {
    "glm": "zai",
    "z-ai": "zai",
    "z.ai": "zai",
    "zhipu": "zai",
    "github": "copilot",
    "github-copilot": "copilot",
    "github-models": "copilot",
    "github-model": "copilot",
    "github-copilot-acp": "copilot-acp",
    "copilot-acp-agent": "copilot-acp",
    "kimi": "kimi-coding",
    "moonshot": "kimi-coding",
    "minimax-china": "minimax-cn",
    "minimax_cn": "minimax-cn",
    "claude": "anthropic",
    "claude-code": "anthropic",
    "deep-seek": "deepseek",
    "opencode": "opencode-zen",
    "zen": "opencode-zen",
    "go": "opencode-go",
    "opencode-go-sub": "opencode-go",
    "aigateway": "ai-gateway",
    "vercel": "ai-gateway",
    "vercel-ai-gateway": "ai-gateway",
    "kilo": "kilocode",
    "kilo-code": "kilocode",
    "kilo-gateway": "kilocode",
    "dashscope": "alibaba",
    "aliyun": "alibaba",
    "qwen": "alibaba",
    "alibaba-cloud": "alibaba",
}

DEFAULT_MODEL_IDS: dict[str, str] = {
    "mock": "mock/io-test",
    "openrouter": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
    "openai": "openai/gpt-5.4-mini",
    "openai-codex": "openai-codex/gpt-5.3-codex",
    "anthropic": "anthropic/claude-opus-4-6",
    "nous": "nous/claude-opus-4-6",
    "copilot": "copilot/gpt-5.4",
    "copilot-acp": "copilot-acp/copilot-acp",
    "zai": "zai/glm-5",
    "kimi-coding": "kimi-coding/kimi-for-coding",
    "minimax": "minimax/MiniMax-M2.7",
    "minimax-cn": "minimax-cn/MiniMax-M2.7",
    "deepseek": "deepseek/deepseek-chat",
    "ai-gateway": "ai-gateway/anthropic/claude-opus-4.6",
    "opencode-zen": "opencode-zen/gpt-5.4-pro",
    "opencode-go": "opencode-go/glm-5",
    "kilocode": "kilocode/anthropic/claude-opus-4.6",
    "alibaba": "alibaba/qwen3.5-plus",
}

_KNOWN_PROVIDER_NAMES: set[str] = set(PROVIDER_LABELS) | set(PROVIDER_ALIASES) | {"openrouter", "custom"}

_COPILOT_MODEL_ALIASES: dict[str, str] = {
    "openai/gpt-5": "gpt-5-mini",
    "openai/gpt-5-chat": "gpt-5-mini",
    "openai/gpt-5-mini": "gpt-5-mini",
    "openai/gpt-5-nano": "gpt-5-mini",
    "openai/gpt-4.1": "gpt-4.1",
    "openai/gpt-4.1-mini": "gpt-4.1",
    "openai/gpt-4.1-nano": "gpt-4.1",
    "openai/gpt-4o": "gpt-4o",
    "openai/gpt-4o-mini": "gpt-4o-mini",
    "openai/o1": "gpt-5.2",
    "openai/o1-mini": "gpt-5-mini",
    "openai/o1-preview": "gpt-5.2",
    "openai/o3": "gpt-5.3-codex",
    "openai/o3-mini": "gpt-5-mini",
    "openai/o4-mini": "gpt-5-mini",
    "anthropic/claude-opus-4.6": "claude-opus-4.6",
    "anthropic/claude-sonnet-4.6": "claude-sonnet-4.6",
    "anthropic/claude-sonnet-4.5": "claude-sonnet-4.5",
    "anthropic/claude-haiku-4.5": "claude-haiku-4.5",
}


def model_ids() -> list[str]:
    return [model_id for model_id, _ in OPENROUTER_MODELS]


def menu_labels() -> list[str]:
    labels: list[str] = []
    for model_id, description in OPENROUTER_MODELS:
        labels.append(f"{model_id} ({description})" if description else model_id)
    return labels


def normalize_provider(provider: Optional[str]) -> str:
    normalized = (provider or "openrouter").strip().lower()
    return PROVIDER_ALIASES.get(normalized, normalized)


def provider_label(provider: Optional[str]) -> str:
    original = (provider or "openrouter").strip()
    normalized = original.lower()
    if normalized == "auto":
        return "Auto"
    normalized = normalize_provider(normalized)
    return PROVIDER_LABELS.get(normalized, original or "OpenRouter")


def _resolve_copilot_catalog_api_key() -> str:
    try:
        store = AuthStore()
        return store.get_api_key("copilot") or ""
    except Exception:
        return ""


def _payload_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        data = payload.get("data", [])
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _copilot_catalog_item_is_text_model(item: dict[str, Any]) -> bool:
    model_id = str(item.get("id") or "").strip()
    if not model_id or item.get("model_picker_enabled") is False:
        return False

    capabilities = item.get("capabilities")
    if isinstance(capabilities, dict):
        model_type = str(capabilities.get("type") or "").strip().lower()
        if model_type and model_type != "chat":
            return False

    supported_endpoints = item.get("supported_endpoints")
    if isinstance(supported_endpoints, list):
        normalized_endpoints = {
            str(endpoint).strip()
            for endpoint in supported_endpoints
            if str(endpoint).strip()
        }
        if normalized_endpoints and not normalized_endpoints.intersection(
            {"/chat/completions", "/responses", "/v1/messages"}
        ):
            return False

    return True


def copilot_default_headers() -> dict[str, str]:
    return {
        "Editor-Version": COPILOT_EDITOR_VERSION,
        "User-Agent": "IOAgent/1.0",
        "Openai-Intent": "conversation-edits",
        "x-initiator": "agent",
    }


def fetch_github_model_catalog(
    api_key: Optional[str] = None,
    timeout: float = 5.0,
) -> Optional[list[dict[str, Any]]]:
    attempts: list[dict[str, str]] = []
    if api_key:
        attempts.append({**copilot_default_headers(), "Authorization": f"Bearer {api_key}"})
    attempts.append(copilot_default_headers())

    for headers in attempts:
        request = urllib.request.Request(COPILOT_MODELS_URL, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = json.loads(response.read().decode())
        except Exception:
            continue

        items = _payload_items(data)
        models: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in items:
            if not _copilot_catalog_item_is_text_model(item):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id or model_id in seen_ids:
                continue
            seen_ids.add(model_id)
            models.append(item)
        if models:
            return models
    return None


def _fetch_github_models(api_key: Optional[str] = None, timeout: float = 5.0) -> Optional[list[str]]:
    catalog = fetch_github_model_catalog(api_key=api_key, timeout=timeout)
    if not catalog:
        return None
    return [str(item.get("id") or "").strip() for item in catalog if str(item.get("id") or "").strip()]


def normalize_copilot_model_id(
    model_id: Optional[str],
    *,
    catalog: Optional[list[dict[str, Any]]] = None,
    api_key: Optional[str] = None,
) -> str:
    raw = str(model_id or "").strip()
    if not raw:
        return ""

    catalog_ids: set[str] = set()
    if catalog is not None:
        catalog_ids = {str(item.get("id") or "").strip() for item in catalog if str(item.get("id") or "").strip()}
    elif api_key:
        live = _fetch_github_models(api_key=api_key)
        if live:
            catalog_ids = set(live)

    alias = _COPILOT_MODEL_ALIASES.get(raw)
    if alias:
        return alias

    candidates = [raw]
    if "/" in raw:
        candidates.append(raw.split("/", 1)[1].strip())
    if raw.endswith(("-mini", "-nano", "-chat")):
        candidates.append(raw.rsplit("-", 1)[0])

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if candidate in _COPILOT_MODEL_ALIASES:
            return _COPILOT_MODEL_ALIASES[candidate]
        if candidate in catalog_ids:
            return candidate

    if "/" in raw:
        return raw.split("/", 1)[1].strip()
    return raw


def _should_use_copilot_responses_api(model_id: str) -> bool:
    normalized = (model_id or "").strip().lower()
    match = re.match(r"^gpt-(\d+)", normalized)
    if not match:
        return False
    major = int(match.group(1))
    return major >= 5 and not normalized.startswith("gpt-5-mini")


def copilot_model_api_mode(
    model_id: Optional[str],
    *,
    catalog: Optional[list[dict[str, Any]]] = None,
    api_key: Optional[str] = None,
) -> str:
    normalized = normalize_copilot_model_id(model_id, catalog=catalog, api_key=api_key)
    if not normalized:
        return "chat_completions"

    if _should_use_copilot_responses_api(normalized):
        return "codex_responses"

    if catalog is None and api_key:
        catalog = fetch_github_model_catalog(api_key=api_key)

    if catalog:
        entry = next((item for item in catalog if item.get("id") == normalized), None)
        if isinstance(entry, dict):
            supported_endpoints = {
                str(endpoint).strip()
                for endpoint in (entry.get("supported_endpoints") or [])
                if str(endpoint).strip()
            }
            if "/v1/messages" in supported_endpoints and "/chat/completions" not in supported_endpoints:
                return "anthropic_messages"

    return "chat_completions"


def provider_model_ids(provider: Optional[str]) -> list[str]:
    normalized = normalize_provider(provider)
    if normalized == "openrouter":
        return model_ids()
    if normalized == "openai-codex":
        return get_codex_model_ids()
    if normalized in {"copilot", "copilot-acp"}:
        live = _fetch_github_models(_resolve_copilot_catalog_api_key())
        if live:
            return live
        if normalized == "copilot-acp":
            return list(PROVIDER_MODELS.get("copilot", []))
    return list(PROVIDER_MODELS.get(normalized, []))


def list_available_providers(
    *,
    home: Path | None = None,
    env: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    provider_order = [
        "openrouter",
        "nous",
        "openai-codex",
        "openai",
        "copilot",
        "copilot-acp",
        "zai",
        "kimi-coding",
        "minimax",
        "minimax-cn",
        "kilocode",
        "anthropic",
        "alibaba",
        "opencode-zen",
        "opencode-go",
        "ai-gateway",
        "deepseek",
        "custom",
        "mock",
    ]
    aliases_for: dict[str, list[str]] = {}
    for alias, canonical in PROVIDER_ALIASES.items():
        aliases_for.setdefault(canonical, []).append(alias)

    store = AuthStore(home=home, env=dict(os.environ) if env is None else dict(env))
    result: list[dict[str, Any]] = []
    for provider_id in provider_order:
        status = store.provider_status(provider_id, config=config)
        result.append(
            {
                "id": provider_id,
                "label": PROVIDER_LABELS.get(provider_id, provider_id),
                "aliases": aliases_for.get(provider_id, []),
                "authenticated": bool(status.get("logged_in")),
            }
        )
    return result


def parse_model_input(raw: str, current_provider: str) -> tuple[str, str]:
    """Split ``provider:model`` only when the left side is a known provider token.

    Model ids often contain colons (e.g. OpenRouter ``…/model:free``). Using the
    *first* ``:`` blindly would treat ``openrouter/nvidia/foo:free`` as
    ``provider=openrouter/nvidia/foo`` (invalid) and fall back to *current_provider*,
    which then makes ``ModelRegistry.resolve(..., provider=copilot)`` rewrite
    OpenRouter models to ``copilot/…``.
    """
    stripped = raw.strip()
    colon = stripped.find(":")
    if colon > 0:
        provider_part = stripped[:colon].strip().lower()
        model_part = stripped[colon + 1 :].strip()
        # Real CLI form is ``anthropic:claude-…`` / ``openrouter:gpt-…`` — never ``a/b:c``.
        if (
            provider_part
            and model_part
            and "/" not in provider_part
            and provider_part in _KNOWN_PROVIDER_NAMES
        ):
            return (normalize_provider(provider_part), model_part)
        # Colon present but not ``known_provider:model`` (e.g. ``…/slug:free``) — do not
        # fall back to *current_provider* (would pair copilot + openrouter slug incorrectly).
        return ("", stripped)
    return (current_provider, stripped)


def _find_openrouter_slug(model_name: str) -> Optional[str]:
    name_lower = model_name.strip().lower()
    if not name_lower:
        return None

    for model_id, _ in OPENROUTER_MODELS:
        if name_lower == model_id.lower():
            return model_id

    for model_id, _ in OPENROUTER_MODELS:
        if "/" in model_id:
            _, model_part = model_id.split("/", 1)
            if name_lower == model_part.lower():
                return model_id
    return None


def detect_provider_for_model(model_name: str, current_provider: str) -> Optional[tuple[str, str]]:
    name = (model_name or "").strip()
    if not name:
        return None

    name_lower = name.lower()
    resolved_provider = PROVIDER_ALIASES.get(name_lower, name_lower)
    if resolved_provider not in {"custom", "openrouter"}:
        default_models = PROVIDER_MODELS.get(resolved_provider, [])
        if (
            resolved_provider in PROVIDER_LABELS
            and default_models
            and resolved_provider != normalize_provider(current_provider)
        ):
            return (resolved_provider, default_models[0])

    aggregators = {"nous", "openrouter"}
    current_models = PROVIDER_MODELS.get(current_provider, [])
    if any(name_lower == model.lower() for model in current_models):
        return None

    direct_match: str | None = None
    for provider_id, models in PROVIDER_MODELS.items():
        if provider_id == current_provider or provider_id in aggregators:
            continue
        if any(name_lower == model.lower() for model in models):
            direct_match = provider_id
            break

    if direct_match:
        store = AuthStore()
        if store.get_api_key(direct_match):
            return (direct_match, name)
        openrouter_slug = _find_openrouter_slug(name)
        if openrouter_slug:
            return ("openrouter", openrouter_slug)
        return (direct_match, name)

    openrouter_slug = _find_openrouter_slug(name)
    if openrouter_slug:
        if current_provider != "openrouter":
            return ("openrouter", openrouter_slug)
        if openrouter_slug != name:
            return ("openrouter", openrouter_slug)
        return None

    return None


def _api_for_provider(provider: str, remote_id: str) -> str:
    canonical = canonical_provider_name(provider) or "mock"
    if canonical == "mock":
        return "mock"
    if canonical in {"anthropic", "alibaba"}:
        return "anthropic_messages"
    if canonical == "openai-codex":
        return "codex_responses"
    if canonical == "copilot":
        return copilot_model_api_mode(remote_id)
    return "chat_completions"


def _default_base_url(provider: str) -> str | None:
    canonical = canonical_provider_name(provider) or "mock"
    if canonical == "mock":
        return None
    if canonical == "openrouter":
        return OPENROUTER_BASE_URL
    config = PROVIDER_REGISTRY.get(canonical)
    return config.base_url if config and config.base_url else None


def _make_model_ref(provider: str, remote_id: str, *, metadata: dict[str, Any] | None = None) -> ModelRef:
    canonical = canonical_provider_name(provider) or "mock"
    label = f"{provider_label(canonical)} {remote_id}".strip()
    return ModelRef(
        id=f"{canonical}/{remote_id}",
        provider=canonical,
        api=_api_for_provider(canonical, remote_id),
        remote_id=remote_id,
        label=label,
        base_url=_default_base_url(canonical),
        metadata=metadata or {},
    )


def _build_default_models() -> tuple[ModelRef, ...]:
    models: list[ModelRef] = [
        ModelRef(
            id="mock/io-test",
            provider="mock",
            api="mock",
            remote_id="io-test",
            label="Mock IO Test",
            metadata={"recommended": True},
        )
    ]
    seen_ids = {models[0].id}

    for remote_id, hint in OPENROUTER_MODELS:
        metadata: dict[str, Any] = {}
        if hint:
            metadata["hint"] = hint
        if hint == "recommended":
            metadata["recommended"] = True
        model = _make_model_ref("openrouter", remote_id, metadata=metadata)
        models.append(model)
        seen_ids.add(model.id)

    for provider, provider_models in PROVIDER_MODELS.items():
        if provider == "mock":
            continue
        for remote_id in provider_models:
            model = _make_model_ref(provider, remote_id)
            if model.id in seen_ids:
                continue
            models.append(model)
            seen_ids.add(model.id)

    return tuple(models)


DEFAULT_MODELS = _build_default_models()


@dataclass
class ModelRegistry:
    models: dict[str, ModelRef] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.models:
            self.models = {model.id: model for model in DEFAULT_MODELS}

    def register(self, model: ModelRef) -> None:
        self.models[model.id] = model

    def list(self) -> list[ModelRef]:
        return sorted(self.models.values(), key=lambda item: item.id)

    def get(self, model_id: str) -> ModelRef:
        if model_id in self.models:
            return self.models[model_id]
        raise KeyError(f"Unknown model: {model_id}")

    def provider_models(self, provider: str) -> list[ModelRef]:
        canonical = canonical_provider_name(provider) or normalize_provider(provider)
        models = [model for model in self.list() if model.provider == canonical]
        if models:
            return models
        dynamic = provider_model_ids(canonical)
        return [self._ad_hoc_model(canonical, remote_id) for remote_id in dynamic]

    def default_for(self, provider: str | None = None) -> ModelRef:
        if provider is None:
            canonical = "mock"
        else:
            canonical = canonical_provider_name(provider) or normalize_provider(provider) or "mock"
        default_id = DEFAULT_MODEL_IDS.get(canonical, "mock/io-test")
        if default_id in self.models:
            return self.models[default_id]
        provider_models = self.provider_models(canonical)
        if provider_models:
            return provider_models[0]
        return self.models["mock/io-test"]

    def _ad_hoc_model(self, provider: str, remote_id: str, base_url: str | None = None) -> ModelRef:
        canonical = canonical_provider_name(provider) or "custom"
        return ModelRef(
            id=f"{canonical}/{remote_id}",
            provider=canonical,
            api=_api_for_provider(canonical, remote_id),
            remote_id=remote_id,
            label=f"{provider_label(canonical)} {remote_id}",
            base_url=base_url or _default_base_url(canonical),
        )

    def resolve(
        self,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> ModelRef:
        requested_provider = normalize_provider_name(provider)
        if requested_provider is None and provider is not None:
            requested_provider = normalize_provider(provider)
        canonical = canonical_provider_name(requested_provider) if requested_provider is not None else None
        if canonical is None and requested_provider is not None:
            canonical = normalize_provider(requested_provider)

        if model:
            if model in self.models:
                chosen = self.models[model]
            else:
                parsed_provider = None
                remote_id = model
                if "/" in model:
                    head, remainder = model.split("/", 1)
                    normalized_head = normalize_provider_name(head) or normalize_provider(head)
                    if canonical_provider_name(normalized_head) is not None or normalized_head in self.models:
                        parsed_provider = normalized_head
                        remote_id = remainder

                effective_provider = canonical_provider_name(parsed_provider) or canonical or None
                if effective_provider and f"{effective_provider}/{remote_id}" in self.models:
                    chosen = self.models[f"{effective_provider}/{remote_id}"]
                else:
                    matches = [
                        item
                        for item in self.models.values()
                        if item.remote_id == remote_id
                        and (effective_provider is None or item.provider == effective_provider)
                    ]
                    if matches:
                        chosen = matches[0]
                    else:
                        inferred_provider = effective_provider
                        if inferred_provider is None:
                            if remote_id.startswith("claude-"):
                                inferred_provider = "anthropic"
                            elif remote_id.startswith("gpt-"):
                                inferred_provider = "openai"
                            elif remote_id == "io-test":
                                inferred_provider = "mock"
                            else:
                                inferred = detect_provider_for_model(remote_id, "openrouter")
                                inferred_provider = inferred[0] if inferred else "openrouter"
                        chosen = self._ad_hoc_model(inferred_provider, remote_id, base_url=base_url)
        else:
            chosen = self.default_for(canonical)

        if canonical and chosen.provider != canonical:
            # Do not stomp an explicit ``provider/remote`` id with *canonical* from the
            # outer ``provider=`` argument (e.g. config says copilot but user picked
            # ``openrouter/nvidia/…:free`` in ``/model``).
            skip_force = False
            if model and "/" in model:
                head, _rem = model.split("/", 1)
                nh = normalize_provider_name(head) or normalize_provider(head)
                head_canon = canonical_provider_name(nh)
                if head_canon is not None and head_canon != canonical:
                    skip_force = True
            if not skip_force:
                candidate_id = f"{canonical}/{chosen.remote_id}"
                chosen = self.models.get(
                    candidate_id,
                    self._ad_hoc_model(canonical, chosen.remote_id, base_url=base_url),
                )

        if base_url:
            chosen = ModelRef(
                id=chosen.id,
                provider=chosen.provider,
                api=chosen.api,
                remote_id=chosen.remote_id,
                label=chosen.label,
                base_url=base_url,
                supports_tools=chosen.supports_tools,
                supports_streaming=chosen.supports_streaming,
                reasoning_levels=chosen.reasoning_levels,
                metadata=dict(chosen.metadata),
            )
        return chosen
