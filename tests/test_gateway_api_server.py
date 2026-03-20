from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from io_cli.gateway_models import PlatformConfig
from io_cli.gateway_platforms.api_server import AIOHTTP_AVAILABLE, APIServerAdapter


@pytest.mark.skipif(not AIOHTTP_AVAILABLE, reason="aiohttp is required for API server adapter tests")
class TestAPIServerAdapter:
    class _FakeRequest:
        def __init__(self, *, headers: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> None:
            self.headers = headers or {}
            self._body = body
            self.match_info: dict[str, str] = {}

        async def json(self) -> dict[str, Any]:
            if self._body is None:
                raise json.JSONDecodeError("invalid", "", 0)
            return self._body

    def test_models_requires_auth_when_key_configured(self) -> None:
        adapter = APIServerAdapter(PlatformConfig(enabled=True, extra={"key": "secret-key"}))
        request = self._FakeRequest(headers={})
        response = asyncio.run(adapter._handle_models(request))
        payload = json.loads(response.text)
        assert response.status == 401
        assert payload["error"]["code"] == "invalid_api_key"

    def test_responses_rejects_conversation_and_previous_response_id(self) -> None:
        adapter = APIServerAdapter(PlatformConfig(enabled=True))
        request = self._FakeRequest(
            body={
                "input": "hello",
                "conversation": "ops-room",
                "previous_response_id": "resp_abc",
            }
        )
        response = asyncio.run(adapter._handle_responses(request))
        payload = json.loads(response.text)
        assert response.status == 400
        assert "Cannot use both 'conversation' and 'previous_response_id'" in payload["error"]["message"]

    def test_responses_chains_state_by_conversation_name(self) -> None:
        adapter = APIServerAdapter(PlatformConfig(enabled=True))
        seen_histories: list[list[dict[str, str]]] = []

        async def fake_run_agent(**kwargs):
            history = list(kwargs["conversation_history"])
            seen_histories.append(history)
            return (
                {
                    "final_response": "ok",
                    "messages": [{"role": "assistant", "content": "ok"}],
                },
                {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
            )

        adapter._run_agent = fake_run_agent  # type: ignore[method-assign]

        first = self._FakeRequest(body={"input": "first message", "conversation": "ops-room"})
        first_response = asyncio.run(adapter._handle_responses(first))
        first_payload = json.loads(first_response.text)
        assert first_response.status == 200
        assert first_payload["id"].startswith("resp_")

        second = self._FakeRequest(body={"input": "second message", "conversation": "ops-room"})
        second_response = asyncio.run(adapter._handle_responses(second))
        assert second_response.status == 200

        assert len(seen_histories) == 2
        assert seen_histories[0] == []
        assert any(item.get("content") == "first message" for item in seen_histories[1])

    def test_chat_completions_extracts_user_message_and_history(self) -> None:
        adapter = APIServerAdapter(PlatformConfig(enabled=True))
        captured: dict[str, Any] = {}

        async def fake_run_agent(**kwargs):
            captured.update(kwargs)
            return (
                {"final_response": "done"},
                {"input_tokens": 5, "output_tokens": 2, "total_tokens": 7},
            )

        adapter._run_agent = fake_run_agent  # type: ignore[method-assign]

        request = self._FakeRequest(
            body={
                "model": "io-agent",
                "messages": [
                    {"role": "system", "content": "be precise"},
                    {"role": "user", "content": "first"},
                    {"role": "assistant", "content": "response"},
                    {"role": "user", "content": "latest"},
                ],
            }
        )
        response = asyncio.run(adapter._handle_chat_completions(request))
        payload = json.loads(response.text)

        assert response.status == 200
        assert captured["ephemeral_system_prompt"] == "be precise"
        assert captured["user_message"] == "latest"
        assert captured["conversation_history"] == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "response"},
        ]
        assert payload["choices"][0]["message"]["content"] == "done"
