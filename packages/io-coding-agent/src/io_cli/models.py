"""Model selection helpers."""

from __future__ import annotations

from io_ai import ModelRegistry


def list_models() -> list[str]:
    registry = ModelRegistry()
    return [model.id for model in registry.list()]

