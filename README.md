<p align="center">
  <img src="github_banner.png" alt="IO" width="100%" />
</p>

# IO

IO is a clean-room Python rewrite combining the best of [pi-mono](https://github.com/badlogic/pi-mono) and Hermes, organized as a 7-package monorepo for AI agents and coding assistants.

## Version

Current: `0.2.0` (2026-03-31) — Gotenks fusion complete! 8 packages with io-swarm (Gauss-style workflow orchestration).

## Packages

### Core 7 (pi-mono Architecture)

| Package | Purpose |
|---------|---------|
| `io-ai` | Multi-provider LLM runtime, model registry, auth, cost tracking |
| `io-agent-core` | Agent loop, tools, events, session management |
| `io-coding-agent` | CLI, REPL, session manager, built-in tools |
| `io-tui` | Terminal UI components (prompt_toolkit, Rich) |
| `io-web-ui` | FastAPI web runtime and browser chat |
| `io-pods` | Local pod lifecycle and vLLM management |
| `io-bot` | Telegram bot, morning briefings, notifications |

### Extension (Gauss-Inspired)

| Package | Purpose |
|---------|---------|
| `io-swarm` | **NEW** — Workflow swarm management, Lean formalization, background agents |

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

### Telegram Bot (Primary)

Fully working gateway for Telegram:

```bash
# Setup
io gateway setup telegram

# Run bot
io gateway run --platform telegram

# Check status
io gateway status
```

Supports:
- Direct messages and group chats
- Webhook or long-polling mode
- File attachments (photos, documents)
- Slash commands (`/model`, `/provider`, `/memory`, etc.)

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

### Additional Gateways (Experimental)

Code exists for: Discord, WhatsApp, Slack, Signal, Matrix, Mattermost, Email, SMS, Webhook, Home Assistant, DingTalk. These are **not fully tested** — Telegram is the stable, production-ready option.

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

### Workflow Swarm (io-swarm)

Background agent orchestration for Lean formalization — Gotenks fusion of IO and Gauss:

```bash
# Spawn proof agent
io swarm prove "1+1=2" --project ~/my-lean

# Draft declarations
io swarm draft "topic" --project ~/my-lean

# Formalize statement
io swarm formalize "theorem statement" --project ~/my-lean

# List running agents
io swarm list

# Attach to interactive agent (Ctrl-] to detach)
io swarm attach io-001

# Cancel agent
io swarm cancel io-001

# Manage projects
io project add my-proof ~/my-lean
io project list
```

**Features:**
- Background/foreground agent spawning
- PTY attach/detach (like `screen`/`tmux`)
- Project registry with `.gauss/project.yaml` support
- Trajectory compression for RL training
- Cosign release signing

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
packages/          # Runtime packages (8 total)
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

## Documentation

- [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md) — Memory systems
- [`docs/nuggets_parity.md`](docs/nuggets_parity.md) — Nuggets HRR parity
- [`docs/open_gauss_hermes_port.md`](docs/open_gauss_hermes_port.md) — Security & OpenGauss
- [`docs/gauss_new_user.md`](docs/gauss_new_user.md) — Getting started with Gauss
- [`docs/docker.md`](docs/docker.md) — Docker deployment

## License

See repository for license details.
