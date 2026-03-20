# IO

IO is a clean-room Python rewrite of the IO operating model, organized around
the seven core package boundaries lifted from pi-mono. The runtime and repo layout
are being expanded toward IO parity while keeping IO branding and package-native
Python internals.

## Packages

- `io-ai`: provider runtime, model registry, auth, and cost tracking
- `io-agent-core`: agent loop, tools, events, and session index
- `io-tui`: generic prompt_toolkit and Rich terminal components
- `io-coding-agent`: CLI, session manager, extensions, and built-in tools
- `io-web-ui`: ASGI demo bridge and browser chat scaffold
- `io-mom`: Slack/workspace scaffold
- `io-pods`: pod lifecycle and vLLM scaffold

## Repo Layout

- `packages/`: runtime packages
- `skills/` and `optional-skills/`: bundled skill content
- `docs/`: operator and developer docs
- `website/` and `landingpage/`: browser-facing assets
- `assets/`: shared branding and static resources
- `scripts/`: repo automation
- `environments/`: tool/runtime environment definitions

## Development

```bash
uv sync
uv run io --help
uv run pytest
```
