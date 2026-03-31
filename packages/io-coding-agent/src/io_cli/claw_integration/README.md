# Claw Code Integration

This directory contains the integration of **claw-code** (clean-room Claude Code rewrite) into IO.

## What Was Added

### 1. Reference Data (`reference_data/`)
- `claw_commands.json` - 76 Claude Code command definitions
- `claw_tools.json` - 44 Claude Code tool definitions

### 2. Core Module (`__init__.py`)
- `ClawRouter` - Routes prompts to matching commands/tools
- `ParityAudit` - Compares IO coverage vs Claude Code
- `ClawCommand` / `ClawTool` - Dataclasses for definitions

### 3. CLI Commands (`cli_commands.py`)
Integrated into `io claw` subcommand:
- `io claw stats` - Show statistics
- `io claw route <prompt>` - Route prompt to commands
- `io claw audit` - Run parity audit
- `io claw commands` - List all commands
- `io claw tools` - List all tools
- `io claw show-command <name>` - Show command details
- `io claw show-tool <name>` - Show tool details

### 4. Skill Documentation (`skills/claude/CLAUDE.md`)
Complete skill file documenting:
- What claw-code is
- How to use the integration
- Command/tool categories
- Implementation priorities

## Usage Examples

### Route a Prompt
```bash
$ io claw route "commit my changes"

Matches for: commit my changes
==================================================

1. [COMMAND] commit (score: 1)
   Source: commands/commit.ts
   Create git commits with AI-generated messages

2. [TOOL] GitCommitTool (score: 1)
   Source: tools/GitCommitTool.ts
   Create git commits

3. [COMMAND] commit-push-pr (score: 1)
   Source: commands/commit-push-pr.ts
   Full workflow: commit, push, and create PR
```

### Run Parity Audit
```bash
$ io claw audit

# IO vs Claude Code Parity Report

**Command Coverage:** 12/76 (15.8%)
**Tool Coverage:** 0/44

## Missing Commands (Top 20)
- `compact`
- `review`
- `plan`
- `skills`
- `memory`
...
```

### Programmatic Usage
```python
from io_cli.claw_integration import ClawRouter, ParityAudit

# Route a prompt
router = ClawRouter()
matches = router.route_prompt("deploy to production", limit=3)

# Audit coverage
audit = ParityAudit()
io_commands = ["commit", "diff", "status"]  # Your actual commands
report = audit.compare_with_io_commands(io_commands)
print(report.to_markdown())
```

## Architecture

The integration follows IO's existing patterns:

1. **Reference Data** - JSON snapshots (like skill definitions)
2. **Router** - Token-based matching (similar to model router)
3. **Audit** - Coverage comparison (like doctor checks)
4. **CLI** - Standard argparse subcommands

## Command Categories from Claude Code

### Git Operations
`branch`, `commit`, `commit-push-pr`, `diff`, `review`, `hooks`

### Configuration  
`config`, `theme`, `output-style`, `voice`, `permissions`

### IDE Integration
`chrome`, `desktop`, `ide`, `vim`

### Advanced
`compact`, `plan`, `ultraplan`, `skills`, `memory`, `mcp`, `plugin`

## Tool Categories

### File Operations
`BashTool`, `FileReadTool`, `FileEditTool`, `GlobTool`, `GrepTool`

### Integration
`GitHubTool`, `WebFetchTool`, `MCPManager`

### Analysis
`ProjectAnalyzer`, `SecurityScanner`, `LinterTool`, `ReviewTool`

## Future Enhancements

Priority implementations:
1. **CompactContext** - Smart context compression
2. **AgentTool** - Sub-agent delegation
3. **Review workflow** - Code review automation
4. **Skills marketplace** - Dynamic skill loading
5. **Memory persistence** - Cross-session memory

## Testing

```bash
# Test import
python -c "from io_cli.claw_integration import ClawRouter; print('OK')"

# Test CLI
io claw stats
io claw route "test my code"
io claw commands --limit 5
```
