"""Provider registry."""

from __future__ import annotations

from io_ai.types import CompletionRequest

from .anthropic import AnthropicProvider
from .base import Provider
from .mock import MockProvider
from .openai_responses import OpenAIResponsesProvider
from .openrouter import OpenRouterProvider


PROVIDERS: dict[str, Provider] = {
    "mock": MockProvider(),
    "openai": OpenAIResponsesProvider(),
    "openrouter": OpenRouterProvider(),
    "anthropic": AnthropicProvider(),
}


def get_provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise KeyError(f"Unknown provider: {name}")
    return PROVIDERS[name]


__all__ = [
    "AnthropicProvider",
    "CompletionRequest",
    "MockProvider",
    "OpenAIResponsesProvider",
    "OpenRouterProvider",
    "Provider",
    "PROVIDERS",
    "get_provider",
]

