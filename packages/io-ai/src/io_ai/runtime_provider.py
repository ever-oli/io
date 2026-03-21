"""Shared runtime provider resolution for CLI, cron, gateway, and agent execution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from .auth import AuthStore, OPENROUTER_BASE_URL, PROVIDER_REGISTRY, canonical_provider_name
from .models import copilot_model_api_mode


_VALID_API_MODES = {"chat_completions", "codex_responses", "anthropic_messages", "mock"}


def _env_map(env: dict[str, str] | None = None) -> dict[str, str]:
    return dict(os.environ) if env is None else dict(env)


def _env_get(env: dict[str, str], key: str) -> str:
    return str(env.get(key, "") or "").strip()


def _normalize_custom_provider_name(value: str) -> str:
    return value.strip().lower().replace(" ", "-")


def _parse_api_mode(raw: Any) -> str | None:
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in _VALID_API_MODES:
            return normalized
    return None


def _auto_detect_local_model(base_url: str) -> str:
    """Query a local OpenAI-compatible server for its sole loaded model."""

    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return ""
    if not normalized.endswith("/v1"):
        normalized += "/v1"
    try:
        response = httpx.get(f"{normalized}/models", timeout=5)
        if response.status_code != 200:
            return ""
        data = response.json()
        models = data.get("data", []) if isinstance(data, dict) else []
        if len(models) == 1:
            model_id = models[0].get("id", "")
            if isinstance(model_id, str) and model_id.strip():
                return model_id.strip()
    except Exception:
        return ""
    return ""


def get_model_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    model_cfg = config.get("model") if isinstance(config, dict) else None
    if isinstance(model_cfg, dict):
        cfg = dict(model_cfg)
        default = str(cfg.get("default", "") or "").strip()
        base_url = str(cfg.get("base_url", "") or "").strip()
        is_local = "localhost" in base_url or "127.0.0.1" in base_url
        _stock = frozenset(
            {
                "anthropic/claude-opus-4.6",
                "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
            }
        )
        is_fallback = not default or default in _stock
        if is_local and is_fallback and base_url:
            detected = _auto_detect_local_model(base_url)
            if detected:
                cfg["default"] = detected
        return cfg
    if isinstance(model_cfg, str) and model_cfg.strip():
        return {"default": model_cfg.strip()}
    return {}


def resolve_requested_provider(
    requested: str | None = None,
    *,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve provider request from explicit arg, config, then env."""

    if requested and requested.strip():
        return requested.strip().lower()

    model_cfg = get_model_config(config)
    cfg_provider = model_cfg.get("provider")
    if isinstance(cfg_provider, str) and cfg_provider.strip():
        return cfg_provider.strip().lower()

    runtime_env = _env_map(env)
    env_provider = _env_get(runtime_env, "IO_INFERENCE_PROVIDER")
    if env_provider:
        return env_provider.lower()

    return "auto"


