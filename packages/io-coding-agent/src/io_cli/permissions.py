"""Enhanced permission system with granular tool controls.

Fuses IO's existing approval queue with Claude Code-style permission contexts:
- Per-tool allow/deny lists
- Pattern-based argument blocking
- Session-level permission overrides
- Runtime policy changes
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .approval_queue import ApprovalQueueStore


@dataclass
class ToolPermissionRule:
    """A permission rule for a tool or tool pattern."""

    tool_pattern: str  # Exact name or glob pattern: "BashTool", "*Tool", "bash_*"
    action: str  # "allow", "deny", "prompt"
    argument_patterns: dict[str, str] = field(default_factory=dict)
    # e.g., {"command": "rm -rf *"} -> deny rm -rf
    reason: str = ""

    def matches_tool(self, tool_name: str) -> bool:
        """Check if this rule applies to a tool name."""
        return fnmatch.fnmatch(tool_name, self.tool_pattern)

    def matches_arguments(self, arguments: dict[str, Any]) -> bool:
        """Check if arguments match any blocking patterns."""
        for key, pattern in self.argument_patterns.items():
            value = str(arguments.get(key, ""))
            if fnmatch.fnmatch(value, pattern):
                return True
        return False


@dataclass
class PermissionContext:
    """Permission context for a session or workspace.

    Fuses IO's approval queue with Claude Code's granular controls.
    """

    home: Path
    rules: list[ToolPermissionRule] = field(default_factory=list)
    default_action: str = "prompt"  # "allow", "deny", "prompt"

    def __post_init__(self):
        self._approval_store = ApprovalQueueStore(home=self.home)
        self._load_persistent_rules()

    def _load_persistent_rules(self) -> None:
        """Load rules from ~/.io/permissions/rules.json"""
        rules_path = self.home / "permissions" / "rules.json"
        if rules_path.exists():
            try:
                data = json.loads(rules_path.read_text())
                for rule_data in data.get("rules", []):
                    self.rules.append(
                        ToolPermissionRule(
                            tool_pattern=rule_data["tool_pattern"],
                            action=rule_data["action"],
                            argument_patterns=rule_data.get("argument_patterns", {}),
                            reason=rule_data.get("reason", ""),
                        )
                    )
                self.default_action = data.get("default_action", self.default_action)
            except (json.JSONDecodeError, KeyError):
                pass

    def check_permission(
        self, tool_name: str, arguments: dict[str, Any], tool_reason: str | None = None
    ) -> tuple[str, str | None]:
        """Check if tool execution is allowed.

        Returns:
            (action, reason): action is "allow", "deny", or "prompt"
                              reason is None if allowed, or explanation if denied/prompt
        """
        # Check explicit rules (first match wins)
        for rule in self.rules:
            if rule.matches_tool(tool_name):
                if rule.matches_arguments(arguments):
                    return rule.action, rule.reason or f"Rule matched: {rule.tool_pattern}"
                # Tool matches but arguments don't - check if there's a blanket rule
                if not rule.argument_patterns:
                    return rule.action, rule.reason

        # Check approval queue policies
        policy = self._approval_store.policy_decision(tool_name, arguments)
        if policy == "allow_always":
            return "allow", None
        if policy == "deny_always":
            return "deny", "Permanently denied by policy"

        # Check tool's own approval reason
        if tool_reason:
            return self.default_action, tool_reason

        return self.default_action, None

    def add_rule(self, rule: ToolPermissionRule, persist: bool = False) -> None:
        """Add a permission rule."""
        self.rules.append(rule)
        if persist:
            self._persist_rules()

    def remove_rule(self, tool_pattern: str) -> bool:
        """Remove all rules matching a pattern."""
        original_len = len(self.rules)
        self.rules = [r for r in self.rules if r.tool_pattern != tool_pattern]
        if len(self.rules) != original_len:
            self._persist_rules()
            return True
        return False

    def _persist_rules(self) -> None:
        """Save rules to disk."""
        rules_path = self.home / "permissions" / "rules.json"
        rules_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "default_action": self.default_action,
            "rules": [
                {
                    "tool_pattern": r.tool_pattern,
                    "action": r.action,
                    "argument_patterns": r.argument_patterns,
                    "reason": r.reason,
                }
                for r in self.rules
            ],
        }
        rules_path.write_text(json.dumps(data, indent=2))

    def get_rules_summary(self) -> list[dict[str, Any]]:
        """Get summary of all rules."""
        return [
            {
                "tool_pattern": r.tool_pattern,
                "action": r.action,
                "reason": r.reason or "No reason provided",
            }
            for r in self.rules
        ]


# Predefined permission profiles
SAFE_PROFILE = [
    ToolPermissionRule("BashTool", "deny", {"command": "rm -rf *"}, "Dangerous deletion"),
    ToolPermissionRule("BashTool", "deny", {"command": "*:.*"}, "Hidden file operations"),
    ToolPermissionRule(
        "FileWriteTool", "prompt", {"file_path": "*.*"}, "Writing to existing files"
    ),
]

PARANOID_PROFILE = [
    ToolPermissionRule("BashTool", "prompt"),
    ToolPermissionRule("FileWriteTool", "prompt"),
    ToolPermissionRule("FileEditTool", "prompt"),
]

PERMISSIVE_PROFILE = [
    ToolPermissionRule("*", "allow"),
]
