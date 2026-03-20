# honcho-integration-spec

Comparison of IO vs. openclaw-honcho Φ and a porting spec for bringing IO patterns into other Honcho integrations.

---

## Overview

Two independent Honcho integrations have been built for two different agent runtimes: **IO** (Python, baked into the runner) and **openclaw-honcho** (TypeScript plugin via hook/tool API). Both use the same Honcho peer paradigm Φ dual peer model, `session.context()`, `peer.chat()` Φ but they made different tradeoffs at every layer.

This document maps those tradeoffs and defines a porting spec: a set of IO-originated patterns, each stated as an integration-agnostic interface, that any Honcho integration can adopt regardless of runtime or language.

> **Scope** Both integrations work correctly today. This spec is about the delta Φ patterns in IO that are worth propagating and patterns in openclaw-honcho that IO should eventually adopt. The spec is additive, not prescriptive.

---

## Architecture comparison

### IO: baked-in runner

Honcho is initialised directly inside `AIAgent.__init__`. There is no plugin boundary. Session management, context injection, async prefetch, and CLI surface are all first-class concerns of the runner. Context is injected once per session (baked into `_cached_system_prompt`) and never re-fetched mid-session Φ this maximises prefix cache hits at the LLM provider.

Turn flow:

```
user message
  Φ _honcho_prefetch()       (reads cache Φ no HTTP)
  Φ _build_system_prompt()   (first turn only, cached)
  Φ LLM call
  Φ response
  Φ _honcho_fire_prefetch()  (daemon threads, turn end)
       Φ prefetch_context() thread  ΦΦΦ
       Φ prefetch_dialectic() thread ΦΦΦ _context_cache / _dialectic_cache
```

### openclaw-honcho: hook-based plugin

The plugin registers hooks against OpenClaw's event bus. Context is fetched synchronously inside `before_prompt_build` on every turn. Message capture happens in `agent_end`. The multi-agent hierarchy is tracked via `subagent_spawned`. This model is correct but every turn pays a blocking Honcho round-trip before the LLM call can begin.

Turn flow:

```
user message
  Φ before_prompt_build (BLOCKING HTTP Φ every turn)
       Φ session.context()
  Φ system prompt assembled
  Φ LLM call
  Φ response
  Φ agent_end hook
       Φ session.addMessages()
       Φ session.setMetadata()
```

---

## Diff table

| Dimension | IO | openclaw-honcho |
|---|---|---|
| **Context injection timing** | Once per session (cached). Zero HTTP on response path after turn 1. | Every turn, blocking. Fresh context per turn but adds latency. |
| **Prefetch strategy** | Daemon threads fire at turn end; consumed next turn from cache. | None. Blocking call at prompt-build time. |
| **Dialectic (peer.chat)** | Prefetched async; result injected into system prompt next turn. | On-demand via `honcho_recall` / `honcho_analyze` tools. |
| **Reasoning level** | Dynamic: scales with message length. Floor = config default. Cap = "high". | Fixed per tool: recall=minimal, analyze=medium. |
| **Memory modes** | `user_memory_mode` / `agent_memory_mode`: hybrid / honcho / local. | None. Always writes to Honcho. |
| **Write frequency** | async (background queue), turn, session, N turns. | After every agent_end (no control). |
| **AI peer identity** | `observe_me=True`, `seed_ai_identity()`, `get_ai_representation()`, SOUL.md Φ AI peer. | Agent files uploaded to agent peer at setup. No ongoing self-observation. |
| **Context scope** | User peer + AI peer representation, both injected. | User peer (owner) representation + conversation summary. `peerPerspective` on context call. |
| **Session naming** | per-directory / global / manual map / title-based. | Derived from platform session key. |
| **Multi-agent** | Single-agent only. | Parent observer hierarchy via `subagent_spawned`. |
| **Tool surface** | Single `query_user_context` tool (on-demand dialectic). | 6 tools: session, profile, search, context (fast) + recall, analyze (LLM). |
| **Platform metadata** | Not stripped. | Explicitly stripped before Honcho storage. |
| **Message dedup** | None. | `lastSavedIndex` in session metadata prevents re-sending. |
| **CLI surface in prompt** | Management commands injected into system prompt. Agent knows its own CLI. | Not injected. |
| **AI peer name in identity** | Replaces "IO" in DEFAULT_AGENT_IDENTITY when configured. | Not implemented. |
| **QMD / local file search** | Not implemented. | Passthrough tools when QMD backend configured. |
| **Workspace metadata** | Not implemented. | `agentPeerMap` in workspace metadata tracks agentΦpeer ID. |

---

## Patterns

Six patterns from IO are worth adopting in any Honcho integration. Each is described as an integration-agnostic interface.

**IO contributes:**
- Async prefetch (zero-latency)
- Dynamic reasoning level
- Per-peer memory modes
- AI peer identity formation
- Session naming strategies
- CLI surface injection

