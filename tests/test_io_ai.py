from __future__ import annotations

import pytest

from io_ai import ModelRegistry, stream_simple


def test_model_registry_resolves_known_models() -> None:
    registry = ModelRegistry()
    model = registry.resolve(model="mock/io-test")
    assert model.provider == "mock"
    assert registry.resolve(provider="openai").provider == "openai"


@pytest.mark.asyncio
async def test_mock_provider_can_emit_tool_calls() -> None:
    response = await stream_simple(
        [{"role": "user", "content": 'TOOL[ls] {"path": "."}'}],
        model="mock/io-test",
        provider="mock",
        tools=[{"name": "ls", "description": "list", "input_schema": {"type": "object", "properties": {}}}],
    )
    assert response.tool_calls
    assert response.tool_calls[0].name == "ls"

