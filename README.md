# IO Agent

IO is a Python monorepo that combines pi-mono's package boundaries with Hermes-style
agent orchestration, tools, sessions, and configuration.

## Packages

- `io-ai`: provider runtime, model registry, auth, and cost tracking
- `io-agent-core`: agent loop, tools, events, and session index
- `io-tui`: generic prompt_toolkit and Rich terminal components
- `io-coding-agent`: CLI, session manager, extensions, and built-in tools
- `io-web-ui`: ASGI demo bridge and browser chat scaffold
- `io-mom`: Slack/workspace scaffold
- `io-pods`: pod lifecycle and vLLM scaffold

## Development

```bash
uv sync
uv run io --help
pytest
```

