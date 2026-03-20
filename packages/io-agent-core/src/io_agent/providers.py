"""Runtime provider resolution helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ResolvedRuntime:
    provider: str | None
    model: str
    base_url: str | None = None


def resolve_runtime(
    *,
    cli_provider: str | None = None,
    cli_model: str | None = None,
    cli_base_url: str | None = None,
    config: dict[str, Any] | None = None,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> ResolvedRuntime:
    env = env or dict(os.environ)
    config = config or {}
    provider = (
        cli_provider
        or env.get("IO_INFERENCE_PROVIDER")
        or config.get("model", {}).get("provider")
        or env.get("OPENROUTER_API_KEY")
        and "openrouter"
        or "mock"
    )
    model = (
        cli_model
        or env.get("IO_MODEL")
        or config.get("model", {}).get("default")
        or (
            "openrouter/openai/gpt-5-mini"
            if env.get("OPENROUTER_API_KEY") or env.get("OPENAI_API_KEY")
            else "mock/io-test"
        )
    )
    base_url = cli_base_url or env.get("IO_BASE_URL") or config.get("model", {}).get("base_url")
    return ResolvedRuntime(provider=provider, model=model, base_url=base_url)

