---
name: aristotle-formal-proof
description: Submit formal proof goals via Harmonic Math Aristotle or IO’s lean bridge (uv run aristotle submit). Use when the user wants a theorem proved, checked, or formalized in Lean and they have Aristotle in the project environment.
version: 1.0.0
author: IO
license: MIT
metadata:
  io:
    tags: [mathematics, lean, formal-proof, aristotle, harmonic-math]
    homepage: https://github.com/ever-oli/io
    related_skills: [plan, systematic-debugging]
---

# Aristotle / formal proof submission

## When to use

- User asks to **prove** a mathematical statement, **verify** a claim in Lean, or run a **formal proof** workflow.
- Project already uses **Aristotle** (Harmonic Math) or you can run it with `uv run aristotle`.

## Preferred command (matches typical workflow)

From the **Lean project root** (or directory with `pyproject.toml` / `uv` Aristotle deps):

```bash
uv run aristotle submit "YOUR THEOREM STATEMENT HERE" --project-dir .
```

Example:

```bash
uv run aristotle submit "Prove that there are infinitely many primes." --project-dir .
```

## IO-native equivalent (same subprocess)

IO wraps the same invocation so you can use one entrypoint:

```bash
io lean submit "Prove that there are infinitely many primes." --cwd . --project-dir .
```

**Gauss-style `/prove` bridge** (configurable `lean.prove_argv`, default `uv run aristotle prove`):

```bash
io lean prove "your scope or statement" --cwd . --project-dir .
```

**Gauss-style `/draft` and `/formalize`** — set `lean.draft_argv` and `lean.formalize_argv` to your OpenGauss or wrapper CLIs, then:

```bash
io lean draft "informal goal …"
io lean formalize "statement to formalize …"
```

**Swarm / orchestration hook** — `io lean swarm "…"` with `lean.swarm_argv` pointing at an OpenGauss (or custom) multi-agent entrypoint.

**Draft / formalize / swarm:** set **`lean.draft_argv`**, **`lean.formalize_argv`**, **`lean.swarm_argv`** in config (no automatic fallback to `prove_argv`).

**Two provers:** configure **`lean.backends`** and **`lean.default_backend`**, then `io lean prove "…" --backend NAME` or `/lean prove @NAME …`. **OpenGauss TUI:** `io gauss chat` or `/gauss chat` in the REPL. See `io lean backends list` and [`docs/open_gauss_hermes_port.md`](../../../docs/open_gauss_hermes_port.md).

- `--cwd` — where `uv` runs (usually the repo root).
- `--project-dir` — Lean project root (defaults to `lean.default_project_dir` in `~/.io/config.yaml`, usually `.`).
- **`--project <name>`** — use a named root from `~/.io/lean/registry.yaml` (`io lean project add …`). Set `lean.prefer_registry_current: true` to default to the registry’s `current` pin when flags are omitted.
- Override **`prove_argv`** for [lean4-skills](https://github.com/cameronfreer/lean4-skills) or OpenGauss-style wrappers when you use them.

**Named projects** (OpenGauss-style pins, lighter than `.gauss/project.yaml`):

```bash
io lean project add my-math /path/to/lean-root --current
io lean project list
io lean submit "…" --cwd . --project my-math
```

Check toolchain:

```bash
io lean doctor
```

## In chat (REPL / gateway)

- `/lean submit Prove that there are infinitely many primes.`
- `/lean prove …` (same argv family as `io lean prove`)
- `/lean doctor`
- `/lean project list` (manage registry from chat)
- `/gauss …` — passthrough to the `gauss` CLI (same as `io gauss …`)
- `/gateway start` — background `io gateway run` (log `~/.io/gateway/run.log`)

## Agent playbook

1. Confirm the **exact statement** to prove (user wording or formal spec).
2. Identify the **project directory** containing the Lean/Aristotle setup.
3. Run **`io lean submit "…" --cwd <repo> --project-dir <lean-root>`** (or `uv run aristotle submit …` if IO is not on PATH).
4. Return **stdout/stderr** and exit code to the user; do not invent proof status.

## Limitations

- **Aristotle** may be cloud-backed or licensed separately — IO only runs the local CLI you have configured.
- If `io lean doctor` shows `aristotle_help_ok: false`, install/configure Aristotle in that project’s `uv` environment before retrying.

## See also

- [OpenGauss / Hermes port notes](../../../docs/open_gauss_hermes_port.md) in this repo.
