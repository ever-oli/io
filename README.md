<p align="center">
  <img src="github_banner.png" alt="IO" width="100%" />
</p>

# IO

IO is a clean-room Python rewrite combining the best of [pi-mono](https://github.com/badlogic/pi-mono) and Hermes, organized as a 7-package monorepo for AI agents and coding assistants.

## Version

Current: `0.1.2` (2026-03-31) — Complete 7-package structure with Telegram bot, gateway surfaces, and Hermes-style parity.

## Packages

| Package | Purpose |
|---------|---------|
| `io-ai` | Multi-provider LLM runtime, model registry, auth, cost tracking |
| `io-agent-core` | Agent loop, tools, events, session management |
| `io-coding-agent` | CLI, REPL, session manager, built-in tools |
| `io-tui` | Terminal UI components (prompt_toolkit, Rich) |
| `io-web-ui` | FastAPI web runtime and browser chat |
| `io-pods` | Local pod lifecycle and vLLM management |
| `io-bot` | **NEW** — Telegram bot, morning briefings, notifications |

## Quick Start

```bash
# Install dependencies
uv sync

# Run the CLI
uv run io --help
uv run io chat

# Run tests
uv run pytest
```

## Features

### Hermes-style TUI Parity

| Feature | Status |
|---------|--------|
| Multiline REPL | `display.repl_multiline_mode`: `single_ctrl_j` (default), `meta_submit`, or `buffer` |
| Token streaming | `display.streaming` + `io_ai.stream` → REPL |
| Tool output streaming | `display.stream_tool_output` for `terminal` / `bash` |
| SIGINT handling | Sets `Agent.interrupt_requested` |
| Honcho memory | Honcho API v3 by default (opt-in) |
| Delegation tools | `delegate_task`, `execute_code` |
| Research workflow | `io research list`, `io research export`, `io research summary` |

### Gateway Platforms

Multi-platform bot adapter stack:

`telegram` `discord` `whatsapp` `slack` `signal` `mattermost` `matrix` `email` `sms` `api-server` `webhook`

```bash
# Check gateway status
io gateway status

# Start gateway
io gateway run --platform telegram
```

### API Server (OpenAI-compatible)

```bash
io gateway run --platform api-server
```

Exposes:
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /health`

Default: `127.0.0.1:8642`

### Morning Briefing (io-bot)

```bash
# Daily research briefings via Telegram
io briefing

# Custom topics
io briefing "AI news" "tech startups" "productivity"
```

Configure in `~/.config/io-bot/.env`:
```
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Personal SOUL

The agent's persona loads from (in order):

1. **Workspace** — First `soul.md` / `SOUL.md` found walking up from working directory
2. **Fallback** — `~/.io/SOUL.md`

Repo `soul.md` is `.gitignore`d. Copy `soul.example.md` to get started.

**Verify:** `io doctor` shows `soul_path` and `soul_source`

**For Telegram:** Set `soul.workspace_root` in `~/.io/config.yaml`:
```yaml
soul:
  workspace_root: "/Users/you/Documents/GitHub/io"
```

## Configuration

### Models & Providers

```bash
# Interactive model picker
/model

# Direct selection
/model anthropic:claude-3-5-sonnet-20241022

# Interactive provider picker
/provider

# List all models
io models
io models --search claude
```

Default: OpenRouter free tier (`openrouter/nvidia/nemotron-3-super-120b-a12b:free`)

### Authentication

**GitHub Copilot:**
```bash
io auth copilot-login      # Device code OAuth flow
io auth status             # Check copilot.logged_in
```

**MCP Servers:**
```bash
io auth mcp-login <server> <token>
io auth mcp-status
io auth mcp-logout <server>
```

Tokens saved to `~/.io/auth.json` and `~/.io/mcp_auth.json`.

### Feature Flags

In `~/.io/config.yaml`:
```yaml
semantic:
  enabled: true        # Semantic context injection
  repo_map: true       # Repository map context

nuggets:
  auto_promote: true   # Auto-promote nuggets to memories
```

Or via env: `IO_SEMANTIC_CONTEXT=1`, `IO_REPO_MAP_CONTEXT=1`

## Memory Stack

- **Nuggets** — Holographic Reduced Representation (HRR) memory in `~/.io/nuggets/`
- **Memories** — Traditional memory snapshots in `~/.io/memories/*.md`
- **Honcho** — Optional external memory (API v3)

Nuggets use fixed-size vectors (default `D=16384`). Frequently-recalled facts auto-promote to `memories/MEMORY.md` when `nuggets.auto_promote: true`.

See [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md)

## Security

- **Tirith scanning** — Optional command validation for `bash`/`terminal`
- **OpenGauss** — Security analysis tools
- **Approval queue** — Tool execution approval workflows

```bash
io security tirith-install    # Install Tirith to ~/.io/bin
io gauss ...                  # Security analysis
```

## Development

### Project Structure

```
packages/          # Runtime packages (7 total)
skills/            # Bundled skills
optional-skills/   # Optional skill content
docs/              # Documentation
environments/      # Tool/runtime environments
tests/             # Test suite
scripts/           # Repo automation
```

### Running IO Anywhere

**Option 1: Alias (recommended)**
```bash
# ~/.zshrc
alias io='uv run --directory /path/to/this/repo io'
```

**Option 2: Global install**
```bash
uv tool install .
# Ensure ~/.local/bin is on PATH
```

**Verify:**
```bash
command -v io    # Should show path to this repo's io
io --version
```

### IO vs Mario's `pi`

| Project | Type | Command |
|---------|------|---------|
| **This repo** | Python (uv) | `io` |
| `@mariozechner/pi-coding-agent` | Node/npm | `pi` |

If you have conflicts, ensure `~/.local/bin` (or your venv) comes before npm/Hombrew in PATH.

## Documentation

- [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md) — Memory systems
- [`docs/nuggets_parity.md`](docs/nuggets_parity.md) — Nuggets HRR parity
- [`docs/open_gauss_hermes_port.md`](docs/open_gauss_hermes_port.md) — Security & OpenGauss
- [`docs/gauss_new_user.md`](docs/gauss_new_user.md) — Getting started with Gauss
- [`docs/docker.md`](docs/docker.md) — Docker deployment

## License

See repository for license details.
