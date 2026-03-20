---
sidebar_position: 3
title: "Updating & Uninstalling"
description: "How to update IO to the latest version or uninstall it"
---

# Updating & Uninstalling

## Updating

Update to the latest version with a single command:

```bash
io update
```

This pulls the latest code, updates dependencies, and prompts you to configure any new options that were added since your last update.

:::tip
`io update` automatically detects new configuration options and prompts you to add them. If you skipped that prompt, you can manually run `io config check` to see missing options, then `io config migrate` to interactively add them.
:::

### Updating from Messaging Platforms

You can also update directly from Telegram, Discord, Slack, or WhatsApp by sending:

```
/update
```

This pulls the latest code, updates dependencies, and restarts the gateway.

### Manual Update

If you installed manually (not via the quick installer):

```bash
cd /path/to/io
export VIRTUAL_ENV="$(pwd)/venv"

# Pull latest code and submodules
git pull origin main
git submodule update --init --recursive

# Reinstall (picks up new dependencies)
uv pip install -e ".[all]"
uv pip install -e "./mini-swe-agent"
uv pip install -e "./tinker-atropos"

# Check for new config options
io config check
io config migrate   # Interactively add any missing options
```

---

## Uninstalling

```bash
io uninstall
```

The uninstaller gives you the option to keep your configuration files (`~/.io/`) for a future reinstall.

### Manual Uninstall

```bash
rm -f ~/.local/bin/io
rm -rf /path/to/io
rm -rf ~/.io            # Optional Φ keep if you plan to reinstall
```

:::info
If you installed the gateway as a system service, stop and disable it first:
```bash
io gateway stop
# Linux: systemctl --user disable io-gateway
# macOS: launchctl remove ai.io.gateway
```
:::
