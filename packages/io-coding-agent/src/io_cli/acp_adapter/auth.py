"""ACP auth helpers for IO."""

from __future__ import annotations

import os
from pathlib import Path

from ..config import ensure_io_home, load_config, load_env
from ..runtime_provider import resolve_runtime_provider


def detect_provider(home: Path | None = None) -> str | None:
    """Resolve the active IO runtime provider, or ``None`` if unavailable."""

    io_home = ensure_io_home(home)
    try:
        runtime = resolve_runtime_provider(
            config=load_config(io_home),
            home=io_home,
            env={**load_env(io_home), **os.environ},
        )
        api_key = runtime.get("api_key")
        provider = runtime.get("provider")
        if isinstance(api_key, str) and api_key.strip() and isinstance(provider, str) and provider.strip():
            return provider.strip().lower()
    except Exception:
        return None
    return None


def has_provider(home: Path | None = None) -> bool:
    """Return ``True`` when IO can resolve any runtime credentials."""

    return detect_provider(home=home) is not None
