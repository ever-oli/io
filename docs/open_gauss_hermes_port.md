# OpenGauss / Hermes → IO port map

[OpenGauss](https://github.com/math-inc/OpenGauss) is a **Math, Inc.** fork of [nousresearch/hermes-agent](https://github.com/nousresearch/hermes-agent), extended with **Lean** workflows (`/prove`, `/draft`, project `.gauss/`). [DeepWiki overview](https://deepwiki.com/math-inc/OpenGauss) summarizes the full stack.

IO is already **pi-mono–style** (agent loop in `io-agent-core`, CLI in `io-coding-agent`, gateway adapters, ACP, skins, toolsets). This document tracks **what to port** vs **what to skip** when chasing *Hermes-style infrastructure* and *Gauss-style formal hooks*.

**New to Gauss?** Start with **[`docs/gauss_new_user.md`](gauss_new_user.md)** — **Lean** = `lean.*_argv` (default Aristotle); **OpenGauss** = `io gauss` / `/gauss`; **`/gateway start`** runs `io gateway run` in the background.

## Parity scorecard (approximate)

Percentages are **judgmental engineering estimates** — “same bucket of capability,” not line-count parity.

| Track | ~% | Notes |
|-------|---:|--------|
| **Hermes generic** (agent loop, tools, toolsets, session DB/FTS, gateway, ACP, skins, cron, REPL slash) | **~92%** | Adds REPL multiline, `display.streaming` token deltas, `tool_output_delta` for terminal/bash, SIGINT→`interrupt_requested` + follow-up prompt, `delegate_task` / `execute_code`, optional Honcho HTTP tools, cron status vs gateway runtime, `io research export` JSONL. |
| **Gauss security** (Tirith pre-exec, auto-install, cosign) | **~72%** | IO: Tirith scan + `io security tirith-install` (`cargo install --root ~/.io`); **no** in-process cosign policy like some Gauss release pipelines. |
| **Gauss Lean / formal** (`.gauss/project`, swarm, managed lean4-skills children, `/draft` `/formalize` …) | **~58%** | IO: argv bridges + `.gauss/project.yaml` + registry; **no** embedded OpenGauss swarm supervisor. |
| **Gauss RL / training** (trajectory compressor, envs, mini-swe) | **~12%** | `io research export` → session JSONL from `state.db`; still no env trainer / compressor stack. |
| **Blended “daily driver”** (Hermes + Tirith + lean CLI bridge) | **~78%** | What most coding-agent + formal users touch first. |
| **Whole OpenGauss repo surface** (including Lean product + RL) | **~52%** | Dominated by in-repo RL + deep Lean orchestration you may not embed in IO. |
| **Gauss *verb coverage* in IO** (`/lean` + `io lean` surface) | **100%** † | Verbs wired: `submit`, `prove`, `draft`, `formalize`, `swarm`, `project`, `doctor`, Tirith installer. **†** `draft` / `formalize` / `swarm` need explicit `lean.*_argv`; no fake fallback to `prove_argv`. |

### “100% Gauss” — two meanings

1. **IO Gauss-shaped surface (verbs + config)** — same command names from IO; **Lean** defaults to Aristotle argv ([`gauss_new_user.md`](gauss_new_user.md)).
2. **OpenGauss the product** (embedded swarm manager, RL, signing policy) — **not 100% inside IO**; use OpenGauss alongside IO or set explicit `lean.*_argv` to their CLIs.

## Legend

| Status | Meaning |
|--------|--------|
| ✅ | Present in IO |
| 🟡 | Partial / different shape |
| 📌 | Ported in this repo (see code) |
| ⏭️ | Defer or exclude by design |

## High-level areas

| OpenGauss area | IO today | Target |
|----------------|----------|--------|
| Agent loop (`AIAgent` / `run_conversation`) | `io_agent.Agent.run` / `run_stream` | ✅ same role |
| Tool registry + toolsets | `io_cli.tools.registry`, `toolsets.py` | ✅ |
| Session DB + FTS | `SessionDB`, `session_search` | ✅ |
| Messaging gateway | `gateway_runner`, platform adapters | ✅ broad |
| ACP adapter | `io_cli.acp_adapter` | ✅ |
| Skin engine | `skin_engine.py` | ✅ |
| Cron | `cron.py` | ✅ |
| **Tirith** pre-exec scan | was ❌ | 📌 `io_cli.security.tirith` |
| **Tirith** install into IO home | was ❌ | 📌 `io security tirith-install` (cargo) |
| **Lean submit** (Aristotle) | ❌ | 📌 `io lean submit`, `/lean submit` |
| **Lean prove** (Gauss-style) | ❌ | 📌 `io lean prove`, `/lean prove`, `lean.prove_argv` |
| **Lean draft / formalize** | ❌ | 📌 `io lean draft|formalize`, `/lean …`, `lean.draft_argv` / `lean.formalize_argv` |
| **Lean swarm hook** | ❌ | 📌 `io lean swarm`, `lean.swarm_argv` (shell out to OpenGauss) |
| **Lean project pins** (named roots) | ❌ | 📌 `io lean project …`, `/lean project …`, `--project <name>` |
| **Named prover backends** (Aristotle vs Gauss argv) | ❌ | 📌 `lean.backends`, `default_backend`, `--backend`, `/lean prove @gauss …`, `io lean backends list` |
| **`.gauss/project.yaml`** lean root | ❌ | 📌 `io_cli.gauss_project` + `lean.respect_gauss_project_yaml` |
| **OpenGauss CLI passthrough** | ❌ | 📌 `io gauss …`, `/gauss …` (REPL), `gauss.bin` in config |
| **Slash: start gateway in background** | ❌ | 📌 `/gateway start` → `io gateway run` detached (`~/.io/gateway/run.log`) |
| Trajectory export (RL / JSONL) | 🟡 | 📌 `io research export` (sessions + messages); compressor / env training still ⏭️ |
| In-process swarm + managed lean4-skills children | ❌ | ⏭️ use `lean.swarm_argv` + OpenGauss |
| Tirith **cosign** on release artifacts (Gauss) | ❌ | 🟡 optional org policy; not bundled |
| mini-swe-agent / RL envs | ❌ | ⏭️ only if IO trains models |

## Aristotle / Lean (IO-native)

```bash
io lean project add my-math ./path/to/lean-root --current
io lean submit "Prove that there are infinitely many primes." --cwd . --project my-math
io lean prove "1+1=2" --cwd . --project-dir .
io lean draft "informal sketch …"      # needs lean.draft_argv
io lean formalize "lemma statement …"  # needs lean.formalize_argv
io lean swarm "orchestration payload" # needs lean.swarm_argv (e.g. OpenGauss entrypoint)
io lean doctor
io lean project list
io lean backends list                  # show lean.backends names + default
io lean prove "…" --backend gauss      # requires lean.backends.gauss (configure argv yourself)
io gauss chat                          # real OpenGauss TUI
```

REPL / gateway: `/lean …`, `/gauss …` (REPL runs passthrough; messaging hints to use `io gauss` on host), `/gateway start|status`, `/platforms` (status).

## Run OpenGauss beside IO

IO does **not** reimplement OpenGauss’s TUI swarm, child agents, RL stack, etc. Run Gauss directly:

```bash
pip install gauss-agent   # or: uv add gauss-agent
io gauss chat             # interactive TUI with /prove, /draft, …
io gauss gateway run      # messaging gateway
io gauss --help           # passthrough to gauss CLI
```

Config (`~/.io/config.yaml`):

```yaml
gauss:
  enabled: true
  bin: "gauss"   # or "gauss-agent" / path to wrapper
```

Configure **`lean.backends`** yourself if you want `io lean prove --backend gauss`. Interactive `/prove` lives in **`io gauss chat`**.

### Lean config (`~/.io/config.yaml`)

```yaml
lean:
  enabled: true
  default_project_dir: "."
  prefer_registry_current: false
  respect_gauss_project_yaml: true
  submit_argv: [uv, run, aristotle, submit]
  submit_timeout: 600
  prove_argv: [uv, run, aristotle, prove]
  prove_timeout: 600
  draft_argv: []           # e.g. your OpenGauss / gauss draft CLI
  formalize_argv: []
  swarm_argv: []
  draft_timeout: 600
  formalize_timeout: 600
  swarm_timeout: 900
  # Optional: two (or more) prover CLIs — ``--backend`` / ``@name`` in /lean
  default_backend: aristotle
  backends:
    aristotle:
      submit_argv: [uv, run, aristotle, submit]
      prove_argv: [uv, run, aristotle, prove]
    gauss:
      # Example — replace with your OpenGauss / gauss / wrapper install:
      submit_argv: [uv, run, aristotle, submit]
      prove_argv: [uv, run, aristotle, prove]
```

Omit a key inside a backend block to **inherit** from the top-level `submit_argv` / `prove_argv` / … for that verb.

Point **`prove_argv`**, **`draft_argv`**, etc. at **lean4-skills** or OpenGauss wrappers; IO spawns the process and passes **`--project-dir`** (after Gauss YAML resolution when enabled).

## Tirith installer

Tirith is a **Rust** tool ([sheeki03/tirith](https://github.com/sheeki03/tirith)). IO can install a copy under **`~/.io/bin`** (same layout idea as Gauss’s pinned bin dir):

```bash
io security tirith-install
```

This runs `cargo install <crate> --locked --root ~/.io` (crate name from config, default `tirith`). Requires **Rust/cargo** on PATH. Alternatives: `brew install sheeki03/tap/tirith`, `npm install -g tirith`, etc., then ensure `tirith` is on PATH or symlink into `~/.io/bin/`.

`~/.io/config.yaml`:

```yaml
security:
  tirith:
    enabled: true
    path: "tirith"
    timeout: 5
    fail_open: true
    cargo_install_package: "tirith"
```

## Configuration (IO) — Tirith scan

Env overrides: `TIRITH_ENABLED`, `TIRITH_BIN`, `TIRITH_TIMEOUT`, `TIRITH_FAIL_OPEN`.

## Suggested order for remaining Hermes parity

1. **Tirith** — command-line scanner before `bash` / `terminal`.
2. **Lean bridges** — submit, prove, draft, formalize, swarm argv + `.gauss` hints.
3. **Skills guard / approval** — align with Gauss + existing IO approval callback.
4. **Trajectory tooling** — optional `scripts/` or package.
5. **Gateway hooks** — diff `gateway/run.py` vs `gateway_runner.py` for items you care about.
6. **Heavy OpenGauss orchestration** — run OpenGauss beside IO or wire `lean.swarm_argv`.

## Version note

Revisit this doc when bumping IO; refresh against OpenGauss `main` periodically.
