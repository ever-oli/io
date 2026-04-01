<p align="center">
  <img src="github_banner.png" alt="IO" width="100%" />
</p>

# IO

A professional-grade AI coding harness engineered for the modern development workflow.

**Version:** `0.3.0` — Production-ready

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/ever-oli/io/main/scripts/install.sh | bash
```

Works on Linux, macOS, and WSL2. The installer handles `uv`, Python, Node.js, dependencies, the git checkout in `~/.io/io`, and the `io` command. No prerequisites except git.

On Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/ever-oli/io/main/scripts/install.ps1 | iex
```

Provider credentials live in `~/.io/.env`, and default model/runtime settings live in `~/.io/config.yaml`.

After install:

```bash
source ~/.bashrc    # reload shell (or: source ~/.zshrc)
io                  # start chatting
```

## Getting Started

```bash
io                  # Interactive CLI
io auth status      # Check provider auth status
io config show      # Inspect merged config
io gateway setup    # Configure messaging defaults
io gateway run      # Run the messaging gateway
io update           # Update to the latest version
io doctor           # Print a diagnostic report
```

To update an install created this way:

```bash
io update
```

## Source / Dev Install

```bash
uv sync
uv run io --help
uv run io chat
uv run pytest
```

## Overview

IO is an advanced AI coding assistant designed for professional developers who demand precision, flexibility, and comprehensive tooling. Built on a robust 8-package architecture, IO delivers a complete development environment that seamlessly integrates AI capabilities into existing workflows.

### Design Philosophy

IO synthesizes proven patterns from industry-leading tools while maintaining architectural independence:

- **Hermes Architecture**: Command routing and gateway patterns for multi-platform messaging
- **Clean-Room Implementation**: Original Python codebase optimized for the Python ecosystem
- **Professional Standards**: Enterprise-grade security, audit trails, and permission systems

## Architecture

| Package | Purpose |
|---------|---------|
| `io-ai` | Multi-provider LLM runtime, model registry, authentication, cost tracking |
| `io-agent-core` | Agent loop, tool execution, event system, session management |
| `io-coding-agent` | CLI interface, REPL, session manager, built-in tools |
| `io-tui` | Terminal UI components (prompt_toolkit, Rich) |
| `io-web-ui` | FastAPI web runtime and browser chat interface |
| `io-pods` | Local pod lifecycle management and vLLM orchestration |
| `io-bot` | Telegram bot, morning briefings, notification system |
| `io-swarm` | Workflow swarm management, Lean formalization, background agents |

## Core Capabilities

| Feature | Description |
|---------|-------------|
| **Multiline REPL** | Multiple input modes: `single_ctrl_j` (default), `meta_submit`, or `buffer` |
| **Token Streaming** | Real-time response streaming via `io_ai.stream` |
| **Tool Execution** | Streaming output for shell commands and file operations |
| **SIGINT Handling** | Graceful interruption with `Agent.interrupt_requested` |
| **Plan Mode** | Structured step-by-step task execution with checkpointing |
| **Memory System** | Cross-session persistence with automatic extraction |
| **Smart Compression** | Intelligent context compaction for long sessions |
| **Permission System** | AI-powered risk classification with configurable policies |
| **Sub-Agents** | 8 specialized agent types for complex multi-step tasks |
| **MCP Integration** | Full Model Context Protocol support for external tools |
| **Session Management** | Fork, snapshot, teleport, and rewind capabilities |
| **Browser Automation** | Chrome/CDP integration for web testing |
| **Task System** | Background async task execution |
| **Bug Hunter** | Automated security and code smell detection |
| **Auto-Fix** | Automated linting and formatting corrections |
| **LSP Integration** | Full Language Server Protocol support for code intelligence |
| **Todo Management** | Session-scoped task tracking |
| **Brief Mode** | Concise response toggle |
| **Context Viz** | Visual session state representation |
| **Notebook Support** | Jupyter notebook editing and execution |
| **Cost Tracking** | Budget monitoring with alerts and detailed breakdowns |
| **IDE Integration** | Native support for VS Code, JetBrains, Cursor, and Windsurf |
| **Voice Interface** | Speech-to-text and text-to-speech capabilities |
| **Analytics** | Comprehensive usage tracking and insights |

