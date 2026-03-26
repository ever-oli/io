from __future__ import annotations

import pytest

from io_ai import ModelRegistry, stream_simple
from io_ai.models import parse_model_input


def test_parse_model_input_ignores_colon_inside_openrouter_slug() -> None:
    """``:free`` suffix must not pair with config provider (copilot) and rewrite the model."""
    raw = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
    prov, mid = parse_model_input(raw, "copilot")
    assert prov == ""
    assert mid == raw


def test_parse_model_input_provider_colon_remote() -> None:
    prov, mid = parse_model_input("openrouter:nvidia/nemotron-3-super-120b-a12b:free", "copilot")
    assert prov == "openrouter"
    assert mid == "nvidia/nemotron-3-super-120b-a12b:free"


def test_parse_model_input_no_colon_uses_current_provider() -> None:
    prov, mid = parse_model_input("gpt-5.4", "openai")
    assert prov == "openai"
    assert mid == "gpt-5.4"


def test_model_registry_resolve_openrouter_slug_with_colon_not_forced_to_other_provider() -> None:
    registry = ModelRegistry()
    mid = "openrouter/nvidia/nemotron-3-super-120b-a12b:free"
    chosen = registry.resolve(model=mid, provider="copilot")
    assert chosen.provider == "openrouter"
    assert chosen.id == mid


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