**openclaw-honcho contributes back (IO should adopt):**
- `lastSavedIndex` dedup
- Platform metadata stripping
- Multi-agent observer hierarchy
- `peerPerspective` on `context()`
- Tiered tool surface (fast/LLM)
- Workspace `agentPeerMap`

---

## Spec: async prefetch

### Problem

Calling `session.context()` and `peer.chat()` synchronously before each LLM call adds 200Φ800ms of Honcho round-trip latency to every turn.

### Pattern

Fire both calls as non-blocking background work at the **end** of each turn. Store results in a per-session cache keyed by session ID. At the **start** of the next turn, pop from cache Φ the HTTP is already done. First turn is cold (empty cache); all subsequent turns are zero-latency on the response path.

### Interface contract

```typescript
interface AsyncPrefetch {
  // Fire context + dialectic fetches at turn end. Non-blocking.
  firePrefetch(sessionId: string, userMessage: string): void;

  // Pop cached results at turn start. Returns empty if cache is cold.
  popContextResult(sessionId: string): ContextResult | null;
  popDialecticResult(sessionId: string): string | null;
}

type ContextResult = {
  representation: string;
  card: string[];
  aiRepresentation?: string;  // AI peer context if enabled
  summary?: string;           // conversation summary if fetched
};
```

### Implementation notes

