"""Advanced Permission System - Sophisticated rule-based permissions with AI classification.

Features:
- Rule-based permission system with patterns
- AI-powered permission classification
- Auto-mode with transcript analysis
- Permission explanations
- Filesystem permission rules
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PermissionAction(Enum):
    """Possible permission actions."""

    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


class PermissionMode(Enum):
    """Permission modes."""

    AUTO = "auto"  # AI classifies and auto-approves safe operations
    ACCEPT_EDITS = "accept_edits"  # Auto-accept file edits, prompt others
    ACCEPT_ALL = "accept_all"  # Auto-accept all (dangerous)
    BYPASS = "bypass"  # Bypass permissions entirely
    PROMPT = "prompt"  # Always prompt


@dataclass
class PermissionRule:
    """A single permission rule."""

    tool_pattern: str
    action: PermissionAction
    path_pattern: str | None = None
    description: str = ""
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_pattern": self.tool_pattern,
            "action": self.action.value,
            "path_pattern": self.path_pattern,
            "description": self.description,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionRule:
        return cls(
            tool_pattern=data["tool_pattern"],
            action=PermissionAction(data["action"]),
            path_pattern=data.get("path_pattern"),
            description=data.get("description", ""),
            priority=data.get("priority", 0),
        )

    def matches(self, tool_name: str, path: str | None = None) -> bool:
        """Check if this rule matches a tool and path."""
        # Match tool pattern (supports wildcards)
        import fnmatch

        if not fnmatch.fnmatch(tool_name.lower(), self.tool_pattern.lower()):
            return False

        # Match path pattern if specified
        if self.path_pattern and path:
            if not fnmatch.fnmatch(path, self.path_pattern):
                return False

        return True


@dataclass
class BashClassification:
    """Classification of a bash command."""

    command: str
    risk_level: str  # "safe", "low", "medium", "high", "critical"
    category: str  # "read", "write", "network", "system", "destructive"
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "risk_level": self.risk_level,
            "category": self.category,
            "explanation": self.explanation,
        }


class AIPermissionClassifier:
    """AI-powered permission classification (simplified version)."""

    # Risk patterns for bash commands
    RISK_PATTERNS = {
        "critical": [
            (r"\brm\s+-rf\s+/\b", "Deleting system directories"),
            (r"\bdd\s+if=.*of=/dev/", "Direct disk writes"),
            (r"\bmkfs\.", "Formatting filesystems"),
            (r">\s*/etc/", "Modifying system configuration"),
        ],
        "high": [
            (r"\brm\s+-rf\b", "Recursive deletion"),
            (r"\bcurl\b.*\|\s*\bsh\b", "Piping curl to shell"),
            (r"\bwget\b.*\|\s*\bsh\b", "Piping wget to shell"),
            (r"\bsudo\b", "Escalated privileges"),
            (r"\bsu\s+-", "Switching users"),
        ],
        "medium": [
            (r"\brm\b", "File deletion"),
            (r"\bmv\b", "Moving files"),
            (r"\bcp\b.*-r", "Recursive copy"),
            (r"\bchmod\s+777", "Overly permissive permissions"),
            (r"\bgit\s+push\b", "Pushing to remote"),
            (r"\bgit\s+reset\b.*--hard", "Hard reset"),
        ],
        "low": [
            (r"\bcurl\b", "Network requests"),
            (r"\bwget\b", "Downloading files"),
            (r"\bnpm\s+install\b", "Installing packages"),
            (r"\bpip\s+install\b", "Installing packages"),
            (r"\bdocker\b", "Docker operations"),
        ],
    }

    # Category patterns
    CATEGORY_PATTERNS = {
        "destructive": [r"\brm\b", r"\bdd\b", r"\bmkfs\b", r"\bdestroy\b"],
        "write": [r"\becho\b.*>", r"\btouch\b", r"\bmkdir\b", r"\bwrite\b"],
        "network": [r"\bcurl\b", r"\bwget\b", r"\bssh\b", r"\bscp\b", r"\brsync\b"],
        "system": [r"\bsudo\b", r"\bsystemctl\b", r"\bservice\b", r"\breboot\b"],
        "read": [r"\bcat\b", r"\bls\b", r"\bgrep\b", r"\bfind\b", r"\bread\b"],
    }

    def classify_bash(self, command: str) -> BashClassification:
        """Classify a bash command for risk."""
        command_lower = command.lower()

        # Check risk levels
        for risk, patterns in self.RISK_PATTERNS.items():
            for pattern, explanation in patterns:
                if re.search(pattern, command_lower):
                    # Determine category
                    category = self._classify_category(command_lower)
                    return BashClassification(
                        command=command,
                        risk_level=risk,
                        category=category,
                        explanation=explanation,
                    )

        # Default: safe read operation
        return BashClassification(
            command=command,
            risk_level="safe",
            category="read",
            explanation="Standard read operation",
        )

    def _classify_category(self, command: str) -> str:
        """Classify command category."""
        for category, patterns in self.CATEGORY_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, command):
                    return category
        return "other"

    def should_auto_approve(self, classification: BashClassification, mode: PermissionMode) -> bool:
        """Determine if a command should be auto-approved based on classification and mode."""
        if mode == PermissionMode.BYPASS:
            return True

        if mode == PermissionMode.PROMPT:
            return False

        if mode == PermissionMode.ACCEPT_ALL:
            return True

        if mode == PermissionMode.ACCEPT_EDITS:
            # Auto-approve read operations and safe writes
            if classification.category == "read":
                return True
            if classification.risk_level in ["safe", "low"]:
                return True
            return False

        if mode == PermissionMode.AUTO:
            # AI mode - only auto-approve safe operations
            if classification.risk_level == "safe":
                return True
            if classification.risk_level == "low" and classification.category == "read":
                return True
            return False

        return False


class AdvancedPermissionManager:
    """Advanced permission management with rules and AI classification."""

    def __init__(self, home: Path):
        self.home = home
        self.rules_dir = home / "permissions"
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = home / "permission_config.json"

        self._rules: list[PermissionRule] = []
        self._mode: PermissionMode = PermissionMode.PROMPT
        self._classifier = AIPermissionClassifier()

        self._load_config()
        self._load_rules()

    def _load_config(self) -> None:
        """Load permission configuration."""
        if self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text())
                self._mode = PermissionMode(data.get("mode", "prompt"))
            except (json.JSONDecodeError, ValueError):
                pass

    def _save_config(self) -> None:
        """Save permission configuration."""
        self.config_file.write_text(
            json.dumps(
                {
                    "mode": self._mode.value,
                },
                indent=2,
            )
        )

    def _load_rules(self) -> None:
        """Load permission rules."""
        rules_file = self.rules_dir / "rules.json"
        if rules_file.exists():
            try:
                data = json.loads(rules_file.read_text())
                self._rules = [PermissionRule.from_dict(r) for r in data.get("rules", [])]
            except (json.JSONDecodeError, KeyError):
                pass

    def _save_rules(self) -> None:
        """Save permission rules."""
        rules_file = self.rules_dir / "rules.json"
        rules_file.write_text(
            json.dumps(
                {
                    "rules": [r.to_dict() for r in self._rules],
                },
                indent=2,
            )
        )

    @property
    def mode(self) -> PermissionMode:
        """Get current permission mode."""
        return self._mode

    @mode.setter
    def mode(self, value: PermissionMode) -> None:
        """Set permission mode."""
        self._mode = value
        self._save_config()

    def add_rule(self, rule: PermissionRule) -> None:
        """Add a permission rule."""
        self._rules.append(rule)
        # Sort by priority (higher first)
        self._rules.sort(key=lambda r: r.priority, reverse=True)
        self._save_rules()

    def remove_rule(self, index: int) -> bool:
        """Remove a rule by index."""
        if 0 <= index < len(self._rules):
            self._rules.pop(index)
            self._save_rules()
            return True
        return False

    def list_rules(self) -> list[PermissionRule]:
        """List all rules."""
        return self._rules.copy()

    def check_permission(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> tuple[PermissionAction, str]:
        """Check permission for a tool operation.

        Returns:
            Tuple of (action, explanation)
        """
        arguments = arguments or {}

        # Get path if applicable
        path = arguments.get("path") or arguments.get("file_path") or arguments.get("command")
        if path:
            path = str(path)

        # Check rules first
        for rule in self._rules:
            if rule.matches(tool_name, path):
                return rule.action, f"Matched rule: {rule.description or rule.tool_pattern}"

        # Special handling for bash commands
        if tool_name.lower() in ["bash", "terminal", "shell"] and path:
            classification = self._classifier.classify_bash(path)

            if self._classifier.should_auto_approve(classification, self._mode):
                return (
                    PermissionAction.ALLOW,
                    f"Auto-approved ({classification.risk_level} risk): {classification.explanation}",
                )
            else:
                return (
                    PermissionAction.PROMPT,
                    f"Requires approval ({classification.risk_level} risk): {classification.explanation}",
                )

        # Default based on mode
        if self._mode == PermissionMode.BYPASS:
            return PermissionAction.ALLOW, "Bypass mode - all operations allowed"

        if self._mode == PermissionMode.ACCEPT_ALL:
            return PermissionAction.ALLOW, "Accept all mode"

        return PermissionAction.PROMPT, "No matching rule - approval required"

    def get_explanation(self, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
        """Get detailed explanation of permission decision."""
        action, reason = self.check_permission(tool_name, arguments)

        lines = [
            f"Permission Check: {tool_name}",
            f"Mode: {self._mode.value}",
            f"Decision: {action.value.upper()}",
            f"Reason: {reason}",
        ]

        if tool_name.lower() in ["bash", "terminal", "shell"]:
            cmd = str(arguments.get("command", ""))
            classification = self._classifier.classify_bash(cmd)
            lines.extend(
                [
                    "",
                    f"Command Analysis:",
                    f"  Risk Level: {classification.risk_level}",
                    f"  Category: {classification.category}",
                    f"  Explanation: {classification.explanation}",
                ]
            )

        return "\n".join(lines)
