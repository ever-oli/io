---
sidebar_position: 1
title: "CLI Interface"
description: "Master the IO terminal interface Φ commands, keybindings, personalities, and more"
---

# CLI Interface

IO's CLI is a full terminal user interface (TUI) Φ not a web UI. It features multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, and streaming tool output. Built for people who live in the terminal.

## Running the CLI

```bash
# Start an interactive session (default)
io

# Single query mode (non-interactive)
io chat -q "Hello"

# With a specific model
io chat --model "anthropic/claude-sonnet-4"

# With a specific provider
io chat --provider nous        # Use Nous Portal
io chat --provider openrouter  # Force OpenRouter

# With specific toolsets
io chat --toolsets "web,terminal,skills"

# Start with one or more skills preloaded
io -s io-dev,github-auth
io chat -s github-pr-workflow -q "open a draft PR"

# Resume previous sessions
io --continue             # Resume the most recent CLI session (-c)
io --resume <session_id>  # Resume a specific session by ID (-r)

# Verbose mode (debug output)
io chat --verbose

# Isolated git worktree (for running multiple agents in parallel)
io -w                         # Interactive mode in worktree
io -w -q "Fix issue #123"     # Single query in worktree
```

## Interface Layout

<img className="docs-terminal-figure" src="/img/docs/cli-layout.svg" alt="Stylized preview of the IO CLI layout showing the banner, conversation area, and fixed input prompt." />
<p className="docs-figure-caption">The IO CLI banner, conversation stream, and fixed input prompt rendered as a stable docs figure instead of fragile text art.</p>

The welcome banner shows your model, terminal backend, working directory, available tools, and installed skills at a glance.

### Status Bar

A persistent status bar sits above the input area, updating in real time:

```
 ΦΦΦ claude-sonnet-4-20250514 Φ 12.4K/200K Φ [ΦΦΦΦΦΦΦΦΦΦ] 6% Φ $0.06 Φ 15m
```

| Element | Description |
|---------|-------------|
| Model name | Current model (truncated if longer than 26 chars) |
| Token count | Context tokens used / max context window |
| Context bar | Visual fill indicator with color-coded thresholds |
| Cost | Estimated session cost (or `n/a` for unknown/zero-priced models) |
| Duration | Elapsed session time |

The bar adapts to terminal width Φ full layout at Φ 76 columns, compact at 52Φ75, minimal (model + duration only) below 52.

**Context color coding:**

| Color | Threshold | Meaning |
|-------|-----------|---------|
| Green | < 50% | Plenty of room |
| Yellow | 50Φ80% | Getting full |
| Orange | 80Φ95% | Approaching limit |
| Red | Φ 95% | Near overflow Φ consider `/compress` |

Use `/usage` for a detailed breakdown including per-category costs (input vs output tokens).

### Session Resume Display

