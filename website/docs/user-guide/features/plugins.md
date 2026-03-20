---
sidebar_position: 20
---

# Plugins

IO has a plugin system for adding custom tools, hooks, and integrations without modifying core code.

**Φ [Build an IO Plugin](/docs/guides/build-an-io-plugin)** Φ step-by-step guide with a complete working example.

## Quick overview

Drop a directory into `~/.io/plugins/` with a `plugin.yaml` and Python code:

```
~/.io/plugins/my-plugin/
ΦΦΦ plugin.yaml      # manifest
ΦΦΦ __init__.py      # register() Φ wires schemas to handlers
ΦΦΦ schemas.py       # tool schemas (what the LLM sees)
ΦΦΦ tools.py         # tool handlers (what runs when called)
```

Start IO Φ your tools appear alongside built-in tools. The model can call them immediately.

## What plugins can do

| Capability | How |
|-----------|-----|
| Add tools | `ctx.register_tool(name, schema, handler)` |
| Add hooks | `ctx.register_hook("post_tool_call", callback)` |
| Ship data files | `Path(__file__).parent / "data" / "file.yaml"` |
| Bundle skills | Copy `skill.md` to `~/.io/skills/` at load time |
| Gate on env vars | `requires_env: [API_KEY]` in plugin.yaml |
| Distribute via pip | `[project.entry-points."io.plugins"]` |

## Plugin discovery

| Source | Path | Use case |
|--------|------|----------|
| User | `~/.io/plugins/` | Personal plugins |
| Project | `.io/plugins/` | Project-specific plugins |
| pip | `io.plugins` entry_points | Distributed packages |

## Available hooks

| Hook | Fires when |
|------|-----------|
| `pre_tool_call` | Before any tool executes |
| `post_tool_call` | After any tool returns |
| `pre_llm_call` | Before LLM API request |
| `post_llm_call` | After LLM API response |
| `on_session_start` | Session begins |
| `on_session_end` | Session ends |

## Managing plugins

```
/plugins              # list loaded plugins in a session
io config set display.show_cost true  # show cost in status bar
```

See the **[full guide](/docs/guides/build-an-io-plugin)** for handler contracts, schema format, hook behavior, error handling, and common mistakes.
