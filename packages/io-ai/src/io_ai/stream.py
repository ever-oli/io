"""Streaming helpers for IO providers."""

from __future__ import annotations

from typing import Any

from .auth import AuthStore
from .cost import CostTracker
from .models import ModelRegistry
from .providers import get_provider
from .types import AssistantEvent, AssistantResponse, CompletionRequest


async def stream(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    registry: ModelRegistry | None = None,
    auth: AuthStore | None = None,
):
    registry = registry or ModelRegistry()
    auth = auth or AuthStore()
    model_ref = registry.resolve(model=model, provider=provider, base_url=base_url)
    request = CompletionRequest(
        model=model_ref,
        messages=messages,
        tools=tools or [],
        settings=settings or {},
        headers=auth.headers_for(model_ref.provider),
    )
    provider_client = get_provider(model_ref.provider)
    async for event in provider_client.stream(request):
        yield event


async def stream_simple(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    settings: dict[str, Any] | None = None,
    registry: ModelRegistry | None = None,
    auth: AuthStore | None = None,
    cost_tracker: CostTracker | None = None,
) -> AssistantResponse:
    final_response: AssistantResponse | None = None
    async for event in stream(
        messages,
        model=model,
        provider=provider,
        base_url=base_url,
        tools=tools,
        settings=settings,
        registry=registry,
        auth=auth,
    ):
        if event.type == "message_end":
            final_response = event.response
    if final_response is None:
        final_response = AssistantResponse()
    cost_tracker = cost_tracker or CostTracker()
    final_response.usage = cost_tracker.estimate(final_response.model or model or "mock/io-test", final_response.usage)
    return final_response

