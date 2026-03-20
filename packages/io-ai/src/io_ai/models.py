"""Model registry for IO."""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import ModelRef


DEFAULT_MODELS: tuple[ModelRef, ...] = (
    ModelRef(
        id="mock/io-test",
        provider="mock",
        api="mock",
        remote_id="io-test",
        label="Mock IO Test",
        metadata={"recommended": True},
    ),
    ModelRef(
        id="openai/gpt-5-mini",
        provider="openai",
        api="responses",
        remote_id="gpt-5-mini",
        label="OpenAI GPT-5 Mini",
    ),
    ModelRef(
        id="openrouter/openai/gpt-5-mini",
        provider="openrouter",
        api="responses",
        remote_id="openai/gpt-5-mini",
        label="OpenRouter GPT-5 Mini",
        base_url="https://openrouter.ai/api/v1",
    ),
    ModelRef(
        id="anthropic/claude-sonnet-4-5",
        provider="anthropic",
        api="messages",
        remote_id="claude-sonnet-4-5-latest",
        label="Claude Sonnet 4.5",
    ),
)


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

    def default_for(self, provider: str | None = None) -> ModelRef:
        if provider:
            for model in self.list():
                if model.provider == provider:
                    return model
        return self.models["mock/io-test"]

    def resolve(
        self,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
    ) -> ModelRef:
        if model:
            if model in self.models:
                chosen = self.models[model]
            elif provider and f"{provider}/{model}" in self.models:
                chosen = self.models[f"{provider}/{model}"]
            else:
                matches = [item for item in self.models.values() if item.remote_id == model]
                if matches:
                    chosen = matches[0]
                else:
                    raise KeyError(f"Unable to resolve model '{model}'")
        else:
            chosen = self.default_for(provider)

        if provider and chosen.provider != provider:
            candidates = [
                item
                for item in self.models.values()
                if item.provider == provider and (item.remote_id == chosen.remote_id or item.id == model)
            ]
            if candidates:
                chosen = candidates[0]

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

