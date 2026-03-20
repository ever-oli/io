---
sidebar_position: 1
title: "Quickstart"
description: "Your first conversation with IO Φ from install to chatting in 2 minutes"
---

# Quickstart

This guide walks you through installing IO, setting up a provider, and having your first conversation. By the end, you'll know the key features and how to explore further.

## 1. Install IO

Run the one-line installer:

```bash
# Linux / macOS / WSL2
curl -fsSL https://raw.githubusercontent.com/ever-oli/io/main/scripts/install.sh | bash
```

:::tip Windows Users
Install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) first, then run the command above inside your WSL2 terminal.
:::

After it finishes, reload your shell:

```bash
source ~/.bashrc   # or source ~/.zshrc
```

## 2. Set Up a Provider

The installer configures your LLM provider automatically. To change it later, use one of these commands:

```bash
io model       # Choose your LLM provider and model
io tools       # Configure which tools are enabled
io setup       # Or configure everything at once
```

`io model` walks you through selecting an inference provider:

| Provider | What it is | How to set up |
|----------|-----------|---------------|
| **Nous Portal** | Subscription-based, zero-config | OAuth login via `io model` |
| **OpenAI Codex** | ChatGPT OAuth, uses Codex models | Device code auth via `io model` |
| **Anthropic** | Claude models directly (Pro/Max or API key) | `io model` with Claude Code auth, or an Anthropic API key |
| **OpenRouter** | Multi-provider routing across many models | Enter your API key |
| **Z.AI** | GLM / Zhipu-hosted models | Set `GLM_API_KEY` / `ZAI_API_KEY` |
| **Kimi / Moonshot** | Moonshot-hosted coding and chat models | Set `KIMI_API_KEY` |
| **MiniMax** | International MiniMax endpoint | Set `MINIMAX_API_KEY` |
| **MiniMax China** | China-region MiniMax endpoint | Set `MINIMAX_CN_API_KEY` |
| **Alibaba Cloud** | Qwen models via DashScope | Set `DASHSCOPE_API_KEY` |
| **Kilo Code** | KiloCode-hosted models | Set `KILOCODE_API_KEY` |
| **OpenCode Zen** | Pay-as-you-go access to curated models | Set `OPENCODE_ZEN_API_KEY` |
| **OpenCode Go** | $10/month subscription for open models | Set `OPENCODE_GO_API_KEY` |
| **Vercel AI Gateway** | Vercel AI Gateway routing | Set `AI_GATEWAY_API_KEY` |
| **Custom Endpoint** | VLLM, SGLang, or any OpenAI-compatible API | Set base URL + API key |

:::tip
You can switch providers at any time with `io model` Φ no code changes, no lock-in.
:::

## 3. Start Chatting

```bash
io
```

That's it! You'll see a welcome banner with your model, available tools, and skills. Type a message and press Enter.

```
Φ What can you help me with?
```

The agent has access to tools for web search, file operations, terminal commands, and more Φ all out of the box.

## 4. Try Key Features

### Ask it to use the terminal

```
Φ What's my disk usage? Show the top 5 largest directories.
```

The agent will run terminal commands on your behalf and show you the results.

### Use slash commands

Type `/` to see an autocomplete dropdown of all commands:

| Command | What it does |
|---------|-------------|
| `/help` | Show all available commands |
| `/tools` | List available tools |
| `/model` | Switch models interactively |
| `/personality pirate` | Try a fun personality |
| `/save` | Save the conversation |

### Multi-line input

Press `Alt+Enter` or `Ctrl+J` to add a new line. Great for pasting code or writing detailed prompts.

### Interrupt the agent

If the agent is taking too long, just type a new message and press Enter Φ it interrupts the current task and switches to your new instructions. `Ctrl+C` also works.

### Resume a session

When you exit, io prints a resume command:

```bash
io --continue    # Resume the most recent session
io -c            # Short form
```

## 5. Explore Further

Here are some things to try next:

### Set up a sandboxed terminal

For safety, run the agent in a Docker container or on a remote server:

```bash
io config set terminal.backend docker    # Docker isolation
io config set terminal.backend ssh       # Remote server
```

### Connect messaging platforms

Chat with IO from your phone or other surfaces via Telegram, Discord, Slack, WhatsApp, Signal, Email, or Home Assistant:

```bash
io gateway setup    # Interactive platform configuration
```

### Add voice mode

Want microphone input in the CLI or spoken replies in messaging?

```bash
pip install io[voice]

# Optional but recommended for free local speech-to-text
pip install faster-whisper
```

Then start IO and enable it inside the CLI:

```text
/voice on
```

Press `Ctrl+B` to record, or use `/voice tts` to have IO speak its replies. See [Voice Mode](../user-guide/features/voice-mode.md) for the full setup across CLI, Telegram, Discord, and Discord voice channels.

### Schedule automated tasks

```
Φ Every morning at 9am, check Hacker News for AI news and send me a summary on Telegram.
```

The agent will set up a cron job that runs automatically via the gateway.

### Browse and install skills

```bash
io skills search kubernetes
io skills search react --source skills-sh
io skills search https://mintlify.com/docs --source well-known
io skills install openai/skills/k8s
io skills install official/security/1password
io skills install skills-sh/vercel-labs/json-render/json-render-react --force
```

Tips:
- Use `--source skills-sh` to search the public `skills.sh` directory.
- Use `--source well-known` with a docs/site URL to discover skills from `/.well-known/skills/index.json`.
- Use `--force` only after reviewing a third-party skill. It can override non-dangerous policy blocks, but not a `dangerous` scan verdict.

Or use the `/skills` slash command inside chat.

### Use IO inside an editor via ACP

IO can also run as an ACP server for ACP-compatible editors like VS Code, Zed, and JetBrains:

```bash
pip install -e '.[acp]'
io acp
```

See [ACP Editor Integration](../user-guide/features/acp.md) for setup details.

### Try MCP servers

Connect to external tools via the Model Context Protocol:

```yaml
# Add to ~/.io/config.yaml
mcp_servers:
  github:
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_PERSONAL_ACCESS_TOKEN: "ghp_xxx"
```

---

## Quick Reference

| Command | Description |
|---------|-------------|
| `io` | Start chatting |
| `io model` | Choose your LLM provider and model |
| `io tools` | Configure which tools are enabled per platform |
| `io setup` | Full setup wizard (configures everything at once) |
| `io doctor` | Diagnose issues |
| `io update` | Update to latest version |
| `io gateway` | Start the messaging gateway |
| `io --continue` | Resume last session |

## Next Steps

- **[CLI Guide](../user-guide/cli.md)** Φ Master the terminal interface
- **[Configuration](../user-guide/configuration.md)** Φ Customize your setup
- **[Messaging Gateway](../user-guide/messaging/index.md)** Φ Connect Telegram, Discord, Slack, WhatsApp, Signal, Email, or Home Assistant
- **[Tools & Toolsets](../user-guide/features/tools.md)** Φ Explore available capabilities
