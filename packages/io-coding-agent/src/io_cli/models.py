"""Model selection helpers (pi-mono style: auth-scoped catalog + fuzzy search)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from io_agent import resolve_runtime
from io_ai import ModelRegistry, canonical_provider_name, normalize_provider_name, provider_label
from io_ai.models import parse_model_input, provider_model_ids
from io_ai.types import ModelRef


def list_models(provider: str | None = None, *, detailed: bool = False) -> list[object]:
    """Full static/dynamic catalog (all providers). Used by ``io models --all``."""
    registry = ModelRegistry()
    models = registry.provider_models(provider) if provider else registry.list()
    if not detailed:
        if provider:
            return provider_model_ids(provider)
        return [model.id for model in models]
    return [
        {
            "id": model.id,
            "provider": model.provider,
            "provider_label": provider_label(model.provider),
            "remote_id": model.remote_id,
            "base_url": model.base_url,
            "api": model.api,
            "metadata": model.metadata,
        }
        for model in models
    ]


def _format_token_count(count: object) -> str:
    if not isinstance(count, int) or count <= 0:
        return "-"
    if count >= 1_000_000:
        v = count / 1_000_000
        return f"{int(v)}M" if v == int(v) else f"{v:.1f}M"
    if count >= 1_000:
        v = count / 1_000
        return f"{int(v)}K" if v == int(v) else f"{v:.1f}K"
    return str(count)


def _model_table_row(m: ModelRef) -> dict[str, str]:
    meta = m.metadata or {}
    ctx = meta.get("context_window", meta.get("contextWindow"))
    mx = meta.get("max_tokens", meta.get("maxTokens", meta.get("max_output")))
    reasoning = meta.get("reasoning")
    if reasoning is True:
        think = "yes"
    elif reasoning is False:
        think = "no"
    else:
        think = "yes" if len(m.reasoning_levels) > 1 else "-"
    vision = meta.get("vision") or meta.get("input")
    if vision == "image" or vision == ["image"] or (isinstance(vision, list) and "image" in vision):
        images = "yes"
    elif vision:
        images = str(vision)[:3]
    else:
        images = "-"
    return {
        "provider": m.provider,
        "model": m.remote_id,
        "context": _format_token_count(ctx) if isinstance(ctx, int) else (str(ctx) if ctx else "-"),
        "max_out": _format_token_count(mx) if isinstance(mx, int) else (str(mx) if mx else "-"),
        "thinking": think,
        "images": images,
    }


def format_available_models_table(models: list[ModelRef]) -> str:
    """Aligned columns like pi-mono ``list-models`` (provider / model / context / max-out / thinking / images)."""
    if not models:
        return ""
    rows = [_model_table_row(m) for m in models]
    headers = {
        "provider": "provider",
        "model": "model",
        "context": "context",
        "max_out": "max-out",
        "thinking": "thinking",
        "images": "images",
    }
    widths = {k: len(headers[k]) for k in headers}
    for r in rows:
        for k in widths:
            widths[k] = max(widths[k], len(r[k]))

    def line(cells: dict[str, str]) -> str:
        return "  ".join(cells[k].ljust(widths[k]) for k in headers)

    out = [line(headers)]
    out.extend(line(r) for r in rows)
    return "\n".join(out)


def list_auth_available_model_refs(
    *,
    home: Path,
    config: dict[str, Any],
    provider: str | None = None,
) -> list[ModelRef]:
    """Models for providers that have credentials (pi ``ModelRegistry.getAvailable()``)."""
    from .auth import auth_status

    want = None
    if provider:
        want = normalize_provider_name(provider) or provider.strip().lower()
        want_canon = canonical_provider_name(want) or want

    status = auth_status(home)
    providers_map = status.get("providers", {})
    if not isinstance(providers_map, dict):
        return []

    registry = ModelRegistry()
    out: list[ModelRef] = []
    seen: set[str] = set()

    for _pid, pdata in sorted(providers_map.items(), key=lambda kv: str(kv[0])):
        if not isinstance(pdata, dict) or not pdata.get("logged_in"):
            continue
        prov_key = str(pdata.get("provider", _pid))
        if want:
            pk_n = normalize_provider_name(prov_key) or prov_key
            pk_c = canonical_provider_name(pk_n) or pk_n
            if pk_n != want and pk_c != want_canon and prov_key != want:
                continue

        for m in registry.provider_models(prov_key):
            if m.id not in seen:
                seen.add(m.id)
                out.append(m)

    out.sort(key=lambda x: (x.provider, x.id))
    return out


def apply_user_model_selection_to_config(
    raw: str,
    *,
    home: Path,
    config: dict[str, Any],
    env: dict[str, str],
) -> dict[str, Any]:
    """Parse ``provider:remote_id`` or plain id; return updated ``model`` config section (not saved)."""
    stripped = raw.strip()
    mcfg = dict(config.get("model") or {})
    current = str(mcfg.get("provider") or "auto")
    rt = resolve_runtime(config=config, home=home, env=env)
    fallback = str(rt.provider or "openrouter")
    if current not in {"", "auto"}:
        fallback = current

    registry = ModelRegistry()
    if ":" in stripped:
        prov, mid = parse_model_input(stripped, fallback)
        prov_arg = None if prov in {"", "auto"} else prov
    else:
        mid = stripped
        # ``anthropic/foo`` (no colon) — let resolve infer provider (pi-style full id).
        if "/" in mid:
            prov_arg = None
        else:
            prov_arg = None if fallback in {"", "auto"} else fallback

    resolved = registry.resolve(model=mid, provider=prov_arg)

    mcfg["default"] = resolved.id
    if ":" in stripped or "/" in stripped:
        mcfg["provider"] = resolved.provider
    return mcfg
