from __future__ import annotations

from pathlib import Path

from io_cli.gateway_models import Platform, PlatformConfig
from io_cli.gateway_platforms.webhook import WebhookAdapter
from io_cli.gateway_runner import GatewayRunner
from io_cli.gateway_session import SessionSource


def test_webhook_adapter_renders_prompt_template() -> None:
    adapter = WebhookAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "routes": {
                    "github-pr": {
                        "secret": "test-secret",
                    }
                }
            },
        )
    )
    prompt = adapter._render_prompt(  # noqa: SLF001 - test validates direct-port behavior
        "PR {pull_request.number}: {pull_request.title} by {sender.login}",
        {
            "pull_request": {"number": 42, "title": "Add webhook parity"},
            "sender": {"login": "ever"},
        },
        "pull_request",
        "github-pr",
    )
    assert prompt == "PR 42: Add webhook parity by ever"


def test_webhook_adapter_renders_delivery_extra_templates() -> None:
    adapter = WebhookAdapter(
        PlatformConfig(
            enabled=True,
            extra={
                "routes": {
                    "github-pr": {
                        "secret": "test-secret",
                    }
                }
            },
        )
    )
    payload = {"repository": {"full_name": "ever/io"}, "pull_request": {"number": 7}}
    rendered = adapter._render_delivery_extra(  # noqa: SLF001 - test validates direct-port behavior
        {
            "repo": "{repository.full_name}",
            "pr_number": "{pull_request.number}",
            "chat_id": "ops-room",
        },
        payload,
    )
    assert rendered["repo"] == "ever/io"
    assert rendered["pr_number"] == "7"
    assert rendered["chat_id"] == "ops-room"


def test_gateway_runner_webhook_source_is_authorized(tmp_path: Path) -> None:
    runner = GatewayRunner(home=tmp_path / "home")
    source = SessionSource(
        platform=Platform.WEBHOOK,
        chat_id="webhook:github-pr:1",
        chat_name="webhook/github-pr",
        chat_type="webhook",
        user_id="webhook:github-pr",
        user_name="github-pr",
    )
    assert runner._is_user_authorized(source) is True  # noqa: SLF001 - behavior contract

