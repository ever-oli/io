<p align="center">
  <img src="github_banner.png" alt="IO" width="100%" />
</p>

# IO

IO is a clean-room Python rewrite combining the best of [pi-mono](https://github.com/badlogic/pi-mono) and Hermes, organized as an 8-package monorepo for AI agents and coding assistants.

**Version:** `0.3.0` — Production-ready

## Packages

| Package | Purpose |
|---------|---------|
| `io-ai` | Multi-provider LLM runtime, model registry, auth, cost tracking |
| `io-agent-core` | Agent loop, tools, events, session management |
| `io-coding-agent` | CLI, REPL, session manager, built-in tools |
| `io-tui` | Terminal UI components (prompt_toolkit, Rich) |
| `io-web-ui` | FastAPI web runtime and browser chat |
| `io-pods` | Local pod lifecycle and vLLM management |
| `io-bot` | Telegram bot, morning briefings, notifications |
| `io-swarm` | Workflow swarm management, Lean formalization, background agents |

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

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Multiline REPL** | `single_ctrl_j` (default), `meta_submit`, or `buffer` modes |
| **Token Streaming** | Real-time streaming via `io_ai.stream` |
| **Tool Execution** | Streaming output for `terminal` / `bash` |
| **SIGINT Handling** | Graceful interruption with `Agent.interrupt_requested` |
| **Plan Mode** | Structured step-by-step task execution |
| **Memory System** | Cross-session persistence with auto-extraction |
| **Smart Compression** | Intelligent context compaction |
| **Permission System** | Granular tool controls with profiles |
| **Sub-Agents** | 8 specialized agent types for complex tasks |

### REPL Commands

```bash
# Plan Mode - Structured execution
/plan create "Refactor Auth" | extract auth module | update imports | add tests
/plan next
/plan show

# Memory - Cross-session persistence
/memory add "I prefer Python over JavaScript"
/memory search "programming preferences"

# Context Management
/compact                    # Manual context compression

# Permissions
/permissions allow BashTool
/permissions deny "rm -rf *"

# Model & Provider
/model                      # Interactive picker
/provider                   # Interactive picker

# Utilities
/undo, /retry, /sessions, /status
```

### Gateways

**Telegram (Production-ready):**
```bash
io gateway setup telegram
io gateway run --platform telegram
```

**API Server (OpenAI-compatible):**
```bash
io gateway run --platform api-server  # http://127.0.0.1:8642
```

**Experimental:** Discord, WhatsApp, Slack, Signal, Matrix, Email, SMS

### Workflow Swarm (io-swarm)

Background agent orchestration for Lean formalization:

```bash
io swarm prove "1+1=2" --project ~/my-lean
io swarm list
io swarm attach io-001
io swarm cancel io-001
```

### Morning Briefing

```bash
io briefing "AI news" "tech startups"
```

## Configuration

### Models

```bash
/model anthropic:claude-3-5-sonnet-20241022
io models --search claude
```

Default: OpenRouter free tier

### Authentication

```bash
io auth copilot-login      # GitHub Copilot
io auth mcp-login <server> <token>
io auth status
```

### Feature Flags

`~/.io/config.yaml`:
```yaml
semantic:
  enabled: true
  repo_map: true

nuggets:
  auto_promote: true

soul:
  workspace_root: "/Users/you/workspace"
```

## Memory Stack

- **Nuggets** — HRR vectors in `~/.io/nuggets/`
- **Memories** — Snapshots in `~/.io/memories/`
- **Honcho** — External memory API v3 (optional)
- **Plan Store** — `~/.io/plans/`
- **Session Store** — `~/.io/agent/sessions/`

## Security

- **Tirith** — Command validation for `bash`/`terminal`
- **Permission Profiles** — SAFE, PARANOID, PERMISSIVE
- **Approval Queue** — Tool execution workflows

```bash
io security tirith-install
io doctor
```

## Development

```
packages/          # 8 runtime packages
skills/            # Bundled skills
docs/              # Documentation
environments/      # Tool environments
tests/             # Test suite
scripts/           # Automation
```

**Global install:**
```bash
uv tool install .
```

## Documentation

- [`docs/`](docs/) — Architecture and features
- [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md) — Memory systems

## License

See repository for license details.
