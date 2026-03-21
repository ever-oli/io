<p align="center">
  <img src="github_banner.png" alt="IO" width="100%" />
</p>

# IO

IO is a clean-room Python rewrite of the pi-mono repo and hermes , organized around
the core package boundaries lifted from pi-mono. I couldn't decide on one so why not both. 

## Version

Current milestone: `0.1.2` (2026-03-19) — Nuggets-style HRR memory parity, gateway surfaces, CLI hardening.

## Packages

- `io-ai`: provider runtime, model registry, auth, and cost tracking
- `io-agent-core`: agent loop, tools, events, and session index
- `io-tui`: generic prompt_toolkit and Rich terminal components
- `io-coding-agent`: CLI, session manager, extensions, and built-in tools
- `io-web-ui`: FastAPI web runtime and browser chat surface
- `io-pods`: persisted local pod lifecycle and vLLM management

### Hermes-style TUI parity (CLI)

| Feature | Status |
|--------|--------|
| Multiline REPL | `display.repl_multiline_mode`: **`single_ctrl_j`** (default) = Enter submits, **Ctrl-J** newline; **`meta_submit`** = full PT multiline (Enter newline, Esc/Meta+Enter submit); **`buffer`** = lines until sentinel (`repl_buffer_sentinel`, default `END`) |
| Token streaming | `display.streaming` + `io_ai.stream` deltas → REPL (`message_delta` events) |
| Tool stdout/stderr streaming | `display.stream_tool_output` (default on) → `tool_output_delta` for `terminal` / `bash` |
| SIGINT → interrupt | Sets `Agent.interrupt_requested`; follow-up prompt for redirect text |
| Honcho tools | **Honcho API v3** by default (`workspace_id`, `session_id`, peer defaults). Set `honcho.api_version: legacy` + `paths` for old `/api/*` servers. See [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md) |
| Delegation / code tools | `delegate_task`, `execute_code` registered (`delegation` / `code_execution` toolsets; included in `io-cli`) |
| Cron scheduler truth | `cron.status().scheduler_available` reflects gateway runtime (`io gateway run`) |
| Trajectory export | `io research export --out trajectories.jsonl` (from `~/.io/state.db`) |

**Memory stack:** the original IO layer (`memory_snapshot` + `~/.io/memories/*.md`, `memory` tool, FTS + `session_search`, nuggets) stays the default and is **not** replaced by Honcho. Honcho is optional on top — see [`docs/memory-nuggets-and-honcho.md`](docs/memory-nuggets-and-honcho.md).

### Holographic memory (Nuggets-style)

