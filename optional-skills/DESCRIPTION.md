# Optional Skills

Official skills maintained by Most Wanted Research that are **not activated by default**.

These skills ship with the io repository but are not copied to
`~/.io/skills/` during setup. They are discoverable via the Skills Hub:

```bash
io skills browse               # browse all skills, official shown first
io skills browse --source official  # browse only official optional skills
io skills search <query>       # finds optional skills labeled "official"
io skills install <identifier> # copies to ~/.io/skills/ and activates
```

## Why optional?

Some skills are useful but not broadly needed by every user:

- **Niche integrations** Φ specific paid services, specialized tools
- **Experimental features** Φ promising but not yet proven
- **Heavyweight dependencies** Φ require significant setup (API keys, installs)

By keeping them optional, we keep the default skill set lean while still
providing curated, tested, official skills for users who want them.
