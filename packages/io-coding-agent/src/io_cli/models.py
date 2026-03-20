"""Model selection helpers."""

from __future__ import annotations

from io_ai import ModelRegistry, provider_label, provider_model_ids


def list_models(provider: str | None = None, *, detailed: bool = False) -> list[object]:
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
