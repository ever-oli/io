# OpenGauss Parity Report

**IO/Gauss Fusion Status** - Gotenks mode activated 🌀

OpenGauss is a Math, Inc. fork of Hermes with Lean workflow orchestration. This report tracks IO's parity with OpenGauss features.

## Executive Summary

| Category | Status | Coverage |
|----------|--------|----------|
| **Swarm Management** | ✅ Complete | 100% |
| **Project System** | ✅ Complete | 100% |
| **Workflow Commands** | ✅ Complete | 100% |
| **TUI/Interface** | 🟡 Partial | 60% |
| **RL/Training** | ⏭️ Planned | 0% |
| **Security (cosign)** | ⏭️ Planned | 0% |

**Overall: ~65%** (Core workflows done, RL/training pending)

---

## Detailed Parity Breakdown

### 1. Swarm Manager ✅ 100%

| Feature | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| Task spawning | `swarm_manager.spawn()` | `SwarmManager.spawn()` | ✅ |
| Background threads | Daemon threads | Daemon threads | ✅ |
| Interactive PTY | `spawn_interactive()` | `spawn(interactive=True)` | ✅ |
| Attach/detach | `/swarm attach <id>` | `attach_to_task()` + Ctrl-] | ✅ |
| Task tracking | `SwarmTask` dataclass | `SwarmTask` dataclass | ✅ |
| Status updates | Real-time | Real-time | ✅ |
| Cancel tasks | `cancel()` | `cancel()` | ✅ |
| Rich table display | `render_table()` | `render_swarm_table()` | ✅ |
| Output buffering | `_recent_output` | `_recent_output` | ✅ |
| Singleton pattern | `SwarmManager._instance` | `SwarmManager._instance` | ✅ |

**Files:** `packages/io-swarm/src/io_swarm/manager.py`

---

### 2. Project System ✅ 100%

| Feature | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| Project registry | `~/.gauss/projects.yaml` | `~/.io/lean/registry.yaml` | ✅ |
| Named projects | `/project add <name>` | `ProjectRegistry.add()` | ✅ |
| Project lookup | `/project use <name>` | `registry.get(name)` | ✅ |
| .gauss/project.yaml | Auto-detect lean root | `_find_gauss_root()` | ✅ |
| Path resolution | CWD → parent dirs | Same algorithm | ✅ |
| List projects | `/project list` | `registry.list_all()` | ✅ |

**Files:** `packages/io-swarm/src/io_swarm/projects.py`

---

### 3. Workflow Commands ✅ 100%

| Command | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| /prove | `spawn_prove()` | `spawn_prove()` | ✅ |
| /draft | `spawn_draft()` | `spawn_draft()` | ✅ |
| /formalize | `spawn_formalize()` | `spawn_formalize()` | ✅ |
| /review | `spawn_review()` | `spawn_review()` | ✅ |
| /golf | `spawn_golf()` | `spawn_golf()` | ✅ |
| /autoprove | Planned | Planned | ⏭️ |
| /autoformalize | Planned | Planned | ⏭️ |
| Backend selection | `--backend <name>` | `backend=` param | ✅ |
| Configurable argv | `lean.*_argv` | Same config keys | ✅ |

**Files:** `packages/io-swarm/src/io_swarm/workflows.py`

---

### 4. TUI/Interface 🟡 60%

| Feature | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| Rich tables | Full color themes | Basic colors | 🟡 |
| Status bar | `status_bar_fragment()` | `render_swarm_summary()` | ✅ |
| Task detail view | Full detail table | Basic detail table | 🟡 |
| Progress tracking | Parsed from stream | Basic status | 🟡 |
| Skin engine | `gauss_cli.skin_engine` | Not implemented | ❌ |
| Welcome banner | Custom branding | Not implemented | ❌ |

**Notes:** IO has functional TUI but lacks Gauss's aesthetic polish (skins, custom colors).

---

### 5. RL/Training ⏭️ 0%

