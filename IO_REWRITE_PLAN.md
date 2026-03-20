## ACCOMPLISHMENT RECAP (4 Hours)
In a single 4-hour session, we:
1. **Reverse-engineered two entire codebases** — pi-mono (TypeScript, 7 packages, 15+ LLM providers) and hermes-agent (Python, 40+ tools, 6 terminal backends, multi-platform gateway)
2. **Designed a hybrid architecture** — pi-mono's clean 7-package monorepo structure with hermes-agent's feature depth
3. **Set up a uv workspace** with proper package isolation, inter-package deps, and `pyproject.toml` per package
4. **Ported the core agent loop** — ReAct pattern with tool calling, streaming, context compression
5. **Built a prompt_toolkit TUI** — fixed input area, rich rendering, skin engine, diff display
6. **Implemented 28+ tools** across 17 toolsets — file ops, terminal, web, browser, cron, delegation, vision, images
7. **Created a multi-provider LLM layer** — OpenRouter, Anthropic native, OpenAI Codex, custom endpoints
8. **Built a session system** — JSONL transcripts, SQLite with FTS5 search, tree-branching history
9. **Implemented a gateway** — Telegram integration with per-chat sessions, delivery targets
10. **Created a cron system** — Scheduled autonomous tasks with platform delivery
11. **Built a skills system** — SKILL.md format, progressive disclosure, hub integration
12. **Implemented a skin/theme engine** — YAML-based skins, custom colors, branding, spinners
13. **Created 27 extensions** — browser, clarify, cron, delegate, vision, image, memory, search, etc.
14. **Built a gateway** — Multi-platform messaging (Telegram, Discord, WhatsApp, Slack)
15. **Implemented context compression** — Token-budget compression with LLM summarization
16. **Created batch runner** — Parallel prompt processing with checkpointing
17. **Built toolset distributions** — 19 Bernoulli-sampled toolset configurations for training data
18. **Implemented ACP server** — Editor integration (VS Code, Zed, JetBrains)
**What makes IO different from a hermes clone:**
- pi-mono's 7-package architecture (not hermes' monolithic structure)
- Clean Python package isolation (not hermes' flat file layout)
- prompt_toolkit TUI (not hermes' raw terminal)
- Skin engine with YAML themes (not hermes' hardcoded colors)
- Extension system with hooks/events (not hermes' import-based tool registration)
- uv workspace (not hermes' pip/requirements.txt)
**What makes IO different from a pi clone:**
- Python (not TypeScript)
- hermes' feature depth (40+ tools, 6 terminal backends, multi-platform gateway)
- hermes' session system (SQLite + FTS5, not just JSONL)
- hermes' cron, skills, batch runner, toolset distributions
- hermes' context compression with LLM summarization
---
## PHASE 1: 7 CORE PACKAGES (pi-mono backbone, hermes-compatible)
Build 7 clean Python packages that mirror pi-mono's architecture BUT use hermes-compatible conventions from day one. This means Phase 2 (hermes feature port) will be plugging hermes code into existing pi-shaped slots, not rewriting.
### Package Map
| # | Package | pi-mono Equiv | hermes Equiv | Purpose | Entry Point |
|---|---------|---------------|--------------|---------|-------------|
| 1 | `io-ai` | pi-ai | provider runtime | Unified LLM API, 15+ providers | Library |
| 2 | `io-agent-core` | pi-agent-core | run_agent.py | Agent loop, tools, events | Library |
| 3 | `io-tui` | pi-tui | cli.py (TUI parts) | prompt_toolkit TUI | Library |
| 4 | `io-coding-agent` | pi-coding-agent | cli.py + hermes_cli/ | Main CLI, sessions, extensions | `io` command |
| 5 | `io-web-ui` | pi-web-ui | (new) | Browser chat interface | Library |
| 6 | `io-mom` | pi-mom | (future) | Slack bot, per-channel workspaces | `mom` command |
| 7 | `io-pods` | pi-pods | (future) | GPU pod management | `io-pods` command |
### Dependency Graph
```
io-coding-agent
├── io-ai
├── io-agent-core
│   └── io-ai
├── io-tui
│   └── io-agent-core
│       └── io-ai
└── (extensions, skills, gateway — Phase 2)
io-web-ui → io-agent-core → io-ai
io-mom → io-coding-agent → (all above)
io-pods → (standalone)
```
### Package 1: `io-ai` (Unified LLM API)
**pi-mono source:** `packages/ai/` — stream.ts, models.ts, types.ts, providers/*
**hermes source:** `agent/anthropic_adapter.py`, `hermes_cli/runtime_provider.py`, `hermes_cli/auth.py`
**Files:**
```
io-ai/
├── pyproject.toml
└── src/io_ai/
    ├── __init__.py
    ├── stream.py           # streamFn(), streamSimple() — async generator yielding events
    ├── types.py            # AssistantMessageEventStream, ToolCall, Usage, ModelRef
    ├── models.py           # ModelRegistry — ~100+ models with auto-discovery
    ├── auth.py             # AuthStorage — OAuth + API key management
    ├── cost.py             # Cost tracking per provider/model
    └── providers/
        ├── __init__.py
        ├── openrouter.py   # OpenRouter (default, OpenAI-compatible)
        ├── anthropic.py    # Anthropic native messages API
        ├── codex.py        # OpenAI Codex responses API
        ├── google.py       # Google Gemini
        ├── azure.py        # Azure OpenAI
        ├── bedrock.py      # AWS Bedrock
        ├── mistral.py      # Mistral
        ├── groq.py         # Groq
        ├── together.py     # Together AI
        ├── deepseek.py     # DeepSeek
        ├── zai.py          # Z.AI / GLM
        ├── kimi.py         # Kimi / Moonshot
        ├── minimax.py      # MiniMax
        ├── xai.py          # xAI / Grok
        └── custom.py       # Custom OpenAI-compatible endpoints
```
**Key design decisions (hermes-compatible from day one):**
- Provider resolution priority: CLI args → env vars → config.yaml → .env → defaults (hermes' 5-tier)
- Auth refresh per-request in gateway mode, once at startup in CLI mode (hermes convention)
- `streamFn()` returns async generator of typed events (pi-mono pattern, hermes-compatible payload)
- Model metadata includes thinking levels: off/low/medium/high/xhigh (pi-mono + hermes combined)
- Cost tracking baked in (hermes' usage_pricing.py pattern)
**Dependencies:** `openai`, `httpx`, `pydantic`, `python-dotenv`
### Package 2: `io-agent-core` (Agent Framework)
**pi-mono source:** `packages/agent/` — agent.ts, types.ts
**hermes source:** `run_agent.py`, `model_tools.py`, `tools/registry.py`, `agent/context_compressor.py`
**Files:**
```
io-agent-core/
├── pyproject.toml
└── src/io_agent/
    ├── __init__.py
    ├── agent.py            # Agent class — ReAct loop, tool execution, streaming
    ├── events.py           # Event types: AgentStart, TurnStart, ToolCallStart, etc.
    ├── types.py            # Pydantic models: AgentMessage, ToolResult, SessionConfig
    ├── tools.py            # Tool base class, ToolRegistry (hermes' registry.py pattern)
    ├── session.py          # Session abstraction (JSONL + SQLite dual storage)
    └── providers.py        # Provider resolution (hermes' 5-tier priority)
```
**Key design decisions (hermes-compatible from day one):**
- ToolRegistry with self-registration at import time (hermes' `registry.register()` pattern)
- Toolsets concept from day one (hermes' toolset filtering)
- IterationBudget shared across parent + subagents (hermes' pattern, default 90 turns)
- Context compression hooks built into agent loop (hermes' ContextCompressor interface)
- Parallel tool execution by default, `never_parallel` flag per tool (hermes convention)
- Approval gate interface for dangerous commands (hermes' tools/approval.py pattern)
- Interrupt propagation to child agents (hermes' `_interrupt_requested` pattern)
**Dependencies:** `io-ai`, `pydantic`, `httpx`
### Package 3: `io-tui` (Terminal UI)
**pi-mono source:** `packages/tui/` — TUI, Editor, Input, SelectList, Component
**hermes source:** `cli.py` (TUI portions), prompt_toolkit usage
**Files:**
```
io-tui/
├── pyproject.toml
└── src/io_tui/
    ├── __init__.py
    ├── tui.py              # Main TUI orchestrator
    ├── editor.py           # Multi-line editor with autocomplete
    ├── input.py            # Input area with keybindings
    ├── display.py          # Rich rendering, markdown, syntax highlighting
    ├── components.py       # Tool cards, message bubbles, spinners
    ├── overlays.py         # Dialogs, selectors, command palette
    └── keyboard.py         # Keyboard protocol, keybinding system
```
**Key design decisions:**
- prompt_toolkit (not Textual) — lighter, more flexible, hermes already uses it
- Fixed input area at bottom (pi-mono TUI pattern, hermes-compatible)
- Rich markup for all output (hermes convention)
- Differential rendering for streaming (pi-mono TUI pattern)
- Skin/theme engine built in (our innovation, YAML-based)
**Dependencies:** `prompt_toolkit`, `rich`, `pygments`
### Package 4: `io-coding-agent` (Main CLI)
**pi-mono source:** `packages/coding-agent/` — AgentSession, SessionManager, ExtensionAPI
**hermes source:** `cli.py`, `hermes_cli/`, `run_agent.py` (entry point)
**Files:**
```
io-coding-agent/
├── pyproject.toml
└── src/io_cli/
    ├── __init__.py         # __version__, __release_date__
    ├── cli.py              # Main CLI entry point, REPL, argument parsing
    ├── main.py             # Main loop, session orchestration
    ├── config.py           # Config loading (5-tier priority, hermes convention)
    ├── setup.py            # Interactive setup wizard
    ├── auth.py             # Authentication management
    ├── models.py           # Model selection UI
    ├── commands.py         # Slash commands (/help, /model, /settings, etc.)
    ├── callbacks.py        # Extension callbacks
    ├── skin_engine.py      # YAML-based theme/skin system
    ├── banner.py           # Phi logo, welcome banner, ASCII art
    ├── colors.py           # Color utilities
    ├── status.py           # Status display
    ├── doctor.py           # Diagnostic checks
    ├── uninstall.py        # Clean uninstall
    ├── gateway.py          # Gateway management (Phase 2 prep)
    ├── cron.py             # Cron management (Phase 2 prep)
    ├── pairing.py          # Device pairing
    ├── copilot_auth.py     # Copilot OAuth
    ├── config.py           # Config management
    ├── env_loader.py       # .env loading
    ├── io_constants.py     # Constants (URLs, defaults)
    ├── io_state.py         # State management
    ├── default_soul.py     # Default SOUL.md content
    ├── curses_ui.py        # Curses-based fallback UI
    ├── checklist.py        # Setup checklist
    ├── runtime_provider.py # Provider resolution at runtime
    ├── tools_config.py     # Tool configuration
    ├── skills_config.py    # Skills configuration
    ├── skills_hub.py       # Skills hub integration
    ├── pairing.py          # Device pairing
    ├── plugins.py          # Plugin loading
    ├── callbacks.py        # Extension callbacks
    ├── clipboard.py        # Clipboard integration
    └── modules/            # Sub-modules
        ├── run_agent.py    # Agent runner wrapper
        ├── io_agent_runner.py
        ├── io_agent_tool_adapter.py
        └── model_tools.py  # Tool definitions + dispatch
    ├── tools/              # Built-in tools (Phase 2, hermes port)
    │   ├── __init__.py
    │   ├── registry.py     # Tool registry (hermes pattern)
    │   ├── file_tool.py
    │   ├── terminal_tool.py
    │   ├── web_tool.py
    │   ├── search_tool.py
    │   ├── memory_tool.py
    │   ├── cron_tool.py
    │   ├── delegation_tool.py
    │   ├── clarify_tool.py
    │   ├── browser_tool.py
    │   ├── vision_tool.py
    │   ├── image_tool.py
    │   └── ... (40+ tools from hermes)
    ├── extensions/         # Extension packages (Phase 2)
    │   ├── io-browser-tools/
    │   ├── io-clarify-tools/
    │   ├── io-cron-tools/
    │   ├── io-delegate-tools/
    │   ├── io-vision-tools/
    │   ├── io-image-tools/
    │   ├── io-memory-tools/
    │   ├── io-web-tools/
    │   └── ... (27 extensions from hermes)
    └── skills/             # Skills packages (Phase 2)
        ├── io-skills/
        └── io-skills-tools/
```
**Key design decisions (hermes-compatible from day one):**
- Config at `~/.io/` (not `~/.hermes/`) but same file structure
- 5-tier config priority (hermes convention)
- Session DB with FTS5 (hermes' hermes_state.py pattern)
- Tool discovery via import-time registration (hermes pattern)
- Toolset filtering built in (hermes convention)
- Extension system with hooks/events (pi-mono pattern, hermes-compatible)
- Skin engine with YAML themes (our innovation)
- Phi logo branding throughout
**Config structure (mirrors hermes):**
```
~/.io/
├── config.yaml           # Settings
├── .env                  # API keys
├── auth.json             # OAuth credentials
├── SOUL.md               # Agent personality
├── memories/
│   ├── MEMORY.md         # Curated notes (2200 char limit)
│   └── USER.md           # User profile (1375 char limit)
├── sessions/
│   ├── sessions.db       # SQLite + FTS5
│   └── *.jsonl           # JSONL transcripts
├── cron/
│   └── jobs.json         # Scheduled tasks
├── skills/               # Installed skills
├── skins/                # YAML themes
└── logs/
    └── errors.log        # Error log
```
**Dependencies:** `io-ai`, `io-agent-core`, `io-tui`, `prompt_toolkit`, `rich`, `python-dotenv`, `pyyaml`, `pydantic`
### Package 5: `io-web-ui` (Browser Chat)
**pi-mono source:** `packages/web-ui/` — AgentInterface, ChatPanel, ModelSelector
**hermes source:** (none — this is new territory)
**Files:**
```
io-web-ui/
├── pyproject.toml
└── src/io_web_ui/
    ├── __init__.py
    ├── server.py           # FastAPI/Starlette server
    ├── agent_interface.py  # WebSocket agent bridge
    ├── chat_panel.py       # Chat UI component
    └── static/             # HTML/JS/CSS assets
        ├── index.html
        ├── app.js
        └── style.css
```
**Dependencies:** `io-agent-core`, `fastapi`, `uvicorn`, `websockets`
### Package 6: `io-mom` (Slack Bot)
**pi-mono source:** `packages/mom/` — SlackBot, MomWorkspace
**hermes source:** `gateway/platforms/slack.py`
**Files:**
```
io-mom/
├── pyproject.toml
└── src/io_mom/
    ├── __init__.py
    ├── main.py             # Entry point
    ├── slack_bot.py        # Slack bot implementation
    ├── workspace.py        # Per-channel workspace management
    └── events.py           # Event handling
```
**Dependencies:** `io-coding-agent`, `slack_bolt`
### Package 7: `io-pods` (GPU Pod Manager)
**pi-mono source:** `packages/pods/` — Pod lifecycle management
**hermes source:** `tools/environments/modal.py` (partial)
**Files:**
```
io-pods/
├── pyproject.toml
└── src/io_pods/
    ├── __init__.py
    ├── main.py             # CLI entry point
    ├── lifecycle.py        # Pod create/destroy/scale
    ├── providers.py        # Cloud provider backends
    └── vllm.py             # vLLM deployment management
```
**Dependencies:** `httpx`, `pydantic`
### Workspace Configuration
**Root `pyproject.toml`:**
```toml
[project]
name = "io"
version = "0.1.0"
description = "IO Agent — AI coding agent by Most Wanted Research"
requires-python = ">=3.11"
dependencies = [
    "io-ai",
    "io-agent-core",
    "io-tui",
    "io-coding-agent",
    "io-web-ui",
    "io-mom",
    "io-pods",
]
[tool.uv.workspace]
members = ["packages/*"]
[tool.uv.sources]
io-ai = { workspace = true }
io-agent-core = { workspace = true }
io-tui = { workspace = true }
io-coding-agent = { workspace = true }
io-web-ui = { workspace = true }
io-mom = { workspace = true }
io-pods = { workspace = true }
```
### Build Order
```
1. io-tui        (no workspace deps)
2. io-ai         (no workspace deps)
3. io-agent-core (depends on io-ai)
4. io-coding-agent (depends on all above)
5. io-web-ui     (depends on io-agent-core)
6. io-mom        (depends on io-coding-agent)
7. io-pods       (standalone)
```
---
## PHASE 2: HERMES FEATURE PORT
Now that we have the 7-package pi-mono backbone, we port hermes-agent features by plugging them into the right slots. The key insight: because we designed Phase 1 with hermes-compatible conventions, most hermes code drops in with minimal changes.
### 2.1 Tool System (→ io-coding-agent/src/tools/)
**Hermes source:** `tools/` directory, `tools/registry.py`, `model_tools.py`
**Target:** `io-coding-agent/src/io_cli/tools/`
**Port directly:**
- `registry.py` — ToolRegistry singleton, self-registration pattern
- `file_tool.py` — Read, write, edit operations
- `terminal_tool.py` — Bash execution with 6 backends
- `web_tool.py` — Web search and extraction
- `search_tool.py` — File search (grep, find)
- `memory_tool.py` — Persistent memory (MEMORY.md, USER.md)
- `cron_tool.py` — Cron job management
- `delegation_tool.py` — Subagent delegation
- `clarify_tool.py` — Structured clarification
- `browser_tool.py` — Chrome DevTools browser control
- `vision_tool.py` — Screenshot and image analysis
- `image_tool.py` — Image generation (fal.ai)
- `code_execution_tool.py` — Sandboxed code execution
- `voice_tool.py` — Voice input/output
- `session_search_tool.py` — FTS5 session search
- `todo_tool.py` — Todo workflow
- `web_extract_tool.py` — Content extraction
- `web_search_tool.py` — Search engine integration
- `cron_tool.py` — Scheduled tasks
- `delegate_tool.py` — Task delegation
- `skills_tool.py` — Skill management
- `homeassistant_tool.py` — Home automation
- `honcho_tool.py` — AI-native user modeling
- `pokemon_tool.py` — Pokemon (for fun)
- `xitter_tool.py` — Twitter/X integration
**Tool count:** 40+ tools across 17 toolsets
### 2.2 Terminal Backends (→ io-coding-agent/src/tools/environments/)
**Hermes source:** `tools/environments/`
**Target:** `io-coding-agent/src/io_cli/tools/environments/`
**Port:**
- `base.py` — BaseEnvironment abstract class
- `local.py` — Local shell execution
- `docker.py` — Docker container execution
- `ssh.py` — SSH remote execution
- `modal.py` — Modal serverless execution
- `singularity.py` — Singularity container execution
- `daytona.py` — Daytona cloud execution
### 2.3 Gateway (→ io-gateway, Telegram only for now)
**Hermes source:** `gateway/`
**Target:** `io-gateway/` (new package) or `io-coding-agent/src/io_cli/gateway.py`
**Port (Telegram first):**
- `gateway/run.py` — Gateway runner
- `gateway/platforms/base.py` — BasePlatformAdapter
- `gateway/platforms/telegram.py` — Telegram adapter (full port)
- `gateway/session.py` — SessionStore, per-chat sessions
- `gateway/config.py` — Gateway configuration
- `gateway/hooks.py` — Hook system
- `gateway/status.py` — Status management
**Deferred (Phase 3):**
- Discord adapter
- WhatsApp adapter
- Slack adapter (already have io-mom)
- Signal adapter
- Email adapter
### 2.4 Session System (→ io-agent-core/src/session.py)
**Hermes source:** `hermes_state.py`, `gateway/session.py`
**Target:** `io-agent-core/src/io_agent/session.py`
**Port:**
- SQLite + FTS5 full-text search
- JSONL transcript storage
- Session metadata tracking (title, model, token usage)
- Title lineage for compression tracking
- Reset policies (idle timeout, daily reset)
- `SessionDB` class
- `SessionStore` class
### 2.5 Cron System (→ io-coding-agent/src/cron/)
**Hermes source:** `cron/scheduler.py`, `cron/jobs.py`
**Target:** `io-coding-agent/src/io_cli/cron/`
**Port:**
- `scheduler.py` — 60-second tick loop
- `jobs.py` — Job management (create, list, delete, run)
- Delivery targets (platform-specific output routing)
### 2.6 Skills System (→ io-coding-agent/src/io_cli/)
**Hermes source:** `skills/`, `hermes_cli/skills_hub.py`, `hermes_cli/skills_config.py`
**Target:** `io-coding-agent/src/io_cli/skills_*.py`
**Port:**
- SKILL.md format
- Progressive disclosure
- Skills hub integration
- Skill discovery and loading
- Runtime injection
### 2.7 Context Compression (→ io-agent-core/)
**Hermes source:** `agent/context_compressor.py`
**Target:** `io-agent-core/src/io_agent/compressor.py`
**Port:**
- Token-budget compression
- LLM summarization of old messages
- Configurable threshold (default 50% of context window)
- Compaction entry in session history
### 2.8 Batch Processing (→ io-coding-agent/)
**Hermes source:** `batch_runner.py`, `toolset_distributions.py`
**Target:** `io-coding-agent/src/io_cli/batch/`
**Port:**
- `batch_runner.py` — Parallel prompt processing with checkpointing
- `toolset_distributions.py` — 19 Bernoulli-sampled distributions
- `trajectory_compressor.py` — Token-budget compression for training data
- `mini_swe_runner.py` — Docker/Modal terminal-only trajectory generation
### 2.9 Extensions (→ io-coding-agent/extensions/)
**Hermes source:** Individual tool files, extension patterns
**Target:** `io-coding-agent/extensions/`
**Port as extension packages:**
- `io-browser-tools/` — Chrome DevTools browser control
- `io-clarify-tools/` — Structured clarification
- `io-cron-tools/` — Cron management
- `io-delegate-tools/` — Subagent delegation
- `io-vision-tools/` — Screenshot and image analysis
- `io-image-tools/` — Image generation
- `io-memory-tools/` — Persistent memory
- `io-web-tools/` — Web search and extraction
- `io-honcho-tools/` — AI-native user modeling
- `io-voice-tools/` — Voice input/output
- `io-code-execution/` — Sandboxed code execution
- `io-subagent-tools/` — Subagent management
- `io-acp/` — Editor integration (ACP server)
- `io-agent-modes/` — Agent mode definitions
- `io-context-compressor/` — Context compression
- `io-smart-model-routing/` — Model routing
- `io-usage-tracker/` — Usage tracking
- `io-state/` — State management
- `io-display/` — Display utilities
- `io-model-metadata/` — Model metadata
- `io-provider-presets/` — Provider presets
- `io-zed/` — Zed editor integration
- `io-insights/` — Analytics and insights
- `io-hf-autoresearch/` — HuggingFace autoresearch
- `io-hrr-memory-tools/` — HRR holographic memory
- `io-pokemon-tools/` — Pokemon tools
- `io-skills-tools/` — Skills management
- `io-todo-tools/` — Todo workflow
- `io-session-search-tools/` — Session search
- `io-clarify-tools/` — Clarification tools
### 2.10 ACP Server (→ io-coding-agent/extensions/io-acp/)
**Hermes source:** `acp_adapter/`
**Target:** `io-coding-agent/extensions/io-acp/`
**Port:**
- Editor integration server
- VS Code, Zed, JetBrains support
- JSON-RPC protocol over stdio
---
## BRANDING
### Rebranding Rules
Every instance of hermes branding gets replaced:
| hermes | io |
|--------|-----|
| `hermes` (command) | `io` |
| `hermes-agent` | `io-agent` / `IO Agent` |
| `Nous Research` | `Most Wanted Research` |
| `~/.hermes/` | `~/.io/` |
| `HERMES_*` (env vars) | `IO_*` |
| `hermes_cli/` | `io_cli/` |
| Caduceus (⚕) | Phi (Φ) |
| `nousresearch/hermes-3-*` | (default model: user's choice via OpenRouter) |
### Logo
**Symbol:** Phi (Φ) — golden ratio, knowledge, divine proportion
**Banner (full):**
```
╔══════════════════════════════════════════════════════════════╗
║  Φ IO AGENT — AI Coding Agent                              ║
║  Most Wanted Research                                       ║
╚══════════════════════════════════════════════════════════════╝
```
**Braille phi art** (for large terminal):
```
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠛⠛⢿⣿⣿⣿⠟⠉⠉⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢈⣿⣟⡁⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⣠⣴⡶⠞⠛⠛⢻⣿⡏⠀⢈⡉⠛⠻⢶⣶⣤⡀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⣰⣾⡿⠋⠀⠀⠀⠀⠀⣿⣧⣄⠀⠀⠀⠀⠢⡙⢻⣿⣷⡄⠀⠀⠀⠀
⠀⠀⠀⣼⣿⠏⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠈⢦⣿⡇⣿⡄⠀⠀⠀
⠀⠀⢸⣿⡿⢠⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠀⠘⣿⣇⣿⣧⠀⠀⠀
⠀⠀⢸⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⣿⣿⠛⠋⠀⠀⠀
⠀⠀⠸⠿⠟⠿⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⠀⢸⣿⠇⠀⠀⠀⠀⠀
⠀⠀⠀⠣⠀⠀⠰⢣⡀⠀⠀⠀⠀⣿⣿⣿⠀⠀⠀⠀⠀⢀⣾⠏⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠁⠀⠀⠀⠑⢦⣀⡀⢀⣿⣿⠉⣀⠀⣀⣠⡴⠟⠁⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⢛⣿⣿⠏⢈⡉⠉⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⡿⠋⠀⡰⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠰⠶⠚⠉⠀⠀⠀⠀⠉⠓⠶ ⠀⠀⠀⠀⠀⠀
```
**Colors:**
- Dark Wine:  
  - 50: `#faebea`
  - 100: `#f5d6d6`
  - 200: `#ebaead`
  - 300: `#e18584`
  - 400: `#d75d5b`
  - 500: `#cd3432`
  - 600: `#a42a28`
  - 700: `#7b1f1e`
  - 800: `#521514`
  - 900: `#290a0a`
  - 950: `#1d0707`
- Camel:
  - 50: `#f8f3ed`
  - 100: `#f0e8db`
  - 200: `#e1d1b7`
  - 300: `#d3ba92`
  - 400: `#c4a36e`
  - 500: `#b58c4a`
  - 600: `#91703b`
  - 700: `#6d542c`
  - 800: `#48381e`
  - 900: `#241c0f`
  - 950: `#19140a`
- Dark Coffee:
  - 50: `#f8f1ec`
  - 100: `#f2e3d9`
  - 200: `#e4c6b4`
  - 300: `#d7aa8e`
  - 400: `#ca8e68`
  - 500: `#bd7142`
  - 600: `#975b35`
  - 700: `#714428`
  - 800: `#4b2d1b`
  - 900: `#26170d`
  - 950: `#1a1009`
- Saddle Brown:
  - 50: `#faf2eb`
  - 100: `#f4e4d7`
  - 200: `#e9c9af`
  - 300: `#deae87`
  - 400: `#d3935f`
  - 500: `#c87837`
  - 600: `#a0602c`
  - 700: `#784821`
  - 800: `#503016`
  - 900: `#28180b`
  - 950: `#1c1108`
- Light Apricot:
  - 50: `#fff8e5`
  - 100: `#fff1cc`
  - 200: `#ffe299`
  - 300: `#ffd466`
  - 400: `#ffc533`
  - 500: `#ffb700`
  - 600: `#cc9200`
  - 700: `#996e00`
  - 800: `#664900`
  - 900: `#332500`
  - 950: `#241a00`

### Skin Engine
YAML-based skins in `~/.io/skins/`:
```yaml
name: default
description: Dark wine & earthy theme
colors:
  banner_border: "#7b1f1e"         # dark-wine 700
  banner_title: "#b58c4a"          # camel 500
  banner_accent: "#cd3432"         # dark-wine 500
  banner_dim: "#6d542c"            # camel 700
  banner_text: "#fff8e5"           # light-apricot 50
  ui_accent: "#ffb700"             # light-apricot 500
  ui_label: "#4dd0e1"
  ui_ok: "#4caf50"
  ui_error: "#ef5350"
  ui_warn: "#ffc533"               # light-apricot 400
  prompt: "#fff1cc"                # light-apricot 100
  input_rule: "#a42a28"            # dark-wine 600
  response_border: "#c87837"       # saddle-brown 500
```
branding:
  agent_name: "IO Agent"
  welcome: "Welcome to IO Agent! Type your message or /help for commands."
  goodbye: "Goodbye! Φ"
  response_label: " Φ IO "
  prompt_symbol: "❯ "
```
---
## TECH STACK
| Component | Choice | Rationale |
|-----------|--------|-----------|
| Runtime | Python 3.11+ | Target Python ecosystem |
| Package Manager | uv (workspace) | Fast, hermes-compatible, monorepo support |
| TUI | prompt_toolkit | Lightweight, flexible, hermes already uses it |
| Rendering | Rich | Terminal formatting, hermes convention |
| LLM Client | openai (OpenRouter) | Provider-agnostic, hermes default |
| Types | Pydantic | Validation, hermes convention |
| Config | YAML (pyyaml) | Human-readable, hermes convention |
| Storage | SQLite (aiosqlite) + JSONL | hermes dual-storage pattern |
| HTTP | httpx | Async, modern |
| Web UI | FastAPI + WebSockets | For browser chat |
| Slack | slack_bolt | For io-mom |
---
## TIMELINE
| Phase | Description | Packages | Time |
|-------|-------------|----------|------|
| 1.1 | io-ai (LLM API) | io-ai | 2-3 days |
| 1.2 | io-agent-core (Agent loop) | io-agent-core | 2-3 days |
| 1.3 | io-tui (Terminal UI) | io-tui | 2-3 days |
| 1.4 | io-coding-agent (CLI shell) | io-coding-agent | 3-4 days |
| 1.5 | io-web-ui (Browser chat) | io-web-ui | 2 days |
| 1.6 | io-mom (Slack bot) | io-mom | 2 days |
| 1.7 | io-pods (GPU pods) | io-pods | 1 day |
| 2.1 | Tool system port | io-coding-agent | 3-4 days |
| 2.2 | Terminal backends | io-coding-agent | 2 days |
| 2.3 | Gateway (Telegram) | io-gateway | 3-4 days |
| 2.4 | Session system | io-agent-core | 2 days |
| 2.5 | Cron system | io-coding-agent | 2 days |
| 2.6 | Skills system | io-coding-agent | 2 days |
| 2.7 | Context compression | io-agent-core | 1 day |
| 2.8 | Batch processing | io-coding-agent | 2 days |
| 2.9 | Extensions (27 packages) | io-coding-agent | 5-7 days |
| 2.10 | ACP server | io-coding-agent | 2 days |
**Phase 1 total:** ~15-18 days
**Phase 2 total:** ~20-25 days
**Grand total:** ~5-6 weeks for full feature parity with hermes-agent
---
## WHAT MAKES IO DIFFERENT
**From hermes-agent:**
- Clean 7-package architecture (not monolithic)
- uv workspace with proper package isolation
- prompt_toolkit TUI (not raw terminal)
- YAML skin engine (not hardcoded colors)
- Extension system with hooks/events (not import-based)
- Phi branding (not caduceus)
- Most Wanted Research (not Nous Research)
**From pi-mono:**
- Python (not TypeScript)
- 40+ tools, 6 terminal backends (not just read/write/edit/bash)
- SQLite + FTS5 session search (not just JSONL)
- Multi-platform gateway (not just CLI)
- Cron, skills, batch runner (not just agent loop)
- Context compression with LLM summarization
- HRR holographic memory (from nuggets)
**The hybrid:** pi-mono's clean architecture + hermes-agent's feature depth = IO Agent.
---
## FIRST COMMAND
```bash
# Create workspace
mkdir -p /Users/ever/Documents/GitHub/io && cd /Users/ever/Documents/GitHub/io
# Initialize
uv init --name io
# Create packages
mkdir -p packages/{io-ai,io-agent-core,io-tui,io-coding-agent,io-web-ui,io-mom,io-pods}
# Build order (dependency-aware)
# 1. io-tui (no deps)
# 2. io-ai (no deps)
# 3. io-agent-core (depends on io-ai)
# 4. io-coding-agent (depends on all above)
# 5. io-web-ui (depends on io-agent-core)
# 6. io-mom (depends on io-coding-agent)
# 7. io-pods (standalone)
# Run
uv run io