The `nuggets` tool provides **Holographic Reduced Representation (HRR)** memory
inspired by [Nuggets](https://github.com/NeoVertex1/nuggets) (MIT): facts live
under `~/.io/nuggets/` (per IO home) as small JSON files; recall is local
algebra on fixed-size vectors. Facts recalled often are merged into
`memories/MEMORY.md` (threshold 3) when `nuggets.auto_promote` is true in config.
The default vector dimension is large (`D=16384`); Python rebuild cost is higher
than the upstream TypeScript engine—use smaller `D` only for tests or light use.
Behavioral parity targets (PRNG goldens, Nuggets-style fuzzy keys, promotion header)
are documented in [`docs/nuggets_parity.md`](docs/nuggets_parity.md) with tests in
`tests/test_nuggets_parity.py`.

**OpenGauss / Hermes-style security:** optional [Tirith](https://github.com/sheeki03/tirith) command scanning for `bash` / `terminal`, plus `io security tirith-install` (cargo → `~/.io/bin`); see [`docs/open_gauss_hermes_port.md`](docs/open_gauss_hermes_port.md).

**Lean / Aristotle:** `io lean submit|prove|…` (`lean.*_argv`), optional **`lean.backends`** and **`--backend`**, `/lean prove @name …`, **`io lean backends list`**. **OpenGauss:** `io gauss …` / `/gauss …` (real CLI). **`/gateway start`** spawns `io gateway run` in the background. See [`docs/gauss_new_user.md`](docs/gauss_new_user.md), [`docs/open_gauss_hermes_port.md`](docs/open_gauss_hermes_port.md), skill `mathematics/aristotle-formal-proof`.

## Personal SOUL (repo-local, not committed)

The agent’s **system persona** is loaded like this:

1. **Workspace file** — From the session **working directory**, IO walks **up** the directory tree and uses the first **`soul.md`** or **`SOUL.md`** it finds (usually the repo root). That’s where you put a SillyTavern / character-card–style identity without committing it.
2. **Fallback** — If no such file exists, IO uses **`~/.io/SOUL.md`** (created on first bootstrap).

Repo root **`soul.md` / `SOUL.md`** are listed in **`.gitignore`**, so they stay on your machine only. A committed starter is **`soul.example.md`** — copy it to `soul.md` and edit freely.

**Verify IO is using it:** run `io doctor` from the same directory you use for `io chat` (or pass `--cwd`). Check **`soul_path`** and **`soul_source`** (`workspace` = your repo `soul.md`, `io_home` = `~/.io/SOUL.md`). If `soul_source` is `io_home`, your shell’s current directory wasn’t under the repo when the agent started—use `io chat --cwd /path/to/this/repo`.

**Cursor / IDE chat** is separate: it does **not** load IO’s `soul.md`. Only **`io chat`**, **`io ask`**, gateway, web UI, etc. use `load_soul`.

**Telegram / gateway:** the gateway’s working directory defaults to **`$HOME`** (when `terminal.cwd` is `.`), so walking upward from cwd usually **never** reaches your git repo. Set **`soul.workspace_root`** in `~/.io/config.yaml` to the directory that contains your `soul.md`, e.g.:

```yaml
soul:
  workspace_root: "/Users/you/Documents/GitHub/io"
```

Then `io doctor` should show **`soul_source`: `workspace_root`**.

**Prove the right file is loaded:** `io soul status` (add `--cwd ~` to mimic gateway). Check **`soul_path`**, **`soul_source`**, and **`preview`** (first lines of the file). If **`preview`** doesn’t show your persona header, the bot isn’t reading that file yet.

## Repo Layout

- `packages/`: runtime packages
- `skills/` and `optional-skills/`: bundled skill content
- `docs/`: operator and developer docs
- `scripts/`: repo automation
- `environments/`: tool/runtime environment definitions

## Development

```bash
uv sync
uv run io --help
uv run pytest
```

**`/model` in the REPL:** With no arguments, IO opens **one prompt** with **fuzzy Tab completion** (same dropdown style as slash commands) over models from **configured providers**. You can still **`/model anthropic:claude-…`** in one line. New installs default to a **free** OpenRouter model (`openrouter/nvidia/nemotron-3-super-120b-a12b:free`); override in `~/.io/config.yaml`. CLI: `io models` / `io models --search …` / `io models --all`.

### Typing `io` in any terminal (like `pi`)

`pi` is usually on your **PATH** from a global install (`pipx`, Homebrew, etc.). This repo’s CLI is the console script **`io`** → `io_cli.cli:main`; until something puts that on PATH, only `uv run io` from the clone works.

Pick one:

1. **Alias (simplest, always uses this repo’s lockfile)** — in `~/.zshrc`:

   ```bash
   alias io='uv run --directory /ABS/PATH/TO/THIS/REPO io'
   ```

   Then `source ~/.zshrc` and run `io` from any directory.

2. **Prepend the repo venv** — after `uv sync`:

   ```bash
   export PATH="/ABS/PATH/TO/THIS/REPO/.venv/bin:$PATH"
   ```

   Put that in `~/.zshrc` so bare `io` resolves to `.venv/bin/io`.

3. **Global tool install** (optional):

   ```bash
   cd /ABS/PATH/TO/THIS/REPO
   uv tool install .
   ```

   Ensure `uv tool`'s bin dir is on PATH (often `~/.local/bin`).

**Terminal tab (pi-style):** When the **interactive** REPL starts, IO prints an **OSC 0** title sequence (same mechanism as pi’s `setTitle`) so many terminals show **`φ io — ~/your/project`**. If the tab still says **`uv`** until IO boots, that’s the parent process name — put **`.venv/bin/io`** on PATH (option 2) so the shell spawns **`io`** directly. Set **`IO_TERMINAL_TITLE=0`** to disable title changes.

If `which io` shows nothing or the wrong binary, fix PATH/alias first. If `io` fails with `ModuleNotFoundError: No module named 'numpy'`, reinstall from this repo (`uv sync`) or `pip install numpy` into the **same environment** as the `io` executable (e.g. refresh a `pipx`/`pip --user` install). Holographic nuggets need NumPy when that tool is enabled.

## Gateway Parity Surfaces

IO now ships the multi-platform gateway adapter stack, including:

- `telegram`
- `discord`
- `whatsapp`
- `slack`
- `signal`
- `mattermost`
- `matrix`
- `homeassistant`
- `email`
- `sms`
- `dingtalk`
- `api-server`
- `webhook`

Check runtime status:

```bash
uv run io gateway status
```

### API Server (OpenAI-compatible)

Enable and start the gateway with `api-server` to expose:

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /health`

Default bind is `127.0.0.1:8642` (configurable via gateway platform extra config).

### Webhook Adapter

`webhook` provides an authenticated webhook ingress with:

- route-based event filtering
- HMAC signature validation
- idempotency for delivery retries
- rate limiting and payload size guardrails

Route handlers can template payload data into prompts and deliver agent output
to logs, GitHub PR comments (`gh pr comment`), or relay to connected messaging
platforms.
