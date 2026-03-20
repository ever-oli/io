# IO ACP Setup

IO supports the Agent Client Protocol so editors can use `io` as a coding agent backend over stdio.

## Install

```bash
uv sync
```

That installs the ACP dependency declared by `io-coding-agent` and exposes both:

```bash
io acp
io-acp
```

## Registry

Editor ACP clients can point at:

```text
/Users/ever/Documents/GitHub/io/acp_registry
```

The registry entry runs:

```bash
io acp
```

## Runtime Notes

- ACP uses the same `~/.io` config, auth, skills, and session index as the CLI.
- ACP sessions persist into `~/.io/state.db` with source `acp`.
- Editor sessions keep their working directory bound to the ACP session, so file and terminal tools run relative to the editor workspace.
