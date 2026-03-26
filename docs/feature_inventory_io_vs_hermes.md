# IO vs Hermes Feature Inventory

This is a practical, code-path-oriented inventory to track parity and guide porting work.
Sources:
- Local IO repository (`/Users/ever/Documents/GitHub/io`)
- Hermes main repo structure and docs ([NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent))

## Top-Level Architecture

### IO (workspace split)

- `packages/io-ai`: provider/auth/runtime/model registry/streaming/cost.
- `packages/io-agent-core`: loop, events, tool execution, runtime resolution bridge.
- `packages/io-coding-agent`: CLI/REPL, gateway, tools, skills, cron, ACP adapter, security.
- `packages/io-tui`: terminal UI primitives.
- `packages/io-web-ui`: FastAPI web chat surface.
- `packages/io-pods`: local pods registry CLI.
- `skills/`, `optional-skills/`: bundled skill content.
- `environments/`: research/eval environment utilities.
- `docs/`: operator and parity docs.

### Hermes (single-package + modules)

- `agent/`: prompt assembly, compression, display, metadata, trajectory hooks.
- `tools/`: built-in tool implementations and infra.
- `hermes_cli/`: CLI commands/setup/doctor/gateway wrappers/plugins.
- `gateway/`: platform adapters, run loop, delivery/pairing/session.
- `cron/`: scheduler/jobs.
- `acp_adapter/`: ACP process adapter.
- `honcho_integration/`: Honcho-specific integration.
- top-level modules (`run_agent.py`, `cli.py`, `toolsets.py`, etc.).

## Domain-by-Domain Features

## CLI + REPL

### IO
- Command tree and REPL loop: `packages/io-coding-agent/src/io_cli/cli.py`
- Slash command registry/completions: `packages/io-coding-agent/src/io_cli/commands.py`
- REPL slash dispatch parity with gateway: `packages/io-coding-agent/src/io_cli/repl_slash.py`
- Model/provider pickers: `packages/io-coding-agent/src/io_cli/model_picker.py`, `provider_picker.py`
- Banner/skins/title UX: `banner.py`, `skin_engine.py`, `colors.py`

### Hermes
- Main CLI command system: `hermes_cli/commands.py`, `hermes_cli/main.py`
- REPL/TUI helpers: `hermes_cli/banner.py`, `callbacks.py`, `curses_ui.py`, `colors.py`
- Slash and model flows via CLI + agent orchestration: `cli.py`, `run_agent.py`

## Auth / Providers / Models

### IO
- Provider registry + auth store: `packages/io-ai/src/io_ai/auth.py`
- Runtime provider resolution: `packages/io-ai/src/io_ai/runtime_provider.py`
- Model registry/catalog/dynamic provider models: `packages/io-ai/src/io_ai/models.py`
- Copilot OAuth device-code flow (Hermes-style): `packages/io-ai/src/io_ai/copilot_auth.py`
- Streaming + provider adapters: `packages/io-ai/src/io_ai/stream.py`, `providers/*`

### Hermes
- Provider auth/runtime + model selection: `hermes_cli/auth.py`, `hermes_cli/runtime_provider.py`, `hermes_cli/models.py`
- Copilot OAuth/token rules: `hermes_cli/copilot_auth.py`
- Provider/model metadata/routing helpers: `agent/model_metadata.py`, `agent/smart_model_routing.py`

## Tools + Toolsets

### IO
- Tool registry and selection: `packages/io-coding-agent/src/io_cli/tools/registry.py`, `toolsets.py`
- Core tool execution contracts: `packages/io-agent-core/src/io_agent/tools.py`
- Built-ins: `tools/shell.py`, `tools/filesystem.py`, `tools/web.py`, `tools/browser_tools.py`, `tools/delegation.py`, `tools/memory.py`, `tools/session_search.py`, `tools/cronjob.py`, `tools/skills.py`, `tools/honcho_tools.py`, `tools/compat.py`
- Security checks and approval hooks: `security/tirith.py`, `tools/shell.py`, `tools/compat.py`

### Hermes
- Tool registry/infrastructure: `tools/registry.py`, `tools/__init__.py`
- Broad tool catalog: filesystem/shell/browser/memory/cron/delegation/tts/vision/mcp/etc in `tools/*`
- Toolset definitions: `toolsets.py`, `toolset_distributions.py`
- Approval + security paths: `tools/approval.py`, `tools/tirith_security.py`

## Gateway / Messaging

### IO
- Manager/runner/session/delivery/runtime: `gateway.py`, `gateway_runner.py`, `gateway_session.py`, `gateway_delivery.py`, `gateway_runtime.py`
- Platform adapters:
  - telegram/discord/slack/whatsapp/signal/mattermost/matrix/homeassistant/email/sms/dingtalk/webhook/api_server
  - under `packages/io-coding-agent/src/io_cli/gateway_platforms/*.py`
- Pairing: `pairing.py`
- Recent parity work: startup/poll reconnect with exponential backoff in `gateway_runner.py`

### Hermes
- Gateway run loop + session/delivery/pairing: `gateway/run.py`, `gateway/session.py`, `gateway/delivery.py`, `gateway/pairing.py`
- Platform adapters in `gateway/platforms/*.py`
- Recent upstream focus: reconnect/backoff, safer command handling in gateway startup/run path.

## Cron / Scheduling

### IO
- Cron manager and jobs: `packages/io-coding-agent/src/io_cli/cron.py`
- CLI commands: `cli.py` (`io cron ...`)
- Agent-facing cron tools: `tools/cronjob.py`

### Hermes
- Scheduler/jobs: `cron/scheduler.py`, `cron/jobs.py`
- CLI wrappers: `hermes_cli/cron.py`
- Tool surfaces: `tools/cronjob_tools.py`