| Feature | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| Trajectory compression | `trajectory_compressor.py` | Planned | ⏭️ |
| JSONL export | `io research export` | Already exists ✅ | ✅ |
| Mini-SWE agent | `mini-swe-agent/` submodule | Planned | ⏭️ |
| Training envs | Atropos, Tinker | Planned | ⏭️ |
| Wandb integration | Built-in | Not planned | ❌ |
| Reward modeling | Custom | Not planned | ❌ |

**Notes:** RL/training is a large undertaking. IO focuses on inference/agent runtime, not training.

---

### 6. Security (cosign) ⏭️ 0%

| Feature | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| Release signing | cosign integration | Planned | ⏭️ |
| SBOM generation | sigstore | Not planned | ❌ |
| Policy verification | In-pipeline | Not planned | ❌ |

**Notes:** Supply chain security important for releases, not for daily use.

---

### 7. Additional Gauss Features

| Feature | OpenGauss | IO | Status |
|---------|-----------|-----|--------|
| Tirith scanning | `tools/tirith_security.py` | ✅ Implemented | ✅ |
| Tirith install | `io security tirith-install` | ✅ Implemented | ✅ |
| Gauss CLI passthrough | `io gauss ...` | ✅ Implemented | ✅ |
| Managed backends | Claude Code spawner | PTY spawn (generic) | 🟡 |
| Checkpoint workflow | `/checkpoint` | Not implemented | ❌ |
| Refactor workflow | `/refactor` | Not implemented | ❌ |
| Auto-proving | Autonomous mode | Not implemented | ❌ |

---

## Architecture Comparison

### OpenGauss
```
gauss-cli/          # TUI + swarm manager (monolithic)
├── main.py         # Entry point
├── swarm_manager.py # Task orchestration
├── gauss_cli/      # Interactive CLI
└── tools/          # Built-in tools
```

### IO (Gotenks Fusion)
```
packages/
├── io-ai/          # LLM runtime (pi-mono)
├── io-agent-core/  # Agent loop (pi-mono)
├── io-coding-agent/# CLI + REPL (pi-mono)
├── io-tui/         # Terminal components (pi-mono)
├── io-web-ui/      # Web interface (pi-mono)
├── io-pods/        # vLLM management (pi-mono)
├── io-bot/         # Telegram gateway (custom)
└── io-swarm/       # Workflow swarm (Gauss-inspired)
    ├── manager.py   # SwarmManager
    ├── projects.py  # Project registry
    ├── workflows.py # /prove, /draft, etc.
    └── tui.py       # Rich displays
```

**Key Difference:** IO separates concerns into packages; OpenGauss is more monolithic.

---

## Usage Examples

### OpenGauss
```bash
gauss                          # Start TUI
/project create ~/my-proof     # Create project
/prove "1+1=2"                 # Spawn proof agent
/swarm                         # View running agents
/swarm attach af-001           # Attach to agent
```

### IO (Gotenks)
```bash
io swarm spawn --prove "1+1=2" # Spawn proof agent
io swarm list                  # View running agents
io swarm attach io-001         # Attach to agent (Ctrl-] detach)
io project add my-proof ~/work # Register project
io lean prove "1+1=2"          # Alternative CLI
```

---

## What's Missing (Priority Order)

### High Priority
1. ✅ **Swarm management** - DONE
2. ✅ **Project system** - DONE
3. ✅ **Core workflows** - DONE
4. 🟡 **Better TUI polish** - Basic but functional

### Medium Priority
5. ⏭️ **Trajectory compression** - For RL data prep
6. ⏭️ **Cosign signing** - Release security

### Low Priority
7. ⏭️ **Training infrastructure** - Full RL stack
8. ⏭️ **Mini-SWE agent** - Benchmarking

---

## Recommendations

1. **Keep io-swarm as 8th package** - Clean separation from core 7
2. **Focus on workflow stability** before RL features
3. **Integrate with io-coding-agent CLI** for `/swarm`, `/prove` slash commands
4. **Add trajectory compression** if planning RL training
5. **Defer cosign** until first release

---

## Version Note

Last checked against OpenGauss `main` (March 2026)

**IO Swarm Version:** 0.1.0 (Gotenks initial release)