def _get_named_custom_provider(
    requested_provider: str,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    requested_norm = _normalize_custom_provider_name(requested_provider or "")
    if not requested_norm or requested_norm in {"auto", "custom"}:
        return None

    if not requested_norm.startswith("custom:"):
        canonical = canonical_provider_name(requested_norm)
        if canonical and canonical in PROVIDER_REGISTRY:
            return None

    custom_providers = config.get("custom_providers") if isinstance(config, dict) else None
    if not isinstance(custom_providers, list):
        return None

    for entry in custom_providers:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        base_url = entry.get("base_url")
        if not isinstance(name, str) or not isinstance(base_url, str):
            continue
        name_norm = _normalize_custom_provider_name(name)
        menu_key = f"custom:{name_norm}"
        if requested_norm not in {name_norm, menu_key}:
            continue
        result = {
            "name": name.strip(),
            "base_url": base_url.strip(),
            "api_key": str(entry.get("api_key", "") or "").strip(),
        }
        api_mode = _parse_api_mode(entry.get("api_mode"))
        if api_mode:
            result["api_mode"] = api_mode
        return result
    return None


def _resolve_named_custom_runtime(
    *,
    requested_provider: str,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    explicit_api_key: str | None = None,
    explicit_base_url: str | None = None,
) -> dict[str, Any] | None:
    custom_provider = _get_named_custom_provider(requested_provider, config=config)
    if not custom_provider:
        return None

    runtime_env = _env_map(env)
    base_url = ((explicit_base_url or "").strip() or custom_provider.get("base_url", "")).rstrip("/")
    if not base_url:
        return None

    api_key = (
        (explicit_api_key or "").strip()
        or custom_provider.get("api_key", "")
        or _env_get(runtime_env, "OPENAI_API_KEY")
        or _env_get(runtime_env, "OPENROUTER_API_KEY")
    )

    return {
        "provider": "openrouter",
        "api_mode": custom_provider.get("api_mode", "chat_completions"),
        "base_url": base_url,
        "api_key": api_key,
        "source": f"custom_provider:{custom_provider.get('name', requested_provider)}",
    }


def _compat_runtime_source(
    *,
    explicit_api_key: str | None = None,
    explicit_base_url: str | None = None,
) -> str:
    return "explicit" if (explicit_api_key or explicit_base_url) else "env/config"


def _resolve_openai_compat_runtime(
    *,
    requested_provider: str,
    config: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
    explicit_api_key: str | None = None,
    explicit_base_url: str | None = None,
) -> dict[str, Any]:
    model_cfg = get_model_config(config)
    runtime_env = _env_map(env)

    cfg_base_url = str(model_cfg.get("base_url", "") or "").strip()
    cfg_provider = str(model_cfg.get("provider", "") or "").strip().lower()
    cfg_api_key = ""
    for key in ("api_key", "api"):
        value = model_cfg.get(key)
        if isinstance(value, str) and value.strip():
            cfg_api_key = value.strip()
            break

    requested_norm = (requested_provider or "").strip().lower()
    env_openai_base_url = _env_get(runtime_env, "OPENAI_BASE_URL")
    env_openrouter_base_url = _env_get(runtime_env, "OPENROUTER_BASE_URL")

    use_config_base_url = False
    if cfg_base_url and not explicit_base_url:
        if requested_norm == "auto":
            if (not cfg_provider or cfg_provider == "auto") and not env_openai_base_url:
                use_config_base_url = True
        elif requested_norm == "custom" and cfg_provider == "custom":
            use_config_base_url = True

    skip_openai_base = requested_norm == "openrouter"
    base_url = (
        (explicit_base_url or "").strip()
        or (cfg_base_url if use_config_base_url else "")
        or ("" if skip_openai_base else env_openai_base_url)
        or env_openrouter_base_url
        or OPENROUTER_BASE_URL
    ).rstrip("/")

    is_openrouter_url = "openrouter.ai" in base_url.lower()
    if is_openrouter_url:
        api_key = (
            (explicit_api_key or "").strip()
            or _env_get(runtime_env, "OPENROUTER_API_KEY")
            or _env_get(runtime_env, "OPENAI_API_KEY")
        )
    else:
        api_key = (
            (explicit_api_key or "").strip()
            or (cfg_api_key if use_config_base_url else "")
            or _env_get(runtime_env, "OPENAI_API_KEY")
            or _env_get(runtime_env, "OPENROUTER_API_KEY")
        )

    return {
        "provider": "openrouter",
        "api_mode": _parse_api_mode(model_cfg.get("api_mode")) or "chat_completions",
        "base_url": base_url,
        "api_key": api_key,
        "source": _compat_runtime_source(
            explicit_api_key=explicit_api_key,
            explicit_base_url=explicit_base_url,
        ),
    }


def resolve_runtime_provider(
    *,
    requested: str | None = None,
    explicit_api_key: str | None = None,
    explicit_base_url: str | None = None,
    config: dict[str, Any] | None = None,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve runtime provider credentials for IO execution."""

    runtime_env = _env_map(env)
    requested_provider = resolve_requested_provider(requested, config=config, env=runtime_env)

    custom_runtime = _resolve_named_custom_runtime(
        requested_provider=requested_provider,
        config=config,
        env=runtime_env,
        explicit_api_key=explicit_api_key,
        explicit_base_url=explicit_base_url,
    )
    if custom_runtime:
        custom_runtime["requested_provider"] = requested_provider
        return custom_runtime

    store = AuthStore(home=home, env=runtime_env)
    provider = store.resolve_provider(requested_provider, config=config)
    if provider.startswith("custom:"):
        provider = "custom"
    if provider == "mock":
        model_cfg = get_model_config(config)
        hinted_base_url = (
            (explicit_base_url or "").strip()
            or str(model_cfg.get("base_url", "") or "").strip()
            or _env_get(runtime_env, "OPENAI_BASE_URL")
            or _env_get(runtime_env, "OPENROUTER_BASE_URL")
        )
        if hinted_base_url:
            provider = "openrouter"

    if provider == "mock":
        return {
            "provider": "mock",
            "api_mode": "mock",
            "base_url": "",
            "api_key": "",
            "source": "mock",
            "requested_provider": requested_provider,
        }

    if provider in {"openrouter", "custom"}:
        runtime = _resolve_openai_compat_runtime(
            requested_provider=requested_provider,
            config=config,
            env=runtime_env,
            explicit_api_key=explicit_api_key,
            explicit_base_url=explicit_base_url,
        )
        runtime["requested_provider"] = requested_provider
        return runtime

    provider_cfg = PROVIDER_REGISTRY.get(provider)
    base_url = (
        (explicit_base_url or "").strip()
        or (store.get_base_url(provider, config=config) or "").strip()
    ).rstrip("/")
    api_key = (explicit_api_key or "").strip() or (store.get_api_key(provider, config=config) or "")
    source = _compat_runtime_source(explicit_api_key=explicit_api_key, explicit_base_url=explicit_base_url)

    if provider == "openai-codex":
        return {
            "provider": "openai-codex",
            "api_mode": "codex_responses",
            "base_url": base_url,
            "api_key": api_key,
            "source": source,
            "requested_provider": requested_provider,
        }

    if provider == "copilot-acp":
        command = _env_get(runtime_env, "IO_COPILOT_ACP_COMMAND")
        args = _env_get(runtime_env, "IO_COPILOT_ACP_ARGS")
        return {
            "provider": "copilot-acp",
            "api_mode": "chat_completions",
            "base_url": base_url,
            "api_key": api_key,
            "command": command,
            "args": [arg for arg in args.split() if arg],
            "source": source if command else "process",
            "requested_provider": requested_provider,
        }

    if provider in {"anthropic", "alibaba"}:
        return {
            "provider": provider,
            "api_mode": "anthropic_messages",
            "base_url": base_url,
            "api_key": api_key,
            "source": source,
            "requested_provider": requested_provider,
        }

    api_mode = provider_cfg.api if provider_cfg else "chat_completions"
    model_cfg = get_model_config(config)
    if provider == "copilot":
        api_mode = copilot_model_api_mode(str(model_cfg.get("default") or ""), api_key=api_key)
    else:
        configured_mode = _parse_api_mode(model_cfg.get("api_mode"))
        if configured_mode:
            api_mode = configured_mode
        elif base_url.rstrip("/").endswith("/anthropic"):
            api_mode = "anthropic_messages"

    return {
        "provider": provider,
        "api_mode": api_mode,
        "base_url": base_url,
        "api_key": api_key,
        "source": source,
        "requested_provider": requested_provider,
    }


def format_runtime_provider_error(error: Exception) -> str:
    return str(error)
