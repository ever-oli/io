# Filesystem Checkpoints

IO automatically snapshots your working directory before making file changes, giving you a safety net to roll back if something goes wrong. Checkpoints are **enabled by default**.

## Quick Reference

| Command | Description |
|---------|-------------|
| `/rollback` | List all checkpoints with change stats |
| `/rollback <N>` | Restore to checkpoint N (also undoes last chat turn) |
| `/rollback diff <N>` | Preview diff between checkpoint N and current state |
| `/rollback <N> <file>` | Restore a single file from checkpoint N |

## What Triggers Checkpoints

- **File tools** Φ `write_file` and `patch`
- **Destructive terminal commands** Φ `rm`, `mv`, `sed -i`, output redirects (`>`), `git reset`/`clean`

## Configuration

```yaml
# ~/.io/config.yaml
checkpoints:
  enabled: true          # default: true
  max_snapshots: 50      # max checkpoints per directory
```

## Learn More

For the full guide Φ how shadow repos work, diff previews, file-level restore, conversation undo, safety guards, and best practices Φ see **[Checkpoints and /rollback](../checkpoints-and-rollback.md)**.