When resuming a previous session (`io -c` or `io --resume <id>`), a "Previous Conversation" panel appears between the banner and the input prompt, showing a compact recap of the conversation history. See [Sessions Φ Conversation Recap on Resume](sessions.md#conversation-recap-on-resume) for details and configuration.

## Keybindings

| Key | Action |
|-----|--------|
| `Enter` | Send message |
| `Alt+Enter` or `Ctrl+J` | New line (multi-line input) |
| `Alt+V` | Paste an image from the clipboard when supported by the terminal |
| `Ctrl+V` | Paste text and opportunistically attach clipboard images |
| `Ctrl+B` | Start/stop voice recording when voice mode is enabled (`voice.record_key`, default: `ctrl+b`) |
| `Ctrl+C` | Interrupt agent (double-press within 2s to force exit) |
| `Ctrl+D` | Exit |
| `Tab` | Accept auto-suggestion (ghost text) or autocomplete slash commands |

## Slash Commands

Type `/` to see the autocomplete dropdown. IO supports a large set of CLI slash commands, dynamic skill commands, and user-defined quick commands.

Common examples:

| Command | Description |
|---------|-------------|
| `/help` | Show command help |
| `/model` | Show or change the current model |
| `/tools` | List currently available tools |
| `/skills browse` | Browse the skills hub and official optional skills |
| `/background <prompt>` | Run a prompt in a separate background session |
| `/skin` | Show or switch the active CLI skin |
| `/voice on` | Enable CLI voice mode (press `Ctrl+B` to record) |
| `/voice tts` | Toggle spoken playback for IO replies |
| `/reasoning high` | Increase reasoning effort |
| `/title My Session` | Name the current session |

For the full built-in CLI and messaging lists, see [Slash Commands Reference](../reference/slash-commands.md).

For setup, providers, silence tuning, and messaging/Discord voice usage, see [Voice Mode](features/voice-mode.md).

:::tip
Commands are case-insensitive Φ `/HELP` works the same as `/help`. Installed skills also become slash commands automatically.
:::

## Quick Commands

You can define custom commands that run shell commands instantly without invoking the LLM. These work in both the CLI and messaging platforms (Telegram, Discord, etc.).

```yaml
# ~/.io/config.yaml
quick_commands:
  status:
    type: exec
    command: systemctl status io
  gpu:
    type: exec
    command: nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader
```

Then type `/status` or `/gpu` in any chat. See the [Configuration guide](/docs/user-guide/configuration#quick-commands) for more examples.

## Preloading Skills at Launch

If you already know which skills you want active for the session, pass them at launch time:

```bash
io -s io-dev,github-auth
io chat -s github-pr-workflow -s github-auth
```

IO loads each named skill into the session prompt before the first turn. The same flag works in interactive mode and single-query mode.

## Skill Slash Commands

Every installed skill in `~/.io/skills/` is automatically registered as a slash command. The skill name becomes the command:

```
/gif-search funny cats
/axolotl help me fine-tune Llama 3 on my dataset
/github-pr-workflow create a PR for the auth refactor

# Just the skill name loads it and lets the agent ask what you need:
/excalidraw
```

## Personalities

Set a predefined personality to change the agent's tone:

```
/personality pirate
/personality kawaii
/personality concise
```

Built-in personalities include: `helpful`, `concise`, `technical`, `creative`, `teacher`, `kawaii`, `catgirl`, `pirate`, `shakespeare`, `surfer`, `noir`, `uwu`, `philosopher`, `hype`.

You can also define custom personalities in `~/.io/config.yaml`:

```yaml
agent:
  personalities:
    helpful: "You are a helpful, friendly AI assistant."
    kawaii: "You are a kawaii assistant! Use cute expressions..."
    pirate: "Arrr! Ye be talkin' to Captain IO..."
    # Add your own!
```

## Multi-line Input

There are two ways to enter multi-line messages:

1. **`Alt+Enter` or `Ctrl+J`** Φ inserts a new line
2. **Backslash continuation** Φ end a line with `\` to continue:

```
Φ Write a function that:\
  1. Takes a list of numbers\
  2. Returns the sum
```

:::info
Pasting multi-line text is supported Φ use `Alt+Enter` or `Ctrl+J` to insert newlines, or simply paste content directly.
:::

## Interrupting the Agent

You can interrupt the agent at any point:

- **Type a new message + Enter** while the agent is working Φ it interrupts and processes your new instructions
- **`Ctrl+C`** Φ interrupt the current operation (press twice within 2s to force exit)
- In-progress terminal commands are killed immediately (SIGTERM, then SIGKILL after 1s)
- Multiple messages typed during interrupt are combined into one prompt

## Tool Progress Display

The CLI shows animated feedback as the agent works:

**Thinking animation** (during API calls):
```
  Φ (｡Φ́︿Φ̀｡) pondering... (1.2s)
  Φ (Φ_Φ) contemplating... (2.4s)
  Φ٩(ˊᗜˋ*)وΦ got it! (3.1s)
```

**Tool execution feed:**
```
  Φ 💻 terminal `ls -la` (0.3s)
  Φ 🔍 web_search (1.2s)
  Φ 📄 web_extract (2.1s)
```

Cycle through display modes with `/verbose`: `off Φ new Φ all Φ verbose`.

## Session Management

### Resuming Sessions

When you exit a CLI session, a resume command is printed:

```
Resume this session with:
  io --resume 20260225_143052_a1b2c3

Session:        20260225_143052_a1b2c3
Duration:       12m 34s
Messages:       28 (5 user, 18 tool calls)
```

Resume options:

```bash
io --continue                          # Resume the most recent CLI session
io -c                                  # Short form
io -c "my project"                     # Resume a named session (latest in lineage)
io --resume 20260225_143052_a1b2c3     # Resume a specific session by ID
io --resume "refactoring auth"         # Resume by title
io -r 20260225_143052_a1b2c3           # Short form
```

Resuming restores the full conversation history from SQLite. The agent sees all previous messages, tool calls, and responses Φ just as if you never left.

Use `/title My Session Name` inside a chat to name the current session, or `io sessions rename <id> <title>` from the command line. Use `io sessions list` to browse past sessions.

### Session Storage

CLI sessions are stored in IO's SQLite state database under `~/.io/state.db`. The database keeps:

- session metadata (ID, title, timestamps, token counters)
- message history
- lineage across compressed/resumed sessions
- full-text search indexes used by `session_search`

Some messaging adapters also keep per-platform transcript files alongside the database, but the CLI itself resumes from the SQLite session store.

### Context Compression

Long conversations are automatically summarized when approaching context limits:

```yaml
# In ~/.io/config.yaml
compression:
  enabled: true
  threshold: 0.50    # Compress at 50% of context limit by default
  summary_model: "google/gemini-3-flash-preview"  # Model used for summarization
```

When compression triggers, middle turns are summarized while the first 3 and last 4 turns are always preserved.

## Background Sessions

Run a prompt in a separate background session while continuing to use the CLI for other work:

```
/background Analyze the logs in /var/log and summarize any errors from today
```

IO immediately confirms the task and gives you back the prompt:

```
🔄 Background task #1 started: "Analyze the logs in /var/log and summarize..."
   Task ID: bg_143022_a1b2c3
```

### How It Works

Each `/background` prompt spawns a **completely separate agent session** in a daemon thread:

- **Isolated conversation** Φ the background agent has no knowledge of your current session's history. It receives only the prompt you provide.
- **Same configuration** Φ the background agent inherits your model, provider, toolsets, reasoning settings, and fallback model from the current session.
- **Non-blocking** Φ your foreground session stays fully interactive. You can chat, run commands, or even start more background tasks.
- **Multiple tasks** Φ you can run several background tasks simultaneously. Each gets a numbered ID.

### Results

When a background task finishes, the result appears as a panel in your terminal:

```
ΦΦΦ ΦΦΦ IO (background #1) ΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦ
Φ Found 3 errors in syslog from today:                         Φ
Φ 1. OOM killer invoked at 03:22 Φ killed process nginx        Φ
Φ 2. Disk I/O error on /dev/sda1 at 07:15                      Φ
Φ 3. Failed SSH login attempts from 192.168.1.50 at 14:30      Φ
ΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦ
```

If the task fails, you'll see an error notification instead. If `display.bell_on_complete` is enabled in your config, the terminal bell rings when the task finishes.

### Use Cases

- **Long-running research** Φ "/background research the latest developments in quantum error correction" while you work on code
- **File processing** Φ "/background analyze all Python files in this repo and list any security issues" while you continue a conversation
- **Parallel investigations** Φ start multiple background tasks to explore different angles simultaneously

:::info
Background sessions do not appear in your main conversation history. They are standalone sessions with their own task ID (e.g., `bg_143022_a1b2c3`).
:::

## Quiet Mode

By default, the CLI runs in quiet mode which:
- Suppresses verbose logging from tools
- Enables kawaii-style animated feedback
- Keeps output clean and user-friendly

For debug output:
```bash
io chat --verbose
```
