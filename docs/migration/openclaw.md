# Migrating from OpenClaw to IO

This guide covers how to import your OpenClaw settings, memories, skills, and API keys into IO.

## Three Ways to Migrate

### 1. Automatic (during first-time setup)

When you run `io setup` for the first time and IO detects `~/.openclaw`, it automatically offers to import your OpenClaw data before configuration begins. Just accept the prompt and everything is handled for you.

### 2. CLI Command (quick, scriptable)

```bash
io claw migrate                      # Full migration with confirmation prompt
io claw migrate --dry-run            # Preview what would happen
io claw migrate --preset user-data   # Migrate without API keys/secrets
io claw migrate --yes                # Skip confirmation prompt
```

**All options:**

| Flag | Description |
|------|-------------|
| `--source PATH` | Path to OpenClaw directory (default: `~/.openclaw`) |
| `--dry-run` | Preview only Φ no files are modified |
| `--preset {user-data,full}` | Migration preset (default: `full`). `user-data` excludes secrets |
| `--overwrite` | Overwrite existing files (default: skip conflicts) |
| `--migrate-secrets` | Include allowlisted secrets (auto-enabled with `full` preset) |
| `--workspace-target PATH` | Copy workspace instructions (AGENTS.md) to this absolute path |
| `--skill-conflict {skip,overwrite,rename}` | How to handle skill name conflicts (default: `skip`) |
| `--yes`, `-y` | Skip confirmation prompts |

### 3. Agent-Guided (interactive, with previews)

Ask the agent to run the migration for you:

```
> Migrate my OpenClaw setup to IO
```

The agent will use the `openclaw-migration` skill to:
1. Run a dry-run first to preview changes
2. Ask about conflict resolution (SOUL.md, skills, etc.)
3. Let you choose between `user-data` and `full` presets
4. Execute the migration with your choices
5. Print a detailed summary of what was migrated

## What Gets Migrated

### `user-data` preset
| Item | Source | Destination |
|------|--------|-------------|
| SOUL.md | `~/.openclaw/workspace/SOUL.md` | `~/.io/SOUL.md` |
| Memory entries | `~/.openclaw/workspace/MEMORY.md` | `~/.io/memories/MEMORY.md` |
| User profile | `~/.openclaw/workspace/USER.md` | `~/.io/memories/USER.md` |
| Skills | `~/.openclaw/workspace/skills/` | `~/.io/skills/openclaw-imports/` |
| Command allowlist | `~/.openclaw/workspace/exec_approval_patterns.yaml` | Merged into `~/.io/config.yaml` |
| Messaging settings | `~/.openclaw/config.yaml` (TELEGRAM_ALLOWED_USERS, MESSAGING_CWD) | `~/.io/.env` |
| TTS assets | `~/.openclaw/workspace/tts/` | `~/.io/tts/` |

### `full` preset (adds to `user-data`)
| Item | Source | Destination |
|------|--------|-------------|
| Telegram bot token | `~/.openclaw/config.yaml` | `~/.io/.env` |
| OpenRouter API key | `~/.openclaw/.env` or config | `~/.io/.env` |
| OpenAI API key | `~/.openclaw/.env` or config | `~/.io/.env` |
| Anthropic API key | `~/.openclaw/.env` or config | `~/.io/.env` |
| ElevenLabs API key | `~/.openclaw/.env` or config | `~/.io/.env` |

Only these 6 allowlisted secrets are ever imported. Other credentials are skipped and reported.

## Conflict Handling

By default, the migration **will not overwrite** existing IO data:

- **SOUL.md** Φ skipped if one already exists in `~/.io/`
- **Memory entries** Φ skipped if memories already exist (to avoid duplicates)
- **Skills** Φ skipped if a skill with the same name already exists
- **API keys** Φ skipped if the key is already set in `~/.io/.env`

To overwrite conflicts, use `--overwrite`. The migration creates backups before overwriting.

For skills, you can also use `--skill-conflict rename` to import conflicting skills under a new name (e.g., `skill-name-imported`).

## Migration Report

Every migration (including dry runs) produces a report showing:
- **Migrated items** Φ what was successfully imported
- **Conflicts** Φ items skipped because they already exist
- **Skipped items** Φ items not found in the source
- **Errors** Φ items that failed to import

For execute runs, the full report is saved to `~/.io/migration/openclaw/<timestamp>/`.

## Troubleshooting

### "OpenClaw directory not found"
The migration looks for `~/.openclaw` by default. If your OpenClaw is installed elsewhere, use `--source`:
```bash
io claw migrate --source /path/to/.openclaw
```

### "Migration script not found"
The migration script ships with IO. If you installed via pip (not git clone), the `optional-skills/` directory may not be present. Install the skill from the Skills Hub:
```bash
io skills install openclaw-migration
```

### Memory overflow
If your OpenClaw MEMORY.md or USER.md exceeds IO' character limits, excess entries are exported to an overflow file in the migration report directory. You can manually review and add the most important ones.
