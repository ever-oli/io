"""Runtime provider resolution helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from io_ai import (
    AuthStore,
    ModelRegistry,
    canonical_provider_name,
    get_model_config,
    normalize_provider_name,
    resolve_runtime_provider,
)


@dataclass(slots=True)
class RuntimeTarget:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    api_mode: str = "chat_completions"
    source: str = "default"
    requested_provider: str | None = None
    route_kind: str = "primary"
    route_label: str = "primary"
    route_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "api_mode": self.api_mode,
            "source": self.source,
            "requested_provider": self.requested_provider,
            "route_kind": self.route_kind,
            "route_label": self.route_label,
            "route_reason": self.route_reason,
        }


@dataclass(slots=True)
class ResolvedRuntime:
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    api_mode: str = "chat_completions"
    source: str = "default"
    requested_provider: str | None = None
    requested_model: str | None = None
    route_kind: str = "primary"
    route_label: str = "primary"
    route_reason: str | None = None
    fallback_targets: list[RuntimeTarget] = field(default_factory=list)
    primary_target: RuntimeTarget | None = None

    def active_target(self) -> RuntimeTarget:
        return RuntimeTarget(
            provider=self.provider,
            model=self.model,
            base_url=self.base_url,
            api_key=self.api_key,
            api_mode=self.api_mode,
            source=self.source,
            requested_provider=self.requested_provider,
            route_kind=self.route_kind,
            route_label=self.route_label,
            route_reason=self.route_reason,
        )

    def all_targets(self) -> list[RuntimeTarget]:
        return [self.active_target(), *self.fallback_targets]


def _has_any_auth(store: AuthStore, config: dict[str, Any]) -> bool:
    for provider in store.list_known_providers():
        if provider == "mock":
            continue
        status = store.provider_status(provider, config=config)
        if status.get("logged_in"):
            return True
    custom_providers = config.get("custom_providers", [])
    if isinstance(custom_providers, list):
        for entry in custom_providers:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("base_url", "") or "").strip():
                return True
    return False


def resolve_runtime(
    *,
    cli_provider: str | None = None,
    cli_model: str | None = None,
    cli_base_url: str | None = None,
    config: dict[str, Any] | None = None,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> ResolvedRuntime:
    # `{}` is a valid "isolated" env for tests; do not treat it as falsy.
    if env is None:
        env = dict(os.environ)
    else:
        env = dict(env)
    config = config or {}
    store = AuthStore(home=home, env=env)
    registry = ModelRegistry()
    model_cfg = get_model_config(config)

    runtime = resolve_runtime_provider(
        requested=cli_provider,
        explicit_base_url=cli_base_url,
        config=config,
        home=home,
        env=env,
    )
    requested_provider = runtime.get("requested_provider")
    provider = canonical_provider_name(str(runtime.get("provider") or "")) or "mock"
    base_url = str(runtime.get("base_url") or "").strip() or None
    api_key = str(runtime.get("api_key") or "").strip() or None
    api_mode = str(runtime.get("api_mode") or "chat_completions")
    source = str(runtime.get("source") or "config/env")
    requested_normalized = normalize_provider_name(requested_provider)

    if provider == "openrouter" and (
        source.startswith("custom_provider:")
        or requested_normalized == "custom"
        or str(requested_normalized or "").startswith("custom:")
        or (base_url and "openrouter.ai" not in base_url.lower())
    ):
        provider = "custom"

    explicit_model = cli_model or env.get("IO_MODEL") or model_cfg.get("default")

    if (
        not _has_any_auth(store, config)
        and requested_provider in {None, "", "auto"}
        and not cli_model
        and not cli_base_url
    ):
        provider = "mock"
        chosen = registry.resolve(model="mock/io-test", provider="mock")
        base_url = None
        api_key = None
        api_mode = "mock"
        source = "mock-fallback"
    elif provider == "mock":
        chosen = registry.resolve(model=explicit_model or "mock/io-test", provider="mock")
    elif provider == "custom" and explicit_model and not explicit_model.startswith("custom/"):
        chosen = registry.resolve(model=explicit_model, provider="openai", base_url=base_url)
        chosen = replace(
            chosen,
            provider="custom",
            id=f"custom/{chosen.remote_id}",
            base_url=base_url,
        )
    else:
        chosen = registry.resolve(model=explicit_model, provider=provider, base_url=base_url)
        provider = chosen.provider

    return ResolvedRuntime(
        provider=provider,
        model=chosen.id,
        base_url=base_url or chosen.base_url,
        api_key=api_key,
        api_mode=api_mode or chosen.api,
        source=source,
        requested_provider=requested_normalized,
        requested_model=explicit_model or chosen.id,
        route_kind="primary",
        route_label="primary",
        primary_target=RuntimeTarget(
            provider=provider,
            model=chosen.id,
            base_url=base_url or chosen.base_url,
            api_key=api_key,
            api_mode=api_mode or chosen.api,
            source=source,
            requested_provider=requested_normalized,
            route_kind="primary",
            route_label="primary",
        ),
    )