## REPL Commands

```bash
# Plan Mode - Structured execution
/plan create "Refactor Auth" | extract auth module | update imports | add tests
/plan next
/plan show

# Memory - Cross-session persistence
/memory add "I prefer Python over JavaScript"
/memory search "programming preferences"

# Todo Management
/todo add "Fix authentication bug"
/todo clear

# Context Management
/compact                    # Manual context compression
/context                   # Visualize session state
/context add <file>        # Add file to context
/context remove <file>     # Remove file from context

# Session Control
/resume                    # List and resume sessions
/resume fork               # Fork current session
/resume rewind             # Rewind session
/export <file.md>          # Export session
/import <file.md>          # Import session

# File Operations
/diff                      # Show git diff
/diff <file>               # Show file diff
/rewind <file>             # List/restore file versions

# Skills & Tools
/skills                    # List available skills
/skills describe <name>    # Show skill details
/skills run <name>         # Execute skill

# MCP (Model Context Protocol)
/mcp connect <name> <url>  # Connect to MCP server
/mcp list                  # List MCP resources/tools

# Permissions & Safety
/permissions               # Show permission rules
/permissions allow <tool>  # Allow tool
/permissions deny <tool>   # Block tool
/permissions mode auto     # Enable AI auto-classification

# Browser Automation
/chrome navigate <url>     # Navigate to URL
/chrome screenshot         # Capture screenshot
/chrome click <selector>   # Click element
/chrome type <selector>    # Type text

# Brief Mode
/brief on                  # Enable concise responses
/brief off                 # Disable brief mode

# Utilities
/undo, /retry, /sessions, /status, /clear, /copy

# IDE Integration (VS Code, JetBrains, Cursor, Windsurf)
/ide status                          # Check available IDEs
/ide connect vscode                  # Connect to specific IDE
/ide open src/main.py 42             # Open file at line 42
/ide diff src/main.py                # Show diff in IDE

# Voice Support (STT/TTS)
/voice record 10                     # Record 10 seconds
/voice transcribe                    # Transcribe to text
/voice speak "Hello world"           # Text-to-speech
/voice config                        # Configure voice settings

# Analytics & Insights
/analytics report week               # Weekly usage report
/analytics insights                  # AI-powered usage insights
/analytics export json               # Export analytics data
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

## Tool Inventory

IO provides **55+ professional-grade tools** organized by domain:

### File and Code Operations
- `read`, `write`, `edit`, `patch` — File operations
- `search_files`, `grep`, `find`, `ls` — Search and discovery
- `diff` — Unified diff display
- `rewind` — File version management

### Terminal and Execution
- `bash`, `terminal`, `process` — Shell execution
- `task_create`, `task_list`, `task_stop` — Background task management

### Browser and Web
- `browser_navigate`, `browser_click`, `browser_type` — Chrome CDP automation
- `web_search`, `web_extract` — Web scraping and research

### Analysis and Quality Assurance
- `bughunter` — Security vulnerability and code smell detection
- `lsp`, `lsp_diagnostics` — Language server integration
- `autofix_pr` — Automated pull request fixing

### Memory and State Management
- `memory`, `nuggets` — Persistent memory systems
- `todo_write`, `todo_list` — Task tracking
- `plan_create`, `plan_list` — Plan management

### Communication and Integration
- `ask_user` — Interactive user prompts
- `agent`, `multi_agent` — Sub-agent orchestration
- `skill` — Dynamic skill execution

### MCP (Model Context Protocol)
- `mcp_connect`, `mcp_list`, `mcp_read`, `mcp_call`

### IDE Integration
- `ide_open`, `ide_diff`, `ide_sync_selection` — File operations
- `ide_status`, `ide_connect` — Connection management

### Voice Interface
- `voice_record`, `voice_transcribe`, `voice_speak` — Audio operations
- `voice_status`, `voice_config`, `voice_list_voices` — Configuration

### Analytics
- `analytics_report`, `analytics_status` — Reporting
- `analytics_export`, `analytics_insights` — Data analysis

## Configuration

### Model Selection

```bash
# Switch models interactively
/model anthropic:claude-3-5-sonnet-20241022

