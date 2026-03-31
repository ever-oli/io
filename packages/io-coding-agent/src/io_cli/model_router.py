"""Smart model routing and ordered fallback resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from io_agent import ResolvedRuntime, RuntimeTarget, resolve_runtime

_COMPLEX_KEYWORDS = (
    "debug",
    "investigate",
    "root cause",
    "architecture",
    "concurrency",
    "distributed",
    "performance",
    "migration",
    "frontend",
    "design",
    "refactor",
    "write code",
    "implement",
    "test",
    "fix",
)


def _smart_config(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("smart_model_routing")
    return dict(raw) if isinstance(raw, dict) else {}


def _prompt_words(prompt: str) -> list[str]:
    return [item for item in prompt.strip().split() if item]


def _cheap_model_config(config: dict[str, Any]) -> dict[str, Any]:
    smart_cfg = _smart_config(config)
    cheap_cfg = smart_cfg.get("cheap_model")
    if isinstance(cheap_cfg, str) and cheap_cfg.strip():
        return {"model": cheap_cfg.strip()}
    if isinstance(cheap_cfg, dict):
        return dict(cheap_cfg)
    return {}


def is_simple_prompt(prompt: str, config: dict[str, Any]) -> tuple[bool, str]:
    smart_cfg = _smart_config(config)
    max_chars = int(smart_cfg.get("max_simple_chars", 160) or 160)
    max_words = int(smart_cfg.get("max_simple_words", 28) or 28)
    stripped = prompt.strip()
    words = _prompt_words(stripped)
    lowered = stripped.lower()

    if not stripped:
        return False, "empty_prompt"
    if "\n" in stripped or "```" in stripped:
        return False, "multiline_or_code_block"
    if len(stripped) > max_chars:
        return False, f"chars>{max_chars}"
    if len(words) > max_words:
        return False, f"words>{max_words}"
    if any(keyword in lowered for keyword in _COMPLEX_KEYWORDS):
        return False, "matched_complex_keyword"
    return True, "short_single_line_prompt"


def _entry_from_legacy_fallback(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str) and raw.strip():
        return [{"model": raw.strip()}]
    if isinstance(raw, dict):
        entry = dict(raw)
        if any(
            str(entry.get(key, "") or "").strip()
            for key in ("provider", "model", "base_url", "api_key_env", "api_mode")
        ):
            return [entry]
    return []


def _fallback_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    raw = config.get("fallback_providers")
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                entries.append(dict(item))
    entries.extend(_entry_from_legacy_fallback(config.get("fallback_model")))
    return entries


def _dedupe_targets(targets: list[RuntimeTarget]) -> list[RuntimeTarget]:
    seen: set[tuple[str, str, str]] = set()
    out: list[RuntimeTarget] = []
    for target in targets:
        key = (target.provider, target.model, str(target.base_url or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(target)
    return out


def _target_from_entry(
    entry: dict[str, Any],
    *,
    config: dict[str, Any],
    env: dict[str, str],
    home: Path | None,
    default_provider: str | None,
    route_kind: str,
    route_label: str,
    route_reason: str | None,
) -> RuntimeTarget | None:
    model = str(entry.get("model", "") or "").strip()
    provider = str(entry.get("provider", "") or "").strip() or default_provider or None
    base_url = str(entry.get("base_url", "") or "").strip() or None
    if not model and not provider:
        return None
    resolved = resolve_runtime(
        cli_model=model or None,
        cli_provider=provider,
        cli_base_url=base_url,
        config=config,
        home=home,
        env=env,
    )
    api_key = resolved.api_key
    api_key_env = str(entry.get("api_key_env", "") or "").strip()
    if api_key_env:
        api_key = str(env.get(api_key_env, "") or os.environ.get(api_key_env, "")).strip() or api_key
    api_mode = str(entry.get("api_mode", "") or "").strip() or resolved.api_mode
    return RuntimeTarget(
        provider=resolved.provider,
        model=resolved.model,
        base_url=resolved.base_url,
        api_key=api_key,
        api_mode=api_mode,
        source=resolved.source,
        requested_provider=resolved.requested_provider,
        route_kind=route_kind,
        route_label=route_label,
        route_reason=route_reason,
    )


def apply_model_routing(
    prompt: str,
    *,
    runtime: ResolvedRuntime,
    config: dict[str, Any],
    env: dict[str, str] | None = None,
    home: Path | None = None,
) -> ResolvedRuntime:
    env_map = dict(os.environ) if env is None else dict(env)
    primary_target = runtime.primary_target or runtime.active_target()
    selected = runtime

    smart_cfg = _smart_config(config)
    simple_prompt, simple_reason = is_simple_prompt(prompt, config)
    cheap_cfg = _cheap_model_config(config)
    smart_enabled = bool(smart_cfg.get("enabled", False))

    if smart_enabled and simple_prompt and cheap_cfg:
        route_reason = f"smart_model_routing matched ({simple_reason})"
        cheap_target = _target_from_entry(
            cheap_cfg,
            config=config,
            env=env_map,
            home=home,
            default_provider=runtime.provider,
            route_kind="smart",
            route_label="cheap_model",
            route_reason=route_reason,
        )
        if cheap_target is not None:
            selected = ResolvedRuntime(
                provider=cheap_target.provider,
                model=cheap_target.model,
                base_url=cheap_target.base_url,
                api_key=cheap_target.api_key,
                api_mode=cheap_target.api_mode,
                source=cheap_target.source,
                requested_provider=runtime.requested_provider,
                requested_model=runtime.requested_model,
                route_kind="smart",
                route_label="cheap_model",
                route_reason=route_reason,
                primary_target=primary_target,
            )

    fallback_targets: list[RuntimeTarget] = []
    if selected.route_kind == "smart":
        fallback_targets.append(
            RuntimeTarget(
                provider=primary_target.provider,
                model=primary_target.model,
                base_url=primary_target.base_url,
                api_key=primary_target.api_key,
                api_mode=primary_target.api_mode,
                source=primary_target.source,
                requested_provider=primary_target.requested_provider,
                route_kind="fallback",
                route_label="primary_strong_model",
                route_reason="smart cheap-model route failed",
            )
        )

    for entry in _fallback_entries(config):
        target = _target_from_entry(
            entry,
            config=config,
            env=env_map,
            home=home,
            default_provider=runtime.provider,
            route_kind="fallback",
            route_label="configured_fallback",
            route_reason="configured fallback provider",
        )
        if target is not None:
            fallback_targets.append(target)

    selected.fallback_targets = _dedupe_targets(fallback_targets)
    return selected


def recommend_model_route(
    task: str,
    *,
    config: dict[str, Any],
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env_map = dict(os.environ) if env is None else dict(env)
    runtime = resolve_runtime(config=config, home=home, env=env_map)
    routed = apply_model_routing(task, runtime=runtime, config=config, env=env_map, home=home)
    simple_prompt, reason = is_simple_prompt(task, config)
    return {
        "input": task,
        "simple_prompt": simple_prompt,
        "simple_reason": reason,
        "selected": routed.active_target().to_dict(),
        "primary": (routed.primary_target or runtime.active_target()).to_dict(),
        "fallbacks": [item.to_dict() for item in routed.fallback_targets],
    }


def model_router_status(
    *,
    config: dict[str, Any],
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env_map = dict(os.environ) if env is None else dict(env)
    runtime = resolve_runtime(config=config, home=home, env=env_map)
    cheap_cfg = _cheap_model_config(config)
    cheap_target = None
    if cheap_cfg:
        cheap_target = _target_from_entry(
            cheap_cfg,
            config=config,
            env=env_map,
            home=home,
            default_provider=runtime.provider,
            route_kind="smart",
            route_label="cheap_model",
            route_reason=None,
        )
    return {
        "enabled": bool(_smart_config(config).get("enabled", False)),
        "runtime": runtime.active_target().to_dict(),
        "cheap_model": cheap_target.to_dict() if cheap_target else None,
        "fallbacks": [item.to_dict() for item in apply_model_routing("", runtime=runtime, config=config, env=env_map, home=home).fallback_targets],
    }


def set_model_router_auto(config: dict[str, Any], enabled: bool) -> dict[str, Any]:
    smart_cfg = config.setdefault("smart_model_routing", {})
    if not isinstance(smart_cfg, dict):
        smart_cfg = {}
        config["smart_model_routing"] = smart_cfg
    smart_cfg["enabled"] = bool(enabled)
    return config
