# Claudetenks Architecture Fusion

## The Confusion

You wanted to **fuse** claw-code's agent harness patterns into IO's core, not add CLI commands to browse claw-code data. My bad!

## What We Have Now

### IO Gotenks (Current)
```
io-agent-core/src/io_agent/agent.py
├── Agent.run_stream()          # Event-driven loop
├── ContextCompressor           # Summarizes when long
├── ToolRegistry                # Tool schemas & execution
├── Events: AgentStart/TurnStart/ToolCall/etc
└── max_iterations: int = 8     # Hard turn limit
```

### Claw-Code (What to Fuse)
```
src/query_engine.py
├── QueryEnginePort             # Turn manager with session state
├── submit_message()            # Turn-based with budget tracking
├── stream_submit_message()     # Streaming turns
├── compact_messages_if_needed() # Smart compaction
└── Config: max_turns, max_budget_tokens, compact_after_turns

src/runtime.py  
├── PortRuntime.route_prompt()  # Routes prompt to commands/tools
├── bootstrap_session()         # Full context setup
├── run_turn_loop()             # Multi-turn with persistence
└── Execution registry integration
```

## What Claudetenks Should Be

A fusion that adds **Claude Code's strengths** to IO:

1. **Smart Routing** - Route prompts to specific tools/commands before LLM call
2. **Turn Budget Management** - Token budget tracking per session
3. **Session Persistence** - Save/resume full conversation state
4. **Command Awareness** - Know when user wants a specific command vs conversation

## The Real Integration

Instead of CLI commands, we should modify IO's **Agent class**:

### Option 1: Extend Agent with ClawRouter

```python
# packages/io-agent-core/src/io_agent/claudetenks_agent.py

from dataclasses import dataclass, field
from .agent import Agent
from io_cli.claw_integration import ClawRouter

@dataclass
class ClaudetenksAgent(Agent):
    """IO Agent fused with Claude Code patterns."""
    
    claw_router: ClawRouter = field(default_factory=ClawRouter)
    max_budget_tokens: int = 2000  # From claw-code
    enable_routing: bool = True     # Route prompts to commands
    
    async def run_stream(self, prompt, ...):
        # NEW: Route prompt before LLM call
        if self.enable_routing:
            matches = self.claw_router.route_prompt(prompt)
            # If high-confidence command match, execute directly
            # Otherwise proceed to LLM
        
        # EXISTING: Run normal IO agent loop
        async for event in super().run_stream(prompt, ...):
            yield event
```

### Option 2: Add Turn Management to Sessions

```python
# packages/io-coding-agent/src/io_cli/session.py modifications

@dataclass
class ClaudetenksSession(SessionManager):
    """Session with Claude Code-style turn management."""
    
    max_turns: int = 8
    max_budget_tokens: int = 2000
    conversation_turns: list[TurnResult] = field(default_factory=list)
    
    def add_turn(self, prompt: str, output: str, usage: Usage):
        """Track turn with budget checking."""
        turn = TurnResult(
            prompt=prompt,
            output=output,
            usage=usage,
        )
        self.conversation_turns.append(turn)
        
        # Check budget
        total = sum(t.usage.total_tokens for t in self.conversation_turns)
        if total > self.max_budget_tokens:
            self.compact_context()
    
    def compact_context(self):
        """Claw-code style compaction."""
        # Keep last N turns, summarize older ones
        pass
```

### Option 3: Tool-Level Routing (Most Surgical)

Add a tool that does routing:

```python
# packages/io-coding-agent/src/io_cli/tools/claw_router_tool.py

class ClawRouterTool(Tool):
    """Tool that routes prompts to Claude Code patterns."""
    
    name = "claw_route"
    description = "Route user intent to specific workflows"
    
    async def execute(self, context, arguments):
        prompt = arguments["prompt"]
        router = ClawRouter()
        matches = router.route_prompt(prompt)
        
        # If matches found, suggest specific approach
        if matches and matches[0].score >= 2:
            return ToolResult(
                output=f"Detected intent: {matches[0].name}. "
                       f"Consider using: {matches[0].responsibility}"
            )
```

## What Should We Actually Do?

**Question for you:** Which fusion approach do you want?

### A) Smart Pre-Routing (Recommended)
Before sending to LLM, check if user wants a specific command pattern:
```
User: "commit these changes"
→ Route detects "commit" command
→ Either execute directly OR add context to help LLM
```

### B) Turn Budget Management
Add claw-code's token budget and compaction to IO sessions:
```
Session tracks: 1500/2000 tokens used
→ Auto-compact when threshold hit
→ Persist full turn history
```

### C) Command Registry Integration
Map IO's existing commands to Claude Code patterns:
```
IO's "/commit" → Claude's "commit" command metadata
→ Unified help/documentation
→ Cross-reference parity
```

### D) All of the Above (Full Claudetenks)
Create a new agent class that fuses everything.

## Removing the CLI Stuff

The CLI commands I added (`io claw stats`, etc.) are just for browsing claw-code data - useful for development but not the core fusion. We can:
1. Keep them for debugging/reference
2. Remove them entirely  
3. Convert them into the actual fusion

**What do you want to build?** The true Claudetenks fusion at the agent level?
