"""Codex model discovery from API, local cache, and config."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional


logger = logging.getLogger(__name__)

DEFAULT_CODEX_MODELS: list[str] = [
    "gpt-5.3-codex",
    "gpt-5.2-codex",
    "gpt-5.1-codex-max",
    "gpt-5.1-codex-mini",
]

_FORWARD_COMPAT_TEMPLATE_MODELS: list[tuple[str, tuple[str, ...]]] = [
    ("gpt-5.3-codex", ("gpt-5.2-codex",)),
    ("gpt-5.4", ("gpt-5.3-codex", "gpt-5.2-codex")),
    ("gpt-5.3-codex-spark", ("gpt-5.3-codex", "gpt-5.2-codex")),
]


def _add_forward_compat_models(model_ids: list[str]) -> list[str]:
    """Add synthetic forward-compatible Codex slugs when older templates exist."""

    ordered: list[str] = []
    seen: set[str] = set()
    for model_id in model_ids:
        if model_id not in seen:
            ordered.append(model_id)
            seen.add(model_id)

    for synthetic_model, template_models in _FORWARD_COMPAT_TEMPLATE_MODELS:
        if synthetic_model in seen:
            continue
        if any(template in seen for template in template_models):
            ordered.append(synthetic_model)
            seen.add(synthetic_model)

    return ordered


def _fetch_models_from_api(access_token: str) -> list[str]:
    """Fetch visible Codex models from the ChatGPT Codex API."""

    try:
        import httpx

        response = httpx.get(
            "https://chatgpt.com/backend-api/codex/models?client_version=1.0.0",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if response.status_code != 200:
            return []
        data = response.json()
        entries = data.get("models", []) if isinstance(data, dict) else []
    except Exception as exc:  # pragma: no cover - network failures are best-effort
        logger.debug("Failed to fetch Codex models from API: %s", exc)
        return []

    sortable: list[tuple[int, str]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        slug = slug.strip()
        if item.get("supported_in_api") is False:
            continue
        visibility = item.get("visibility", "")
        if isinstance(visibility, str) and visibility.strip().lower() in {"hide", "hidden"}:
            continue
        priority = item.get("priority")
        rank = int(priority) if isinstance(priority, (int, float)) else 10_000
        sortable.append((rank, slug))

    sortable.sort(key=lambda item: (item[0], item[1]))
    return _add_forward_compat_models([slug for _, slug in sortable])


def _read_default_model(codex_home: Path) -> Optional[str]:
    config_path = codex_home / "config.toml"
    if not config_path.exists():
        return None
    try:
        import tomllib
    except Exception:  # pragma: no cover - python >=3.11 always has tomllib
        return None
    try:
        payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    model = payload.get("model") if isinstance(payload, dict) else None
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def _read_cache_models(codex_home: Path) -> list[str]:
    cache_path = codex_home / "models_cache.json"
    if not cache_path.exists():
        return []
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    entries = raw.get("models") if isinstance(raw, dict) else None
    sortable: list[tuple[int, str]] = []
    if isinstance(entries, list):
        for item in entries:
            if not isinstance(item, dict):
                continue
            slug = item.get("slug")
            if not isinstance(slug, str) or not slug.strip():
                continue
            slug = slug.strip()
            if item.get("supported_in_api") is False:
                continue
            visibility = item.get("visibility")
            if isinstance(visibility, str) and visibility.strip().lower() in {"hide", "hidden"}:
                continue
            priority = item.get("priority")
            rank = int(priority) if isinstance(priority, (int, float)) else 10_000
            sortable.append((rank, slug))

    sortable.sort(key=lambda item: (item[0], item[1]))
    deduped: list[str] = []
    for _, slug in sortable:
        if slug not in deduped:
            deduped.append(slug)
    return deduped


def get_codex_model_ids(access_token: Optional[str] = None) -> list[str]:
    """Return available Codex model IDs from API, cache, and defaults."""

    codex_home_str = os.getenv("CODEX_HOME", "").strip() or str(Path.home() / ".codex")
    codex_home = Path(codex_home_str).expanduser()
    ordered: list[str] = []

    if access_token:
        api_models = _fetch_models_from_api(access_token)
        if api_models:
            return _add_forward_compat_models(api_models)

    default_model = _read_default_model(codex_home)
    if default_model:
        ordered.append(default_model)

    for model_id in _read_cache_models(codex_home):
        if model_id not in ordered:
            ordered.append(model_id)

    for model_id in DEFAULT_CODEX_MODELS:
        if model_id not in ordered:
            ordered.append(model_id)

    return _add_forward_compat_models(ordered)