- **Python:** `threading.Thread(daemon=True)`. Write to `dict[session_id, result]` Φ GIL makes this safe for simple writes.
- **TypeScript:** `Promise` stored in `Map<string, Promise<ContextResult>>`. Await at pop time. If not resolved yet, return null Φ do not block.
- The pop is destructive: clears the cache entry after reading so stale data never accumulates.
- Prefetch should also fire on first turn (even though it won't be consumed until turn 2).

### openclaw-honcho adoption

Move `session.context()` from `before_prompt_build` to a post-`agent_end` background task. Store result in `state.contextCache`. In `before_prompt_build`, read from cache instead of calling Honcho. If cache is empty (turn 1), inject nothing Φ the prompt is still valid without Honcho context on the first turn.

---

## Spec: dynamic reasoning level

### Problem

Honcho's dialectic endpoint supports reasoning levels from `minimal` to `max`. A fixed level per tool wastes budget on simple queries and under-serves complex ones.

### Pattern

Select the reasoning level dynamically based on the user's message. Use the configured default as a floor. Bump by message length. Cap auto-selection at `high` Φ never select `max` automatically.

### Logic

```
< 120 chars  Φ default (typically "low")
120Φ400 chars Φ one level above default (cap at "high")
> 400 chars  Φ two levels above default (cap at "high")
```

### Config key

Add `dialecticReasoningLevel` (string, default `"low"`). This sets the floor. The dynamic bump always applies on top.

### openclaw-honcho adoption

Apply in `honcho_recall` and `honcho_analyze`: replace fixed `reasoningLevel` with the dynamic selector. `honcho_recall` uses floor `"minimal"`, `honcho_analyze` uses floor `"medium"` Φ both still bump with message length.

---

## Spec: per-peer memory modes

### Problem

Users want independent control over whether user context and agent context are written locally, to Honcho, or both.

### Modes

| Mode | Effect |
|---|---|
| `hybrid` | Write to both local files and Honcho (default) |
| `honcho` | Honcho only Φ disable corresponding local file writes |
| `local` | Local files only Φ skip Honcho sync for this peer |

### Config schema

```json
{
  "memoryMode": "hybrid",
  "userMemoryMode": "honcho",
  "agentMemoryMode": "hybrid"
}
```

Resolution order: per-peer field wins Φ shorthand `memoryMode` Φ default `"hybrid"`.

### Effect on Honcho sync

- `userMemoryMode=local`: skip adding user peer messages to Honcho
- `agentMemoryMode=local`: skip adding assistant peer messages to Honcho
- Both local: skip `session.addMessages()` entirely
- `userMemoryMode=honcho`: disable local USER.md writes
- `agentMemoryMode=honcho`: disable local MEMORY.md / SOUL.md writes

---

## Spec: AI peer identity formation

### Problem

Honcho builds the user's representation organically by observing what the user says. The same mechanism exists for the AI peer Φ but only if `observe_me=True` is set for the agent peer. Without it, the agent peer accumulates nothing.

Additionally, existing persona files (SOUL.md, IDENTITY.md) should seed the AI peer's Honcho representation at first activation.

### Part A: observe_me=True for agent peer

```typescript
await session.addPeers([
  [ownerPeer.id, { observeMe: true,  observeOthers: false }],
  [agentPeer.id, { observeMe: true,  observeOthers: true  }], // was false
]);
```

One-line change. Foundational. Without it, the AI peer representation stays empty regardless of what the agent says.

### Part B: seedAiIdentity()

```typescript
async function seedAiIdentity(
  agentPeer: Peer,
  content: string,
  source: string
): Promise<boolean> {
  const wrapped = [
    `<ai_identity_seed>`,
    `<source>${source}</source>`,
    ``,
    content.trim(),
    `</ai_identity_seed>`,
  ].join("\n");

  await agentPeer.addMessage("assistant", wrapped);
  return true;
}
```

### Part C: migrate agent files at setup

During `honcho setup`, upload agent-self files (SOUL.md, IDENTITY.md, AGENTS.md) to the agent peer via `seedAiIdentity()` instead of `session.uploadFile()`. This routes content through Honcho's observation pipeline.

### Part D: AI peer name in identity

When the agent has a configured name, prepend it to the injected system prompt:

```typescript
const namePrefix = agentName ? `You are ${agentName}.\n\n` : "";
return { systemPrompt: namePrefix + "## User Memory Context\n\n" + sections };
```

### CLI surface

```
honcho identity <file>    # seed from file
honcho identity --show    # show current AI peer representation
```

---

## Spec: session naming strategies

### Problem

A single global session means every project shares the same Honcho context. Per-directory sessions provide isolation without requiring users to name sessions manually.

### Strategies

| Strategy | Session key | When to use |
|---|---|---|
| `per-directory` | basename of CWD | Default. Each project gets its own session. |
| `global` | fixed string `"global"` | Single cross-project session. |
| manual map | user-configured per path | `sessions` config map overrides directory basename. |
| title-based | sanitized session title | When agent supports named sessions set mid-conversation. |

### Config schema

```json
{
  "sessionStrategy": "per-directory",
  "sessionPeerPrefix": false,
  "sessions": {
    "/home/user/projects/foo": "foo-project"
  }
}
```

### CLI surface

```
honcho sessions              # list all mappings
honcho map <name>            # map cwd to session name
honcho map                   # no-arg = list mappings
```

Resolution order: manual map Φ session title Φ directory basename Φ platform key.

---

## Spec: CLI surface injection

### Problem

When a user asks "how do I change my memory settings?" the agent either hallucinates or says it doesn't know. The agent should know its own management interface.

### Pattern

When Honcho is active, append a compact command reference to the system prompt. Keep it under 300 chars.

```
# Honcho memory integration
Active. Session: {sessionKey}. Mode: {mode}.
Management commands:
  honcho status                    Φ show config + connection
  honcho mode [hybrid|honcho|local] Φ show or set memory mode
  honcho sessions                  Φ list session mappings
  honcho map <name>                Φ map directory to session
  honcho identity [file] [--show]  Φ seed or show AI identity
  honcho setup                     Φ full interactive wizard
```

---

## openclaw-honcho checklist

Ordered by impact:

- [ ] **Async prefetch** Φ move `session.context()` out of `before_prompt_build` into post-`agent_end` background Promise
- [ ] **observe_me=True for agent peer** Φ one-line change in `session.addPeers()`
- [ ] **Dynamic reasoning level** Φ add helper; apply in `honcho_recall` and `honcho_analyze`; add `dialecticReasoningLevel` to config
- [ ] **Per-peer memory modes** Φ add `userMemoryMode` / `agentMemoryMode` to config; gate Honcho sync and local writes
- [ ] **seedAiIdentity()** Φ add helper; use during setup migration for SOUL.md / IDENTITY.md
- [ ] **Session naming strategies** Φ add `sessionStrategy`, `sessions` map, `sessionPeerPrefix`
- [ ] **CLI surface injection** Φ append command reference to `before_prompt_build` return value
- [ ] **honcho identity subcommand** Φ seed from file or `--show` current representation
- [ ] **AI peer name injection** Φ if `aiPeer` name configured, prepend to injected system prompt
- [ ] **honcho mode / sessions / map** Φ CLI parity with IO

Already done in openclaw-honcho (do not re-implement): `lastSavedIndex` dedup, platform metadata stripping, multi-agent parent observer, `peerPerspective` on `context()`, tiered tool surface, workspace `agentPeerMap`, QMD passthrough, self-hosted Honcho.

---

## nanobot-honcho checklist

Greenfield integration. Start from openclaw-honcho's architecture and apply all IO patterns from day one.

### Phase 1 Φ core correctness

- [ ] Dual peer model (owner + agent peer), both with `observe_me=True`
- [ ] Message capture at turn end with `lastSavedIndex` dedup
- [ ] Platform metadata stripping before Honcho storage
- [ ] Async prefetch from day one Φ do not implement blocking context injection
- [ ] Legacy file migration at first activation (USER.md Φ owner peer, SOUL.md Φ `seedAiIdentity()`)

### Phase 2 Φ configuration

- [ ] Config schema: `apiKey`, `workspaceId`, `baseUrl`, `memoryMode`, `userMemoryMode`, `agentMemoryMode`, `dialecticReasoningLevel`, `sessionStrategy`, `sessions`
- [ ] Per-peer memory mode gating
- [ ] Dynamic reasoning level
- [ ] Session naming strategies

### Phase 3 Φ tools and CLI

- [ ] Tool surface: `honcho_profile`, `honcho_recall`, `honcho_analyze`, `honcho_search`, `honcho_context`
- [ ] CLI: `setup`, `status`, `sessions`, `map`, `mode`, `identity`
- [ ] CLI surface injection into system prompt
- [ ] AI peer name wired into agent identity
