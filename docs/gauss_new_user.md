# Lean (Aristotle) vs OpenGauss in IO

[OpenGauss](https://github.com/math-inc/OpenGauss) is a full product (interactive `gauss` CLI, TUI swarm, RL, …). **IO does not embed that stack.**

## Lean = subprocess to your prover (default: Aristotle)

`io lean submit|prove|draft|formalize|swarm` and `/lean …` run whatever you set in **`lean.*_argv`** (defaults: `uv run aristotle submit` / `prove`). Set **`lean.draft_argv`**, **`lean.formalize_argv`**, **`lean.swarm_argv`** explicitly if you use those verbs.

Optional **`lean.backends`** + **`lean.default_backend`** for multiple provers: `io lean prove "…" --backend NAME`, `/lean prove @NAME …`, `io lean backends list`.

## OpenGauss = real `gauss` binary

```bash
pip install gauss-agent   # or: uv add gauss-agent
io gauss chat             # TUI with /prove, /draft, …
```

In the REPL: **`/gauss chat`**, **`/gauss --help`**, etc. (same as `io gauss …`).

From Telegram/other messaging, IO replies with a short hint to run `io gauss` on the host (no interactive TUI from chat).

## Slash: start the gateway (background)

In the REPL or gateway chat:

- **`/gateway start`** or **`/gateway run`** — spawns **`io gateway run`** detached; log under `~/.io/gateway/run.log`
- **`/gateway status`** — same snapshot idea as **`/platforms`** (configured platforms + runtime)

## Tirith (optional)

```bash
io security tirith-install   # needs Rust cargo; or install via brew/npm per upstream
```

See [`open_gauss_hermes_port.md`](open_gauss_hermes_port.md) for the full parity map.
