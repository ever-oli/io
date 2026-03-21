# Example repo-local SOUL

Copy to **`soul.md`** (or `SOUL.md`) in this repo root — that file is **gitignored** so your persona stays local.

IO walks **up from the session working directory** until it finds `soul.md` or `SOUL.md`. If none exists, it uses **`~/.io/SOUL.md`** (created on first `io setup`).

**Telegram / `io gateway run`:** the agent often runs with cwd **`$HOME`**, so add to `~/.io/config.yaml`:

```yaml
soul:
  workspace_root: "/absolute/path/to/this/repo"
```

You can adapt text from SillyTavern / character cards; keep sections that help the model stay on-mission (tone, boundaries, specialties).

```markdown
# Your name

You are …
```
