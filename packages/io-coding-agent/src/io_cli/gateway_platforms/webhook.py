"""Generic webhook platform adapter.

Runs an aiohttp HTTP server that receives webhook POSTs from external
services (GitHub, GitLab, JIRA, Stripe, etc.), validates HMAC signatures,
transforms payloads into agent prompts, and routes responses back to the
source or to another configured platform.

Configuration lives in gateway config under platforms.webhook.extra.routes.
Each route defines:
  - events: which event types to accept (header-based filtering)
  - secret: HMAC secret for signature validation (REQUIRED)
  - prompt: template string formatted with the webhook payload
  - skills: optional list of skills to load for the agent
  - deliver: where to send the response (github_comment, telegram, etc.)
  - deliver_extra: additional delivery config (repo, pr_number, chat_id)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import re
import subprocess
import time
from typing import Any

try:
    from aiohttp import web

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    web = None  # type: ignore[assignment]

from ..gateway_models import Platform, PlatformConfig
from .base import BasePlatformAdapter, MessageEvent, MessageType, SendResult

logger = logging.getLogger(__name__)

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8644
_INSECURE_NO_AUTH = "INSECURE_NO_AUTH"


def check_webhook_requirements() -> bool:
    """Check if webhook adapter dependencies are available."""
    return AIOHTTP_AVAILABLE


class WebhookAdapter(BasePlatformAdapter):
    """Generic webhook receiver that triggers agent runs from HTTP POSTs."""

    def __init__(self, config: PlatformConfig):
        super().__init__(config, Platform.WEBHOOK)
        self._host: str = str(config.extra.get("host", DEFAULT_HOST))
        self._port: int = int(config.extra.get("port", DEFAULT_PORT))
        self._global_secret: str = str(config.extra.get("secret", ""))
        routes = config.extra.get("routes", {})
        self._routes: dict[str, dict[str, Any]] = routes if isinstance(routes, dict) else {}
        self._runner: web.AppRunner | None = None

        self._delivery_info: dict[str, dict[str, Any]] = {}
        self.gateway_runner = None
        self._seen_deliveries: dict[str, float] = {}
        self._idempotency_ttl = int(config.extra.get("idempotency_ttl_seconds", 3600))
        self._rate_counts: dict[str, list[float]] = {}
        self._rate_limit = int(config.extra.get("rate_limit", 30))
        self._max_body_bytes = int(config.extra.get("max_body_bytes", 1_048_576))

    async def connect(self) -> bool:
        if not AIOHTTP_AVAILABLE:
            logger.error("[webhook] aiohttp is not installed")
            return False

        for name, route in self._routes.items():
            if not isinstance(route, dict):
                continue
            secret = str(route.get("secret", self._global_secret) or "")
            if not secret:
                raise ValueError(
                    f"[webhook] Route '{name}' has no HMAC secret. "
                    f"Set route secret or global secret. "
                    f"Set '{_INSECURE_NO_AUTH}' only for local testing."
                )

        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_post("/webhooks/{route_name}", self._handle_webhook)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        self._mark_connected()
        return True

    async def disconnect(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        self._mark_disconnected()

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SendResult:
        del reply_to
        del metadata
        delivery = self._delivery_info.pop(chat_id, {})
        deliver_type = str(delivery.get("deliver", "log"))
        if deliver_type == "log":
            logger.info("[webhook] Response for %s: %s", chat_id, content[:200])
            return SendResult(success=True)
        if deliver_type == "github_comment":
            return await self._deliver_github_comment(content, delivery)
        if self.gateway_runner and deliver_type in {"telegram", "discord", "slack", "signal", "sms"}:
            return await self._deliver_cross_platform(deliver_type, content, delivery)
        return SendResult(success=False, error=f"Unknown deliver type: {deliver_type}")

    async def _handle_health(self, request: web.Request) -> web.Response:
        del request
        return web.json_response({"status": "ok", "platform": "webhook"})

    async def _handle_webhook(self, request: web.Request) -> web.Response:
        route_name = request.match_info.get("route_name", "")
        route_config = self._routes.get(route_name)
        if not isinstance(route_config, dict):
            return web.json_response({"error": f"Unknown route: {route_name}"}, status=404)

        content_length = request.content_length or 0
        if content_length > self._max_body_bytes:
            return web.json_response({"error": "Payload too large"}, status=413)

        now = time.time()
        window = self._rate_counts.setdefault(route_name, [])
        window[:] = [t for t in window if now - t < 60]
        if len(window) >= self._rate_limit:
            return web.json_response({"error": "Rate limit exceeded"}, status=429)
        window.append(now)

        try:
            raw_body = await request.read()
        except Exception:
            return web.json_response({"error": "Bad request"}, status=400)

        secret = str(route_config.get("secret", self._global_secret) or "")
        if secret and secret != _INSECURE_NO_AUTH and not self._validate_signature(request, raw_body, secret):
            return web.json_response({"error": "Invalid signature"}, status=401)

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            try:
                import urllib.parse

                payload = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8")))
            except Exception:
                return web.json_response({"error": "Cannot parse body"}, status=400)

        event_type = (
            request.headers.get("X-GitHub-Event", "")
            or request.headers.get("X-GitLab-Event", "")
            or str(payload.get("event_type", ""))
            or "unknown"
        )
        allowed_events = route_config.get("events", [])
        if isinstance(allowed_events, list) and allowed_events and event_type not in allowed_events:
            return web.json_response({"status": "ignored", "event": event_type})

        prompt = self._render_prompt(
            str(route_config.get("prompt", "")),
            payload if isinstance(payload, dict) else {"payload": payload},
            event_type,
            route_name,
        )

        skills = route_config.get("skills", [])
        if isinstance(skills, list) and skills:
            try:
                from io_cli.agent.skill_commands import build_skill_invocation_message, get_skill_commands

                skill_cmds = get_skill_commands()
                for skill_name in skills:
                    cmd_key = f"/{skill_name}"
                    if cmd_key in skill_cmds:
                        skill_content = build_skill_invocation_message(cmd_key, user_instruction=prompt)
                        if skill_content:
                            prompt = skill_content
                            break
            except Exception as exc:
                logger.warning("[webhook] Skill loading failed: %s", exc)

        delivery_id = request.headers.get(
            "X-GitHub-Delivery",
            request.headers.get("X-Request-ID", str(int(time.time() * 1000))),
        )
        self._seen_deliveries = {
            key: ts for key, ts in self._seen_deliveries.items() if now - ts < self._idempotency_ttl
        }
        if delivery_id in self._seen_deliveries:
            return web.json_response({"status": "duplicate", "delivery_id": delivery_id}, status=200)
        self._seen_deliveries[delivery_id] = now

        session_chat_id = f"webhook:{route_name}:{delivery_id}"
        deliver_extra = route_config.get("deliver_extra", {})
        rendered_extra = (
            self._render_delivery_extra(deliver_extra, payload if isinstance(payload, dict) else {})
            if isinstance(deliver_extra, dict)
            else {}
        )
        self._delivery_info[session_chat_id] = {
            "deliver": str(route_config.get("deliver", "log")),
            "deliver_extra": rendered_extra,
            "payload": payload,
        }

        source = self.build_source(
            chat_id=session_chat_id,
            chat_name=f"webhook/{route_name}",
            chat_type="webhook",
            user_id=f"webhook:{route_name}",
            user_name=route_name,
        )
        event = MessageEvent(
            text=prompt,
            message_type=MessageType.TEXT,
            source=source,
            raw_message=payload,
            message_id=delivery_id,
        )
        asyncio.create_task(self.handle_message(event))
        return web.json_response(
            {"status": "accepted", "route": route_name, "event": event_type, "delivery_id": delivery_id},
            status=202,
        )

    def _validate_signature(self, request: web.Request, body: bytes, secret: str) -> bool:
        gh_sig = request.headers.get("X-Hub-Signature-256", "")
        if gh_sig:
            expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(gh_sig, expected)
        gl_token = request.headers.get("X-Gitlab-Token", "")
        if gl_token:
            return hmac.compare_digest(gl_token, secret)
        generic_sig = request.headers.get("X-Webhook-Signature", "")
        if generic_sig:
            expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
            return hmac.compare_digest(generic_sig, expected)
        return False

    def _render_prompt(self, template: str, payload: dict[str, Any], event_type: str, route_name: str) -> str:
        if not template:
            truncated = json.dumps(payload, indent=2)[:4000]
            return f"Webhook event '{event_type}' on route '{route_name}':\n\n```json\n{truncated}\n```"

        def _resolve(match: re.Match[str]) -> str:
            key = match.group(1)
            value: Any = payload
            for part in key.split("."):
                if isinstance(value, dict):
                    value = value.get(part, f"{{{key}}}")
                else:
                    return f"{{{key}}}"
            if isinstance(value, (dict, list)):
                return json.dumps(value, indent=2)[:2000]
            return str(value)

        return re.sub(r"\{([a-zA-Z0-9_.]+)\}", _resolve, template)

    def _render_delivery_extra(self, extra: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        rendered: dict[str, Any] = {}
        for key, value in extra.items():
            rendered[key] = self._render_prompt(value, payload, "", "") if isinstance(value, str) else value
        return rendered

    async def _deliver_github_comment(self, content: str, delivery: dict[str, Any]) -> SendResult:
        extra = delivery.get("deliver_extra", {})
        if not isinstance(extra, dict):
            extra = {}
        repo = str(extra.get("repo", ""))
        pr_number = str(extra.get("pr_number", ""))
        if not repo or not pr_number:
            return SendResult(success=False, error="Missing repo or pr_number")
        try:
            result = subprocess.run(
                ["gh", "pr", "comment", pr_number, "--repo", repo, "--body", content],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return SendResult(success=True)
            return SendResult(success=False, error=(result.stderr or "").strip() or "gh pr comment failed")
        except FileNotFoundError:
            return SendResult(success=False, error="gh CLI not installed")
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    async def _deliver_cross_platform(
        self,
        platform_name: str,
        content: str,
        delivery: dict[str, Any],
    ) -> SendResult:
        if not self.gateway_runner:
            return SendResult(success=False, error="No gateway runner for cross-platform delivery")
        try:
            target_platform = Platform(platform_name)
        except ValueError:
            return SendResult(success=False, error=f"Unknown platform: {platform_name}")
        adapter = self.gateway_runner.adapters.get(target_platform)
        if adapter is None:
            return SendResult(success=False, error=f"Platform {platform_name} not connected")

        extra = delivery.get("deliver_extra", {})
        if not isinstance(extra, dict):
            extra = {}
        chat_id = str(extra.get("chat_id", ""))
        if not chat_id:
            home = self.gateway_runner.manager.load_config().get_home_channel(target_platform)
            if home is not None:
                chat_id = home.chat_id
        if not chat_id:
            return SendResult(success=False, error=f"No chat_id or home channel for {platform_name}")
        return await adapter.send(chat_id, content)

