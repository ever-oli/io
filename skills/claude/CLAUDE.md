---
name: claw
version: 1.0.0
description: Claude Code command reference and parity tracking
author: IO Team
metadata:
  io:
    tags: [claude, reference, parity, commands]
    category: integration
---

# Claw Code Integration

This skill provides access to the **claw-code** repository - a clean-room Python rewrite of Claude Code's agent harness. It includes 300+ command definitions and 50+ tool definitions from the original Claude Code system.

## What is Claw Code?

Claw Code (github.com/instructkr/claw-code) is a community-driven, clean-room rewrite of Claude Code's architecture:

- **300+ commands** - Git operations, IDE integration, configuration, plugins
- **50+ tools** - Bash, file operations, web fetch, git, GitHub, memory
- **Prompt routing** - Token-based matching to suggest commands
- **Parity tracking** - Compare IO's coverage vs Claude Code

## Usage

### Route a prompt to Claude Code commands

```python
from io_cli.claw_integration import ClawRouter

router = ClawRouter()
matches = router.route_prompt("commit my changes with a good message")

for match in matches:
    print(f"{match.kind}: {match.name} (score: {match.score})")
    print(f"  Source: {match.source_hint}")
    print(f"  Does: {match.responsibility}")
```

### Audit parity coverage

```python
from io_cli.claw_integration import ParityAudit

audit = ParityAudit()
report = audit.compare_with_io_commands(["commit", "diff", "status"])
print(report.to_markdown())
```

### CLI Commands

```bash
# Show claw stats
io claw stats

# Route a prompt to find matching commands
io claw route "deploy to production"

# Run parity audit comparing IO to Claude Code
io claw audit

# List all available Claude Code commands
io claw commands

# List all available Claude Code tools
io claw tools

# Show details for a specific command
io claw show-command commit

# Show details for a specific tool
io claw show-tool BashTool
```

## Command Categories

### Git Operations
- `branch` - Branch management
- `commit` - Create commits with AI messages
- `commit-push-pr` - Full workflow automation
- `diff` - Show changes
- `review` - Code review

### Configuration
- `config` - Manage settings
- `theme` - Change appearance
- `output-style` - Format preferences
- `voice` - Voice control

### IDE Integration
- `chrome` - Browser control via CDP
- `desktop` - Desktop environment
- `ide` - IDE integration
- `vim` - Vim integration

### Advanced
- `compact` - Compress conversation
- `plan` / `ultraplan` - Project planning
- `skills` - AI skill management
- `memory` - Persistent memory
- `mcp` - MCP server management
- `plugin` - Plugin management

## Tool Categories

### File Operations
- `BashTool` - Execute shell commands
- `FileReadTool` - Read files
- `FileEditTool` - Edit files
- `FileWriteTool` - Write files
- `GlobTool` - Find files by pattern
- `GrepTool` - Search file contents
- `LSTool` - List directories

### Integration
- `GitHubTool` - GitHub API
- `WebFetchTool` - Web content
- `WebSearchTool` - Web search
- `MCPManager` - MCP servers
- `ChromeTool` - Browser control

### Analysis
- `ProjectAnalyzer` - Code analysis
- `SecurityScanner` - Security checks
- `LinterTool` - Code linting
- `TypeChecker` - Type checking
- `TestRunner` - Run tests
- `ReviewTool` - Code review

### Context
- `ContextWindowTracker` - Monitor token usage
- `CostTracker` - Track API costs
- `HistoryTool` - Conversation history
- `MemoryTool` - Persistent memory
- `Summarizer` - Text summarization

## Integration Notes

This is a **reference implementation**, not a full runtime. The data is used to:

1. **Suggest commands** when users describe what they want
2. **Track coverage** of features IO implements vs Claude Code
3. **Guide development** toward high-value missing features

## Future Work

Priority commands to implement:
- `compact` - Compress context (high impact)
- `review` - Code review automation
- `plan` - Project planning with dependencies
- `skills` - Skill marketplace integration
- `memory` - Persistent user memory

Priority tools to implement:
- `CompactContext` - Smart context compression
- `AgentTool` - Sub-agent delegation
- `ComplexityCalculator` - Code complexity analysis
