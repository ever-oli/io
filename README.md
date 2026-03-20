# IO

IO is a clean-room Python rewrite of the IO operating model, organized around
the seven core package boundaries lifted from pi-mono. The runtime and repo layout
are being expanded toward IO parity while keeping IO branding and package-native
Python internals.

## Version

Current milestone: `0.1.1` (gateway parity + improved CLI progress feedback).

## Packages

- `io-ai`: provider runtime, model registry, auth, and cost tracking
- `io-agent-core`: agent loop, tools, events, and session index
- `io-tui`: generic prompt_toolkit and Rich terminal components
- `io-coding-agent`: CLI, session manager, extensions, and built-in tools
- `io-web-ui`: FastAPI web runtime and browser chat surface
- `io-pods`: persisted local pod lifecycle and vLLM management

## Repo Layout

- `packages/`: runtime packages
- `skills/` and `optional-skills/`: bundled skill content
- `docs/`: operator and developer docs
- `scripts/`: repo automation
- `environments/`: tool/runtime environment definitions

## Development

```bash
uv sync
uv run io --help
uv run pytest
```

## Gateway Parity Surfaces

IO now ships the multi-platform gateway adapter stack, including:

- `telegram`
- `discord`
- `whatsapp`
- `slack`
- `signal`
- `mattermost`
- `matrix`
- `homeassistant`
- `email`
- `sms`
- `dingtalk`
- `api-server`
- `webhook`

Check runtime status:

```bash
uv run io gateway status
```

### API Server (OpenAI-compatible)

Enable and start the gateway with `api-server` to expose:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /health`

Default bind is `127.0.0.1:8642` (configurable via gateway platform extra config).

### Webhook Adapter

`webhook` provides an authenticated webhook ingress with:

- route-based event filtering
- HMAC signature validation
- idempotency for delivery retries
- rate limiting and payload size guardrails

Route handlers can template payload data into prompts and deliver agent output
to logs, GitHub PR comments (`gh pr comment`), or relay to connected messaging
platforms.