# Search available models
io models --search claude
```

Default provider: OpenRouter free tier

### Authentication

```bash
# GitHub Copilot integration
io auth copilot-login

# MCP server authentication
io auth mcp-login <server> <token>

# Check authentication status
io auth status
```

### Feature Configuration

Configure via `~/.io/config.yaml`:

```yaml
semantic:
  enabled: true
  repo_map: true

nuggets:
  auto_promote: true

soul:
  workspace_root: "/Users/you/workspace"

permissions:
  mode: "auto"  # Options: auto, accept_edits, accept_all, bypass, prompt

cost_tracking:
  daily_budget: 10.0      # USD
  alert_threshold: 0.8    # Alert at 80% of budget

voice:
  enabled: true
  stt_provider: "whisper"
  tts_provider: "system"
  auto_tts: false

analytics:
  enabled: true
  retention_days: 90
```

## Data Storage

IO maintains a structured data hierarchy in `~/.io/`:

| Component | Location | Purpose |
|-----------|----------|---------|
| **Nuggets** | `~/.io/nuggets/` | HRR vector semantic memory |
| **Memories** | `~/.io/memories/` | Cross-session memory snapshots |
| **Honcho** | External API | Optional external memory service |
| **Plans** | `~/.io/plans/` | Persistent task plans |
| **Sessions** | `~/.io/agent/sessions/` | Session history and state |
| **Backups** | `~/.io/backups/` | Automatic configuration backups |
| **Snapshots** | `~/.io/snapshots/` | Session checkpoints |
| **Tasks** | `~/.io/tasks/` | Background task queue |
| **Analytics** | `~/.io/analytics.db` | Usage statistics and metrics |

## Security

IO implements a comprehensive security model:

- **Tirith** — Command validation and sanitization for shell operations
- **AI-Powered Permissions** — Automated risk classification from safe to critical
- **Permission Modes** — Configurable policies: auto, accept_edits, accept_all, bypass, prompt
- **Approval Queue** — Structured approval workflows for sensitive operations

```bash
# Install Tirith security validator
io security tirith-install

# Run security diagnostics
io doctor
```

## Development

```
packages/          # 8 runtime packages
skills/            # Bundled skills
docs/              # Documentation
environments/      # Tool environments
tests/             # Test suite (50+ files)
scripts/           # Automation
```

**Tool install from the current checkout:**
```bash
uv tool install .
```

## Acknowledgments

IO draws inspiration from several industry-leading tools:

- **Hermes** — Gateway architecture and multi-platform messaging patterns
- **Claude Code** — Command structure and interaction design
- **pi-mono** — Clean architectural principles

IO extends these foundations with:
- Advanced memory systems (HRR vectors + Honcho integration)
- Multi-platform gateway ecosystem (8 messaging platforms)
- Comprehensive test coverage (50+ test files)
- Native Python ecosystem integration

## Documentation

- [`docs/`](docs/) — Architecture and feature documentation
- [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md) — Memory system architecture
- [`docs/ide-integration.md`](docs/ide-integration.md) — IDE setup and configuration
- [`docs/voice-interface.md`](docs/voice-interface.md) — Voice setup and providers
- [`docs/analytics.md`](docs/analytics.md) — Usage tracking and insights

## License

See repository for license details.