## Skills / Memory / Honcho

### IO
- Skill discovery and command surfacing: `skills.py`, `agent/skill_commands.py`
- Skills content in `skills/**` and `optional-skills/**`
- Memory tools + session search: `tools/memory.py`, `tools/session_search.py`
- Nuggets HRR memory stack: `nuggets/*`
- Honcho integrations: `tools/honcho_tools.py`

### Hermes
- Skills content and tooling: `skills/**`, `optional-skills/**`, `tools/skills_tool.py`, `tools/skill_manager_tool.py`
- Session/memory/search tooling in `tools/*`
- Honcho integration package: `honcho_integration/*`, `tools/honcho_tools.py`

## ACP

### IO
- ACP adapter: `packages/io-coding-agent/src/io_cli/acp_adapter/*`
- Registry assets: `acp_registry/agent.json`
- Entrypoints: `io acp`, `io-acp`
- MCP auth/runtime status contracts for ACP + CLI auth commands:
  - `packages/io-coding-agent/src/io_cli/mcp_runtime.py`
  - `io auth mcp-login|mcp-status|mcp-logout`

### Hermes
- ACP adapter: `acp_adapter/*`
- Registry assets: `acp_registry/*`
- Entrypoint: `hermes-acp`

## Terminal Backends / Environments

### IO
- Backends: local/docker/ssh/singularity/modal/daytona in `packages/io-coding-agent/src/io_cli/environments/*`
- Config surface in `config.py` (`terminal.*`)

### Hermes
- Primarily via mini-swe-agent integration and tool environment modules:
  - `mini-swe-agent` submodule
  - `tools/terminal_tool.py`
  - `tools/environments/*`

## Web UI / API Surface

### IO
- Dedicated FastAPI package: `packages/io-web-ui/src/io_web_ui/server.py`
- Gateway API adapter: `gateway_platforms/api_server.py`

### Hermes
- Gateway API server adapter: `gateway/platforms/api_server.py`
- Docs/website stack: `website/` (Docusaurus), plus `landingpage/`

## Research / Trajectory / RL

### IO
- `io research list|export|summary`: `packages/io-coding-agent/src/io_cli/trajectory_export.py`
- Additional research envs and parsers: `environments/*`

## Semantic Search / Repo-Map

### IO
- Lightweight semantic contract + implementation: `packages/io-agent-core/src/io_agent/semantic_context.py`
- CLI/agent integration hooks: `packages/io-coding-agent/src/io_cli/main.py` (`semantic.*` config, env toggles)
- Hermes-compatible contract wrappers:
  - `semantic_search_contract(...)`
  - `repo_map_contract(...)`
  - in `packages/io-coding-agent/src/io_cli/hermes_contracts.py`

### Hermes
- Batch + trajectory compression + RL tooling:
  - `batch_runner.py`
  - `trajectory_compressor.py`
  - `rl_cli.py`
  - `environments/*`
  - `tinker-atropos` submodule

## Security

### IO
- Tirith integration + installer command: `security/tirith.py`, `cli.py` (`io security tirith-install`)
- Website policy helper: `website_policy.py`
- Command approval checks in shell/terminal tools.

### Hermes
- Tirith security checks + command approval stack in `tools/tirith_security.py`, `tools/approval.py`
- Recent updates in gateway command safety paths.

## Maturity Notes (Current)

- IO is strong in command surface parity, gateway adapter breadth, ACP, cron, and provider breadth.
- Hermes still leads in some production-hardening details and integrated research pipeline depth.
- IO recent parity improvements in this session:
  - Copilot device-code login command (`io auth copilot-login`)
  - `/provider` picker + completions
  - `/gate` alias
  - ANSI stripping on shell/terminal tool streams and outputs
  - gateway reconnect with exponential backoff
  - `@path` REPL completion and safe `@file` inline context expansion (cwd-scoped)
  - MCP token contract/auth surface (`io auth mcp-*`) + ACP method exposure for configured MCP servers
  - tool alias normalization contracts (`resolve_tool_name`, `tool_contracts.aliases`, `normalize_tool_call_contract`)
  - semantic search + repo-map context layer (feature-flagged)
  - research/RL CLI path expanded to list/export/summary trajectory workflow

## Fast Porting Backlog

1. Upgrade semantic layer from token-overlap to embedding-backed index when optional deps are enabled.
2. Add trajectory compression/eval helpers for stronger Hermes RL parity.
3. Expand gateway adapter live integration tests (beyond unit/contract matrix).
4. Continue MCP lifecycle parity on capability negotiation and per-server health telemetry.

## Structure Harmonization (No Migration)

To reduce diff noise when porting from Hermes while keeping IO's split packages,
IO now includes small compatibility facades:

- `packages/io-coding-agent/src/io_cli/hermes_contracts.py`
  - `gateway_manager(...)`
  - `gateway_run(...)`
  - `provider_auth_status(...)`
  - `tool_registry()`
  - `expand_context_references(...)`
  - `build_gateway_session_contract(...)`
  - `delivery_router_contract(...)`
  - `tool_contracts(...)`
  - `normalize_tool_call_contract(...)`
  - `auth_command_status_contract(...)`
  - `auth_command_copilot_login_contract(...)`
  - `mcp_status_contract(...)`
  - `mcp_login_contract(...)`
  - `mcp_logout_contract(...)`
  - `semantic_search_contract(...)`
  - `repo_map_contract(...)`
- `packages/io-ai/src/io_ai/hermes_contracts.py`
  - `resolve_runtime_contract(...)`
  - `list_providers_contract(...)`
  - `copilot_login_contract(...)`

These facades are intentionally thin adapters over existing IO internals so
future parity ports can target stable contract surfaces instead of deep paths.

