"""OpenRouter-compatible responses provider."""

from __future__ import annotations

from io_ai.types import CompletionRequest

from .openai_responses import OpenAIResponsesProvider


class OpenRouterProvider(OpenAIResponsesProvider):
    name = "openrouter"

    async def complete(self, request: CompletionRequest):
        request.settings.setdefault("base_url", "https://openrouter.ai/api/v1")
        return await super().complete(request)

