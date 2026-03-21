# IO memory layers: file memories, session index, nuggets, Honcho

This doc explains how the **original IO memory stack** (files + SQLite + tools) relates to **Nuggets (HRR)** and optional **Honcho**. Enabling Honcho does **not** remove or replace the previous layer unless you deliberately stop using those tools or trim toolsets.

---

## 1. Previous IO memory layer (still the default)

These ship with the agent and stay **on** unless you change toolsets or config.

### Injected every turn (system prompt)

- **`memory_snapshot()`** (`io_cli.config`) reads `~/.io/memories/MEMORY.md` and `USER.md` (if present) and appends them to the system prompt in **`run_prompt`** (after soul, before the user message).
- So long-term notes in those files are **always visible** to the model without a tool call.

### `memory` tool

- **`memory`** reads/writes the same files: `view`, `save_note` → `MEMORY.md`, `save_user` → `USER.md` (see `io_cli/tools/memory.py`).
- Size limits are enforced per file in code (`LIMITS`).

### Session index + search

- **`SessionDB`** (`~/.io/state.db`) indexes messages; **FTS5** backs search.
- **`session_search`** tool queries that index for cross-session recall.

### Context compression

- **`ContextCompressor`** can summarize long histories (config under `compression`) — separate from memory files, but part of “how the session remembers.”

### Nuggets (HRR)

- **`nuggets`** tool + files under **`~/.io/nuggets/`** (vector-style local recall).
- Optional **`nuggets.auto_promote`** merges high-recall facts into **`~/.io/memories/MEMORY.md`**, i.e. into the **same** file layer the snapshot reads.

**Summary:** the “previous memory layer” = **markdown memories + SQLite session index + optional nugget vectors + compression**. None of this is turned off when you add Honcho.

---

## 2. Nuggets vs file memories

| Piece | Role |
|--------|------|
| **`MEMORY.md` / `USER.md`** | Human-readable, agent-editable via `memory` tool; always injected via `memory_snapshot` when non-empty. |
| **Nuggets** | Structured local recall + optional promotion **into** `MEMORY.md`. |

---

## 3. Honcho (optional, remote)

- **Honcho** adds a **server-side** identity/session memory API (IO defaults to **Honcho API v3**). It does **not** delete local files or SQLite.
- Typical use: fetch **session context**, **peer cards**, **semantic session search**, **conclusions** — complementary to FTS and file memories.

Enable in `~/.io/config.yaml` and add the **`honcho`** toolset so the model can call the tools. See README **Hermes-style TUI parity** table for keys (`workspace_id`, `session_id`, peers, etc.).

---

## 4. Stacking everything (recommended view)

| Layer | What it is |
|--------|------------|
| **Soul + `memory_snapshot`** | Persona + `MEMORY.md` / `USER.md` every turn. |
| **`memory` tool** | Edit those files explicitly. |
| **`session_search` + FTS** | Search past transcripts locally. |
| **Nuggets** | Local HRR + optional promotion to `MEMORY.md`. |
| **Honcho** | Optional remote user/session modeling when a Honcho server is available. |

You can run **all** of these together. Hermes-style “closed loop” often emphasizes Honcho for **dialectic / user modeling** while keeping **file memories + nuggets** for **offline, cheap, repo-portable** memory.

---

## 5. Legacy Honcho installs

If your server still uses the old `GET /api/context` style:

```yaml
honcho:
  api_version: legacy
  paths:
    context: /api/context
    profile: /api/profile
    search: /api/search
    conclude: /api/conclude
```
