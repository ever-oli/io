---
sidebar_position: 9
title: "Git Worktrees"
description: "Run multiple IO agents safely on the same repository using git worktrees and isolated checkouts"
---

# Git Worktrees

IO is often used on large, longΦlived repositories. When you want to:

- Run **multiple agents in parallel** on the same project, or
- Keep experimental refactors isolated from your main branch,

Git **worktrees** are the safest way to give each agent its own checkout without duplicating the entire repository.

This page shows how to combine worktrees with IO so each session has a clean, isolated working directory.

## Why Use Worktrees with IO?

IO treats the **current working directory** as the project root:

- CLI: the directory where you run `io` or `io chat`
- Messaging gateways: the directory set by `MESSAGING_CWD`

If you run multiple agents in the **same checkout**, their changes can interfere with each other:

- One agent may delete or rewrite files the other is using.
- It becomes harder to understand which changes belong to which experiment.

With worktrees, each agent gets:

- Its **own branch and working directory**
- Its **own Checkpoint Manager history** for `/rollback`

See also: [Checkpoints and /rollback](./checkpoints-and-rollback.md).

## Quick Start: Creating a Worktree

From your main repository (containing `.git/`), create a new worktree for a feature branch:

```bash
# From the main repo root
cd /path/to/your/repo

# Create a new branch and worktree in ../repo-feature
git worktree add ../repo-feature feature/io-experiment
```

This creates:

- A new directory: `../repo-feature`
- A new branch: `feature/io-experiment` checked out in that directory

Now you can `cd` into the new worktree and run IO there:

```bash
cd ../repo-feature

# Start IO in the worktree
io
```

IO will:

- See `../repo-feature` as the project root.
- Use that directory for context files, code edits, and tools.
- Use a **separate checkpoint history** for `/rollback` scoped to this worktree.

## Running Multiple Agents in Parallel

You can create multiple worktrees, each with its own branch:

```bash
cd /path/to/your/repo

git worktree add ../repo-experiment-a feature/io-a
git worktree add ../repo-experiment-b feature/io-b
```

In separate terminals:

```bash
# Terminal 1
cd ../repo-experiment-a
io

# Terminal 2
cd ../repo-experiment-b
io
```

Each IO process:

- Works on its own branch (`feature/io-a` vs `feature/io-b`).
- Writes checkpoints under a different shadow repo hash (derived from the worktree path).
- Can use `/rollback` independently without affecting the other.

This is especially useful when:

- Running batch refactors.
- Trying different approaches to the same task.
- Pairing CLI + gateway sessions against the same upstream repo.

## Cleaning Up Worktrees Safely

When you are done with an experiment:

1. Decide whether to keep or discard the work.
2. If you want to keep it:
   - Merge the branch into your main branch as usual.
3. Remove the worktree:

```bash
cd /path/to/your/repo

# Remove the worktree directory and its reference
git worktree remove ../repo-feature
```

Notes:

- `git worktree remove` will refuse to remove a worktree with uncommitted changes unless you force it.
- Removing a worktree does **not** automatically delete the branch; you can delete or keep the branch using normal `git branch` commands.
- IO checkpoint data under `~/.io/checkpoints/` is not automatically pruned when you remove a worktree, but it is usually very small.

## Best Practices

- **One worktree per IO experiment**
  - Create a dedicated branch/worktree for each substantial change.
  - This keeps diffs focused and PRs small and reviewable.
- **Name branches after the experiment**
  - e.g. `feature/io-checkpoints-docs`, `feature/io-refactor-tests`.
- **Commit frequently**
  - Use git commits for highΦlevel milestones.
  - Use [checkpoints and /rollback](./checkpoints-and-rollback.md) as a safety net for toolΦdriven edits in between.
- **Avoid running IO from the bare repo root when using worktrees**
  - Prefer the worktree directories instead, so each agent has a clear scope.

## Using `io -w` (Automatic Worktree Mode)

IO has a builtΦin `-w` flag that **automatically creates a disposable git worktree** with its own branch. You don't need to set up worktrees manually Φ just `cd` into your repo and run:

```bash
cd /path/to/your/repo
io -w
```

IO will:

- Create a temporary worktree under `.worktrees/` inside your repo.
- Check out an isolated branch (e.g. `io/session-<hash>`).
- Run the full CLI session inside that worktree.

This is the easiest way to get worktree isolation. You can also combine it with a single query:

```bash
io -w -q "Fix issue #123"
```

For parallel agents, open multiple terminals and run `io -w` in each Φ every invocation gets its own worktree and branch automatically.

## Putting It All Together

- Use **git worktrees** to give each IO session its own clean checkout.
- Use **branches** to capture the highΦlevel history of your experiments.
- Use **checkpoints + `/rollback`** to recover from mistakes inside each worktree.

This combination gives you:

- Strong guarantees that different agents and experiments do not step on each other.
- Fast iteration cycles with easy recovery from bad edits.
- Clean, reviewable pull requests targeted at v0.2.0Φs new capabilities.

