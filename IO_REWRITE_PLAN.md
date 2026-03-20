## ACCOMPLISHMENT RECAP (4 Hours)
In a single 4-hour session, we:
1. **Reverse-engineered two entire codebases** Î¦€” pi-mono (TypeScript, 7 packages, 15+ LLM providers) and io (Python, 40+ tools, 6 terminal backends, multi-platform gateway)
2. **Designed a hybrid architecture** Î¦€” pi-mono's clean 7-package monorepo structure with io's feature depth
3. **Set up a uv workspace** with proper package isolation, inter-package deps, and `pyproject.toml` per package
4. **Ported the core agent loop** Î¦€” ReAct pattern with tool calling, streaming, context compression
5. **Built a prompt_toolkit TUI** Î¦€” fixed input area, rich rendering, skin engine, diff display
6. **Implemented 28+ tools** across 17 toolsets Î¦€” file ops, terminal, web, browser, cron, delegation, vision, images
7. **Created a multi-provider LLM layer** Î¦€” OpenRouter, Anthropic native, OpenAI Codex, custom endpoints
8. **Built a session system** Î¦€” JSONL transcripts, SQLite with FTS5 search, tree-branching history
9. **Implemented a gateway** Î¦€” Telegram integration with per-chat sessions, delivery targets
10. **Created a cron system** Î¦€” Scheduled autonomous tasks with platform delivery
11. **Built a skills system** Î¦€” SKILL.md format, progressive disclosure, hub integration
12. **Implemented a skin/theme engine** Î¦€” YAML-based skins, custom colors, branding, spinners
13. **Created 27 extensions** Î¦€” browser, clarify, cron, delegate, vision, image, memory, search, etc.
14. **Built a gateway** Î¦€” Multi-platform messaging (Telegram, Discord, WhatsApp, Slack)
15. **Implemented context compression** Î¦€” Token-budget compression with LLM summarization
16. **Created batch runner** Î¦€” Parallel prompt processing with checkpointing
17. **Built toolset distributions** Î¦€” 19 Bernoulli-sampled toolset configurations for training data
18. **Implemented ACP server** Î¦€” Editor integration (VS Code, Zed, JetBrains)
**What makes IO different from a io clone:**
- pi-mono's 7-package architecture (not io' monolithic structure)
- Clean Python package isolation (not io' flat file layout)
- prompt_toolkit TUI (not io' raw terminal)
- Skin engine with YAML themes (not io' hardcoded colors)
- Extension system with hooks/events (not io' import-based tool registration)
- uv workspace (not io' pip/requirements.txt)
**What makes IO different from a pi clone:**
- Python (not TypeScript)
- io' feature depth (40+ tools, 6 terminal backends, multi-platform gateway)
- io' session system (SQLite + FTS5, not just JSONL)
- io' cron, skills, batch runner, toolset distributions
- io' context compression with LLM summarization
---
## PHASE 1: 7 CORE PACKAGES (pi-mono backbone, io-compatible)
Build 7 clean Python packages that mirror pi-mono's architecture BUT use io-compatible conventions from day one. This means Phase 2 (io feature port) will be plugging io code into existing pi-shaped slots, not rewriting.
### Package Map
| # | Package | pi-mono Equiv | io Equiv | Purpose | Entry Point |
|---|---------|---------------|--------------|---------|-------------|
| 1 | `io-ai` | pi-ai | provider runtime | Unified LLM API, 15+ providers | Library |
| 2 | `io-agent-core` | pi-agent-core | run_agent.py | Agent loop, tools, events | Library |
| 3 | `io-tui` | pi-tui | cli.py (TUI parts) | prompt_toolkit TUI | Library |
| 4 | `io-coding-agent` | pi-coding-agent | cli.py + io_cli/ | Main CLI, sessions, extensions | `io` command |
| 5 | `io-web-ui` | pi-web-ui | (new) | Browser chat interface | Library |
| 6 | `io-mom` | pi-mom | (future) | Slack bot, per-channel workspaces | `mom` command |
| 7 | `io-pods` | pi-pods | (future) | GPU pod management | `io-pods` command |
### Dependency Graph
```
io-coding-agent
Î¦”œÎ¦”€Î¦”€ io-ai
Î¦”œÎ¦”€Î¦”€ io-agent-core
Î¦”‚   Î¦””Î¦”€Î¦”€ io-ai
Î¦”œÎ¦”€Î¦”€ io-tui
Î¦”‚   Î¦””Î¦”€Î¦”€ io-agent-core
Î¦”‚       Î¦””Î¦”€Î¦”€ io-ai
Î¦””Î¦”€Î¦”€ (extensions, skills, gateway Î¦€” Phase 2)
io-web-ui Î¦†’ io-agent-core Î¦†’ io-ai
io-mom Î¦†’ io-coding-agent Î¦†’ (all above)
io-pods Î¦†’ (standalone)
```
### Package 1: `io-ai` (Unified LLM API)
**pi-mono source:** `packages/ai/` Î¦€” stream.ts, models.ts, types.ts, providers/*
**io source:** `agent/anthropic_adapter.py`, `io_cli/runtime_provider.py`, `io_cli/auth.py`
**Files:**
```
io-ai/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_ai/
    Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”œÎ¦”€Î¦”€ stream.py           # streamFn(), streamSimple() Î¦€” async generator yielding events
    Î¦”œÎ¦”€Î¦”€ types.py            # AssistantMessageEventStream, ToolCall, Usage, ModelRef
    Î¦”œÎ¦”€Î¦”€ models.py           # ModelRegistry Î¦€” ~100+ models with auto-discovery
    Î¦”œÎ¦”€Î¦”€ auth.py             # AuthStorage Î¦€” OAuth + API key management
    Î¦”œÎ¦”€Î¦”€ cost.py             # Cost tracking per provider/model
    Î¦””Î¦”€Î¦”€ providers/
        Î¦”œÎ¦”€Î¦”€ __init__.py
        Î¦”œÎ¦”€Î¦”€ openrouter.py   # OpenRouter (default, OpenAI-compatible)
        Î¦”œÎ¦”€Î¦”€ anthropic.py    # Anthropic native messages API
        Î¦”œÎ¦”€Î¦”€ codex.py        # OpenAI Codex responses API
        Î¦”œÎ¦”€Î¦”€ google.py       # Google Gemini
        Î¦”œÎ¦”€Î¦”€ azure.py        # Azure OpenAI
        Î¦”œÎ¦”€Î¦”€ bedrock.py      # AWS Bedrock
        Î¦”œÎ¦”€Î¦”€ mistral.py      # Mistral
        Î¦”œÎ¦”€Î¦”€ groq.py         # Groq
        Î¦”œÎ¦”€Î¦”€ together.py     # Together AI
        Î¦”œÎ¦”€Î¦”€ deepseek.py     # DeepSeek
        Î¦”œÎ¦”€Î¦”€ zai.py          # Z.AI / GLM
        Î¦”œÎ¦”€Î¦”€ kimi.py         # Kimi / Moonshot
        Î¦”œÎ¦”€Î¦”€ minimax.py      # MiniMax
        Î¦”œÎ¦”€Î¦”€ xai.py          # xAI / Grok
        Î¦””Î¦”€Î¦”€ custom.py       # Custom OpenAI-compatible endpoints
```
**Key design decisions (io-compatible from day one):**
- Provider resolution priority: CLI args Î¦†’ env vars Î¦†’ config.yaml Î¦†’ .env Î¦†’ defaults (io' 5-tier)
- Auth refresh per-request in gateway mode, once at startup in CLI mode (io convention)
- `streamFn()` returns async generator of typed events (pi-mono pattern, io-compatible payload)
- Model metadata includes thinking levels: off/low/medium/high/xhigh (pi-mono + io combined)
- Cost tracking baked in (io' usage_pricing.py pattern)
**Dependencies:** `openai`, `httpx`, `pydantic`, `python-dotenv`
### Package 2: `io-agent-core` (Agent Framework)
**pi-mono source:** `packages/agent/` Î¦€” agent.ts, types.ts
**io source:** `run_agent.py`, `model_tools.py`, `tools/registry.py`, `agent/context_compressor.py`
**Files:**
```
io-agent-core/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_agent/
    Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”œÎ¦”€Î¦”€ agent.py            # Agent class Î¦€” ReAct loop, tool execution, streaming
    Î¦”œÎ¦”€Î¦”€ events.py           # Event types: AgentStart, TurnStart, ToolCallStart, etc.
    Î¦”œÎ¦”€Î¦”€ types.py            # Pydantic models: AgentMessage, ToolResult, SessionConfig
    Î¦”œÎ¦”€Î¦”€ tools.py            # Tool base class, ToolRegistry (io' registry.py pattern)
    Î¦”œÎ¦”€Î¦”€ session.py          # Session abstraction (JSONL + SQLite dual storage)
    Î¦””Î¦”€Î¦”€ providers.py        # Provider resolution (io' 5-tier priority)
```
**Key design decisions (io-compatible from day one):**
- ToolRegistry with self-registration at import time (io' `registry.register()` pattern)
- Toolsets concept from day one (io' toolset filtering)
- IterationBudget shared across parent + subagents (io' pattern, default 90 turns)
- Context compression hooks built into agent loop (io' ContextCompressor interface)
- Parallel tool execution by default, `never_parallel` flag per tool (io convention)
- Approval gate interface for dangerous commands (io' tools/approval.py pattern)
- Interrupt propagation to child agents (io' `_interrupt_requested` pattern)
**Dependencies:** `io-ai`, `pydantic`, `httpx`
### Package 3: `io-tui` (Terminal UI)
**pi-mono source:** `packages/tui/` Î¦€” TUI, Editor, Input, SelectList, Component
**io source:** `cli.py` (TUI portions), prompt_toolkit usage
**Files:**
```
io-tui/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_tui/
    Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”œÎ¦”€Î¦”€ tui.py              # Main TUI orchestrator
    Î¦”œÎ¦”€Î¦”€ editor.py           # Multi-line editor with autocomplete
    Î¦”œÎ¦”€Î¦”€ input.py            # Input area with keybindings
    Î¦”œÎ¦”€Î¦”€ display.py          # Rich rendering, markdown, syntax highlighting
    Î¦”œÎ¦”€Î¦”€ components.py       # Tool cards, message bubbles, spinners
    Î¦”œÎ¦”€Î¦”€ overlays.py         # Dialogs, selectors, command palette
    Î¦””Î¦”€Î¦”€ keyboard.py         # Keyboard protocol, keybinding system
```
**Key design decisions:**
- prompt_toolkit (not Textual) Î¦€” lighter, more flexible, io already uses it
- Fixed input area at bottom (pi-mono TUI pattern, io-compatible)
- Rich markup for all output (io convention)
- Differential rendering for streaming (pi-mono TUI pattern)
- Skin/theme engine built in (our innovation, YAML-based)
**Dependencies:** `prompt_toolkit`, `rich`, `pygments`
### Package 4: `io-coding-agent` (Main CLI)
**pi-mono source:** `packages/coding-agent/` Î¦€” AgentSession, SessionManager, ExtensionAPI
**io source:** `cli.py`, `io_cli/`, `run_agent.py` (entry point)
**Files:**
```
io-coding-agent/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_cli/
    Î¦”œÎ¦”€Î¦”€ __init__.py         # __version__, __release_date__
    Î¦”œÎ¦”€Î¦”€ cli.py              # Main CLI entry point, REPL, argument parsing
    Î¦”œÎ¦”€Î¦”€ main.py             # Main loop, session orchestration
    Î¦”œÎ¦”€Î¦”€ config.py           # Config loading (5-tier priority, io convention)
    Î¦”œÎ¦”€Î¦”€ setup.py            # Interactive setup wizard
    Î¦”œÎ¦”€Î¦”€ auth.py             # Authentication management
    Î¦”œÎ¦”€Î¦”€ models.py           # Model selection UI
    Î¦”œÎ¦”€Î¦”€ commands.py         # Slash commands (/help, /model, /settings, etc.)
    Î¦”œÎ¦”€Î¦”€ callbacks.py        # Extension callbacks
    Î¦”œÎ¦”€Î¦”€ skin_engine.py      # YAML-based theme/skin system
    Î¦”œÎ¦”€Î¦”€ banner.py           # Phi logo, welcome banner, ASCII art
    Î¦”œÎ¦”€Î¦”€ colors.py           # Color utilities
    Î¦”œÎ¦”€Î¦”€ status.py           # Status display
    Î¦”œÎ¦”€Î¦”€ doctor.py           # Diagnostic checks
    Î¦”œÎ¦”€Î¦”€ uninstall.py        # Clean uninstall
    Î¦”œÎ¦”€Î¦”€ gateway.py          # Gateway management (Phase 2 prep)
    Î¦”œÎ¦”€Î¦”€ cron.py             # Cron management (Phase 2 prep)
    Î¦”œÎ¦”€Î¦”€ pairing.py          # Device pairing
    Î¦”œÎ¦”€Î¦”€ copilot_auth.py     # Copilot OAuth
    Î¦”œÎ¦”€Î¦”€ config.py           # Config management
    Î¦”œÎ¦”€Î¦”€ env_loader.py       # .env loading
    Î¦”œÎ¦”€Î¦”€ io_constants.py     # Constants (URLs, defaults)
    Î¦”œÎ¦”€Î¦”€ io_state.py         # State management
    Î¦”œÎ¦”€Î¦”€ default_soul.py     # Default SOUL.md content
    Î¦”œÎ¦”€Î¦”€ curses_ui.py        # Curses-based fallback UI
    Î¦”œÎ¦”€Î¦”€ checklist.py        # Setup checklist
    Î¦”œÎ¦”€Î¦”€ runtime_provider.py # Provider resolution at runtime
    Î¦”œÎ¦”€Î¦”€ tools_config.py     # Tool configuration
    Î¦”œÎ¦”€Î¦”€ skills_config.py    # Skills configuration
    Î¦”œÎ¦”€Î¦”€ skills_hub.py       # Skills hub integration
    Î¦”œÎ¦”€Î¦”€ pairing.py          # Device pairing
    Î¦”œÎ¦”€Î¦”€ plugins.py          # Plugin loading
    Î¦”œÎ¦”€Î¦”€ callbacks.py        # Extension callbacks
    Î¦”œÎ¦”€Î¦”€ clipboard.py        # Clipboard integration
    Î¦””Î¦”€Î¦”€ modules/            # Sub-modules
        Î¦”œÎ¦”€Î¦”€ run_agent.py    # Agent runner wrapper
        Î¦”œÎ¦”€Î¦”€ io_agent_runner.py
        Î¦”œÎ¦”€Î¦”€ io_agent_tool_adapter.py
        Î¦””Î¦”€Î¦”€ model_tools.py  # Tool definitions + dispatch
    Î¦”œÎ¦”€Î¦”€ tools/              # Built-in tools (Phase 2, io port)
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ registry.py     # Tool registry (io pattern)
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ file_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ terminal_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ web_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ search_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ memory_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ cron_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ delegation_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ clarify_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ browser_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ vision_tool.py
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ image_tool.py
    Î¦”‚   Î¦””Î¦”€Î¦”€ ... (40+ tools from io)
    Î¦”œÎ¦”€Î¦”€ extensions/         # Extension packages (Phase 2)
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-browser-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-clarify-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-cron-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-delegate-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-vision-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-image-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-memory-tools/
    Î¦”‚   Î¦”œÎ¦”€Î¦”€ io-web-tools/
    Î¦”‚   Î¦””Î¦”€Î¦”€ ... (27 extensions from io)
    Î¦””Î¦”€Î¦”€ skills/             # Skills packages (Phase 2)
        Î¦”œÎ¦”€Î¦”€ io-skills/
        Î¦””Î¦”€Î¦”€ io-skills-tools/
```
**Key design decisions (io-compatible from day one):**
- Config at `~/.io/` (not `~/.io/`) but same file structure
- 5-tier config priority (io convention)
- Session DB with FTS5 (io' io_agent/session.py pattern)
- Tool discovery via import-time registration (io pattern)
- Toolset filtering built in (io convention)
- Extension system with hooks/events (pi-mono pattern, io-compatible)
- Skin engine with YAML themes (our innovation)
- Phi logo branding throughout
**Config structure (mirrors io):**
```
~/.io/
Î¦”œÎ¦”€Î¦”€ config.yaml           # Settings
Î¦”œÎ¦”€Î¦”€ .env                  # API keys
Î¦”œÎ¦”€Î¦”€ auth.json             # OAuth credentials
Î¦”œÎ¦”€Î¦”€ SOUL.md               # Agent personality
Î¦”œÎ¦”€Î¦”€ memories/
Î¦”‚   Î¦”œÎ¦”€Î¦”€ MEMORY.md         # Curated notes (2200 char limit)
Î¦”‚   Î¦””Î¦”€Î¦”€ USER.md           # User profile (1375 char limit)
Î¦”œÎ¦”€Î¦”€ sessions/
Î¦”‚   Î¦”œÎ¦”€Î¦”€ sessions.db       # SQLite + FTS5
Î¦”‚   Î¦””Î¦”€Î¦”€ *.jsonl           # JSONL transcripts
Î¦”œÎ¦”€Î¦”€ cron/
Î¦”‚   Î¦””Î¦”€Î¦”€ jobs.json         # Scheduled tasks
Î¦”œÎ¦”€Î¦”€ skills/               # Installed skills
Î¦”œÎ¦”€Î¦”€ skins/                # YAML themes
Î¦””Î¦”€Î¦”€ logs/
    Î¦””Î¦”€Î¦”€ errors.log        # Error log
```
**Dependencies:** `io-ai`, `io-agent-core`, `io-tui`, `prompt_toolkit`, `rich`, `python-dotenv`, `pyyaml`, `pydantic`
### Package 5: `io-web-ui` (Browser Chat)
**pi-mono source:** `packages/web-ui/` Î¦€” AgentInterface, ChatPanel, ModelSelector
**io source:** (none Î¦€” this is new territory)
**Files:**
```
io-web-ui/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_web_ui/
    Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”œÎ¦”€Î¦”€ server.py           # FastAPI/Starlette server
    Î¦”œÎ¦”€Î¦”€ agent_interface.py  # WebSocket agent bridge
    Î¦”œÎ¦”€Î¦”€ chat_panel.py       # Chat UI component
    Î¦””Î¦”€Î¦”€ static/             # HTML/JS/CSS assets
        Î¦”œÎ¦”€Î¦”€ index.html
        Î¦”œÎ¦”€Î¦”€ app.js
        Î¦””Î¦”€Î¦”€ style.css
```
**Dependencies:** `io-agent-core`, `fastapi`, `uvicorn`, `websockets`
### Package 6: `io-mom` (Slack Bot)
**pi-mono source:** `packages/mom/` Î¦€” SlackBot, MomWorkspace
**io source:** `gateway/platforms/slack.py`
**Files:**
```
io-mom/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_mom/
    Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”œÎ¦”€Î¦”€ main.py             # Entry point
    Î¦”œÎ¦”€Î¦”€ slack_bot.py        # Slack bot implementation
    Î¦”œÎ¦”€Î¦”€ workspace.py        # Per-channel workspace management
    Î¦””Î¦”€Î¦”€ events.py           # Event handling
```
**Dependencies:** `io-coding-agent`, `slack_bolt`
### Package 7: `io-pods` (GPU Pod Manager)
**pi-mono source:** `packages/pods/` Î¦€” Pod lifecycle management
**io source:** `tools/environments/modal.py` (partial)
**Files:**
```
io-pods/
Î¦”œÎ¦”€Î¦”€ pyproject.toml
Î¦””Î¦”€Î¦”€ src/io_pods/
    Î¦”œÎ¦”€Î¦”€ __init__.py
    Î¦”œÎ¦”€Î¦”€ main.py             # CLI entry point
    Î¦”œÎ¦”€Î¦”€ lifecycle.py        # Pod create/destroy/scale
    Î¦”œÎ¦”€Î¦”€ providers.py        # Cloud provider backends
    Î¦””Î¦”€Î¦”€ vllm.py             # vLLM deployment management
```
**Dependencies:** `httpx`, `pydantic`
### Workspace Configuration
**Root `pyproject.toml`:**
```toml
[project]
name = "io"
version = "0.1.0"
description = "IO Agent Î¦€” AI coding agent by Most Wanted Research"
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
## PHASE 2: DIRECT PORT
Now that we have the 7-package pi-mono backbone, we port io features by plugging them into the right slots. The key insight: because we designed Phase 1 with io-compatible conventions, most io code drops in with minimal changes.
### 2.1 Tool System (Î¦†’ io-coding-agent/src/tools/)
**IO source:** `tools/` directory, `tools/registry.py`, `model_tools.py`
**Target:** `io-coding-agent/src/io_cli/tools/`
**Port directly:**
- `registry.py` Î¦€” ToolRegistry singleton, self-registration pattern
- `file_tool.py` Î¦€” Read, write, edit operations
- `terminal_tool.py` Î¦€” Bash execution with 6 backends
- `web_tool.py` Î¦€” Web search and extraction
- `search_tool.py` Î¦€” File search (grep, find)
- `memory_tool.py` Î¦€” Persistent memory (MEMORY.md, USER.md)
- `cron_tool.py` Î¦€” Cron job management
- `delegation_tool.py` Î¦€” Subagent delegation
- `clarify_tool.py` Î¦€” Structured clarification
- `browser_tool.py` Î¦€” Chrome DevTools browser control
- `vision_tool.py` Î¦€” Screenshot and image analysis
- `image_tool.py` Î¦€” Image generation (fal.ai)
- `code_execution_tool.py` Î¦€” Sandboxed code execution
- `voice_tool.py` Î¦€” Voice input/output
- `session_search_tool.py` Î¦€” FTS5 session search
- `todo_tool.py` Î¦€” Todo workflow
- `web_extract_tool.py` Î¦€” Content extraction
- `web_search_tool.py` Î¦€” Search engine integration
- `cron_tool.py` Î¦€” Scheduled tasks
- `delegate_tool.py` Î¦€” Task delegation
- `skills_tool.py` Î¦€” Skill management
- `homeassistant_tool.py` Î¦€” Home automation
- `honcho_tool.py` Î¦€” AI-native user modeling
- `pokemon_tool.py` Î¦€” Pokemon (for fun)
- `xitter_tool.py` Î¦€” Twitter/X integration
**Tool count:** 40+ tools across 17 toolsets
### 2.2 Terminal Backends (Î¦†’ io-coding-agent/src/tools/environments/)
**IO source:** `tools/environments/`
**Target:** `io-coding-agent/src/io_cli/tools/environments/`
**Port:**
- `base.py` Î¦€” BaseEnvironment abstract class
- `local.py` Î¦€” Local shell execution
- `docker.py` Î¦€” Docker container execution
- `ssh.py` Î¦€” SSH remote execution
- `modal.py` Î¦€” Modal serverless execution
- `singularity.py` Î¦€” Singularity container execution
- `daytona.py` Î¦€” Daytona cloud execution
### 2.3 Gateway (Î¦†’ io-gateway, Telegram only for now)
**IO source:** `gateway/`
**Target:** `io-gateway/` (new package) or `io-coding-agent/src/io_cli/gateway.py`
**Port (Telegram first):**
- `gateway/run.py` Î¦€” Gateway runner
- `gateway/platforms/base.py` Î¦€” BasePlatformAdapter
- `gateway/platforms/telegram.py` Î¦€” Telegram adapter (full port)
- `gateway/session.py` Î¦€” SessionStore, per-chat sessions
- `gateway/config.py` Î¦€” Gateway configuration
- `gateway/hooks.py` Î¦€” Hook system
- `gateway/status.py` Î¦€” Status management
**Deferred (Phase 3):**
- Discord adapter
- WhatsApp adapter
- Slack adapter (already have io-mom)
- Signal adapter
- Email adapter
### 2.4 Session System (Î¦†’ io-agent-core/src/session.py)
**IO source:** `io_agent/session.py`, `gateway/session.py`
**Target:** `io-agent-core/src/io_agent/session.py`
**Port:**
- SQLite + FTS5 full-text search
- JSONL transcript storage
- Session metadata tracking (title, model, token usage)
- Title lineage for compression tracking
- Reset policies (idle timeout, daily reset)
- `SessionDB` class
- `SessionStore` class
### 2.5 Cron System (Î¦†’ io-coding-agent/src/cron/)
**IO source:** `cron/scheduler.py`, `cron/jobs.py`
**Target:** `io-coding-agent/src/io_cli/cron/`
**Port:**
- `scheduler.py` Î¦€” 60-second tick loop
- `jobs.py` Î¦€” Job management (create, list, delete, run)
- Delivery targets (platform-specific output routing)
### 2.6 Skills System (Î¦†’ io-coding-agent/src/io_cli/)
**IO source:** `skills/`, `io_cli/skills_hub.py`, `io_cli/skills_config.py`
**Target:** `io-coding-agent/src/io_cli/skills_*.py`
**Port:**
- SKILL.md format
- Progressive disclosure
- Skills hub integration
- Skill discovery and loading
- Runtime injection
### 2.7 Context Compression (Î¦†’ io-agent-core/)
**IO source:** `agent/context_compressor.py`
**Target:** `io-agent-core/src/io_agent/compressor.py`
**Port:**
- Token-budget compression
- LLM summarization of old messages
- Configurable threshold (default 50% of context window)
- Compaction entry in session history
### 2.8 Batch Processing (Î¦†’ io-coding-agent/)
**IO source:** `batch_runner.py`, `toolset_distributions.py`
**Target:** `io-coding-agent/src/io_cli/batch/`
**Port:**
- `batch_runner.py` Î¦€” Parallel prompt processing with checkpointing
- `toolset_distributions.py` Î¦€” 19 Bernoulli-sampled distributions
- `trajectory_compressor.py` Î¦€” Token-budget compression for training data
- `mini_swe_runner.py` Î¦€” Docker/Modal terminal-only trajectory generation
### 2.9 Extensions (Î¦†’ io-coding-agent/extensions/)
**IO source:** Individual tool files, extension patterns
**Target:** `io-coding-agent/extensions/`
**Port as extension packages:**
- `io-browser-tools/` Î¦€” Chrome DevTools browser control
- `io-clarify-tools/` Î¦€” Structured clarification
- `io-cron-tools/` Î¦€” Cron management
- `io-delegate-tools/` Î¦€” Subagent delegation
- `io-vision-tools/` Î¦€” Screenshot and image analysis
- `io-image-tools/` Î¦€” Image generation
- `io-memory-tools/` Î¦€” Persistent memory
- `io-web-tools/` Î¦€” Web search and extraction
- `io-honcho-tools/` Î¦€” AI-native user modeling
- `io-voice-tools/` Î¦€” Voice input/output
- `io-code-execution/` Î¦€” Sandboxed code execution
- `io-subagent-tools/` Î¦€” Subagent management
- `io-acp/` Î¦€” Editor integration (ACP server)
- `io-agent-modes/` Î¦€” Agent mode definitions
- `io-context-compressor/` Î¦€” Context compression
- `io-smart-model-routing/` Î¦€” Model routing
- `io-usage-tracker/` Î¦€” Usage tracking
- `io-state/` Î¦€” State management
- `io-display/` Î¦€” Display utilities
- `io-model-metadata/` Î¦€” Model metadata
- `io-provider-presets/` Î¦€” Provider presets
- `io-zed/` Î¦€” Zed editor integration
- `io-insights/` Î¦€” Analytics and insights
- `io-hf-autoresearch/` Î¦€” HuggingFace autoresearch
- `io-hrr-memory-tools/` Î¦€” HRR holographic memory
- `io-pokemon-tools/` Î¦€” Pokemon tools
- `io-skills-tools/` Î¦€” Skills management
- `io-todo-tools/` Î¦€” Todo workflow
- `io-session-search-tools/` Î¦€” Session search
- `io-clarify-tools/` Î¦€” Clarification tools
### 2.10 ACP Server (Î¦†’ io-coding-agent/extensions/io-acp/)
**IO source:** `acp_adapter/`
**Target:** `io-coding-agent/extensions/io-acp/`
**Port:**
- Editor integration server
- VS Code, Zed, JetBrains support
- JSON-RPC protocol over stdio
---
## BRANDING
### Rebranding Rules
Every instance of io branding gets replaced:
| io | io |
|--------|-----|
| `io` (command) | `io` |
| `io` | `io-agent` / `IO Agent` |
| `Most Wanted Research` | `Most Wanted Research` |
| `~/.io/` | `~/.io/` |
| `IO_*` (env vars) | `IO_*` |
| `io_cli/` | `io_cli/` |
| Phi (Î¦Î¦Î¦) | Phi (Î¦) |
| `nousresearch/hermes-3-*` | (default model: user's choice via OpenRouter) |
### Logo
**Symbol:** Phi (Î¦) Î¦€” golden ratio, knowledge, divine proportion
**Banner (full):**
```
Î¦Î¦”Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦—
Î¦Î¦‘  Î¦ IO AGENT Î¦€” AI Coding Agent                              Î¦Î¦‘
Î¦Î¦‘  Most Wanted Research                                       Î¦Î¦‘
Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦Î¦
```
**Braille phi art** (for large terminal):
```
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ Î¦Î¦ ›Î¦ ›Î¦¢¿Î¦£¿Î¦£¿Î¦£¿Î¦ ŸÎ¦ ‰Î¦ ‰Î¦ ‰Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦¢ˆÎ¦£¿Î¦£ŸÎ¦¡Î¦¢€Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£ Î¦£´Î¦¡¶Î¦ Î¦ ›Î¦ ›Î¦¢»Î¦£¿Î¦¡Î¦ €Î¦¢ˆÎ¦¡‰Î¦ ›Î¦ »Î¦¢¶Î¦£¶Î¦£Î¦Î¦¡€Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦£°Î¦£¾Î¦¡¿Î¦ ‹Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£§Î¦£„Î¦ €Î¦ €Î¦ €Î¦ €Î¦ ¢Î¦¡™Î¦¢»Î¦£¿Î¦£·Î¦¡„Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦£¼Î¦£¿Î¦ Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£¿Î¦£¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ ˆÎ¦¢¦Î¦£¿Î¦¡‡Î¦£¿Î¦¡„Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦¢¸Î¦£¿Î¦¡¿Î¦¢ Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£¿Î¦£¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ Î¦Î¦£¿Î¦£‡Î¦£¿Î¦£§Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦¢¸Î¦£¿Î¦£¿Î¦£¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£¿Î¦£¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£¿Î¦ ›Î¦ ‹Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ ¸Î¦ ¿Î¦ ŸÎ¦ ¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£¿Î¦£¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦¢¸Î¦£¿Î¦ ‡Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ £Î¦ €Î¦ €Î¦ °Î¦¢£Î¦¡€Î¦ €Î¦ €Î¦ €Î¦ €Î¦£¿Î¦£¿Î¦£¿Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦¢€Î¦£¾Î¦ Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ Î¦ €Î¦ €Î¦ €Î¦ ‘Î¦¢¦Î¦£€Î¦¡€Î¦¢€Î¦£¿Î¦£¿Î¦ ‰Î¦£€Î¦ €Î¦£€Î¦£ Î¦¡´Î¦ ŸÎ¦ Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ ˆÎ¦ ‰Î¦¢›Î¦£¿Î¦£¿Î¦ Î¦¢ˆÎ¦¡‰Î¦ ‰Î¦ Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦£ Î¦¡¿Î¦ ‹Î¦ €Î¦¡°Î¦¡€Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ °Î¦ ¶Î¦ Î¦Î¦ ‰Î¦ €Î¦ €Î¦ €Î¦ €Î¦ ‰Î¦ “Î¦ ¶ Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €Î¦ €
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
  goodbye: "Goodbye! Î¦"
  response_label: " Î¦ IO "
  prompt_symbol: "Î¦¯ "
```
---
## TECH STACK
| Component | Choice | Rationale |
|-----------|--------|-----------|
| Runtime | Python 3.11+ | Target Python ecosystem |
| Package Manager | uv (workspace) | Fast, io-compatible, monorepo support |
| TUI | prompt_toolkit | Lightweight, flexible, io already uses it |
| Rendering | Rich | Terminal formatting, io convention |
| LLM Client | openai (OpenRouter) | Provider-agnostic, io default |
| Types | Pydantic | Validation, io convention |
| Config | YAML (pyyaml) | Human-readable, io convention |
| Storage | SQLite (aiosqlite) + JSONL | io dual-storage pattern |
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
**Grand total:** ~5-6 weeks for full feature parity with io
---
## WHAT MAKES IO DIFFERENT
**From io:**
- Clean 7-package architecture (not monolithic)
- uv workspace with proper package isolation
- prompt_toolkit TUI (not raw terminal)
- YAML skin engine (not hardcoded colors)
- Extension system with hooks/events (not import-based)
- Phi branding (not Phi)
- Most Wanted Research (not Most Wanted Research)
**From pi-mono:**
- Python (not TypeScript)
- 40+ tools, 6 terminal backends (not just read/write/edit/bash)
- SQLite + FTS5 session search (not just JSONL)
- Multi-platform gateway (not just CLI)
- Cron, skills, batch runner (not just agent loop)
- Context compression with LLM summarization
- HRR holographic memory (from nuggets)
**The hybrid:** pi-mono's clean architecture + io's feature depth = IO Agent.
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
