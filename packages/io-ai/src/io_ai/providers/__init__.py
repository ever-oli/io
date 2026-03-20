"""Provider registry."""

from __future__ import annotations

from io_ai.auth import PROVIDER_REGISTRY, canonical_provider_name
from io_ai.types import CompletionRequest

from .anthropic import AnthropicProvider
from .base import Provider
from .mock import MockProvider
from .openai_responses import OpenAIResponsesProvider
from .openrouter import OpenRouterProvider


class UnsupportedProvider(Provider):
    def __init__(self, name: str) -> None:
        self.name = name

    async def complete(self, request: CompletionRequest):
        raise NotImplementedError(
            f"Provider '{self.name}' requires an external runtime that is not wired into IO yet."
        )


_OPENAI_COMPAT = OpenAIResponsesProvider()

PROVIDERS: dict[str, Provider] = {
    "mock": MockProvider(),
    "openai": _OPENAI_COMPAT,
    "openrouter": OpenRouterProvider(),
    "anthropic": AnthropicProvider(),
    "custom": _OPENAI_COMPAT,
    "nous": _OPENAI_COMPAT,
    "openai-codex": _OPENAI_COMPAT,
    "copilot": _OPENAI_COMPAT,
    "zai": _OPENAI_COMPAT,
    "kimi-coding": _OPENAI_COMPAT,
    "minimax": _OPENAI_COMPAT,
    "minimax-cn": _OPENAI_COMPAT,
    "deepseek": _OPENAI_COMPAT,
    "ai-gateway": _OPENAI_COMPAT,
    "opencode-zen": _OPENAI_COMPAT,
    "opencode-go": _OPENAI_COMPAT,
    "kilocode": _OPENAI_COMPAT,
    "alibaba": AnthropicProvider(),
    "copilot-acp": UnsupportedProvider("copilot-acp"),
}


def get_provider(name: str) -> Provider:
    canonical = canonical_provider_name(name) or name
    if canonical in PROVIDERS:
        return PROVIDERS[canonical]
    if canonical in PROVIDER_REGISTRY and PROVIDER_REGISTRY[canonical].api == "anthropic_messages":
        return PROVIDERS["anthropic"]
    if canonical in PROVIDER_REGISTRY:
        return _OPENAI_COMPAT
    raise KeyError(f"Unknown provider: {name}")


__all__ = [
    "AnthropicProvider",
    "CompletionRequest",
    "MockProvider",
    "OpenAIResponsesProvider",
    "OpenRouterProvider",
    "Provider",
    "PROVIDERS",
    "UnsupportedProvider",
    "get_provider",
]
