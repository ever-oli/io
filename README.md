<p align="center">
  <img src="github_banner.png" alt="IO" width="100%" />
</p>

# IO

IO is a clean-room Python rewrite of the pi-mono repo and hermes , organized around
the core package boundaries lifted from pi-mono. I couldn't decide on one so why not both. 

## Version

Current milestone: `0.1.2` (2026-03-19) — Nuggets-style HRR memory parity, gateway surfaces, CLI hardening.

## Packages

- `io-ai`: provider runtime, model registry, auth, and cost tracking
- `io-agent-core`: agent loop, tools, events, and session index
- `io-tui`: generic prompt_toolkit and Rich terminal components
- `io-coding-agent`: CLI, session manager, extensions, and built-in tools
- `io-web-ui`: FastAPI web runtime and browser chat surface
- `io-pods`: persisted local pod lifecycle and vLLM management

### Holographic memory (Nuggets-style)

The `nuggets` tool provides **Holographic Reduced Representation (HRR)** memory
inspired by [Nuggets](https://github.com/NeoVertex1/nuggets) (MIT): facts live
under `~/.io/nuggets/` (per IO home) as small JSON files; recall is local
algebra on fixed-size vectors. Facts recalled often are merged into
`memories/MEMORY.md` (threshold 3) when `nuggets.auto_promote` is true in config.
The default vector dimension is large (`D=16384`); Python rebuild cost is higher
than the upstream TypeScript engine—use smaller `D` only for tests or light use.
Behavioral parity targets (PRNG goldens, Nuggets-style fuzzy keys, promotion header)
are documented in [`docs/nuggets_parity.md`](docs/nuggets_parity.md) with tests in
`tests/test_nuggets_parity.py`.

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

If `io` fails with `ModuleNotFoundError: No module named 'numpy'`, reinstall from this repo (`uv sync`) or `pip install numpy` into the **same environment** as the `io` executable (e.g. refresh a `pipx`/`pip --user` install). Holographic nuggets need NumPy when that tool is enabled.

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
