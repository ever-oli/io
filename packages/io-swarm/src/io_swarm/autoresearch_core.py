"""Auto-research loop - Autonomous experiment optimization.

Core implementation of experiment loop with keep/revert decisions.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .autoresearch_types import ExperimentResult


class AutoResearchCore:
    """Core auto-research functionality."""

    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.results: List[ExperimentResult] = []
        self.session_file = session_dir / "autoresearch.jsonl"
        self._load()

    def _load(self) -> None:
        """Load existing results."""
        if not self.session_file.exists():
            return
        with open(self.session_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    self.results.append(ExperimentResult(**data))
                except Exception:
                    pass

    def save_result(self, result: ExperimentResult) -> None:
        """Save result to JSONL."""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        with open(self.session_file, "a") as f:
            f.write(json.dumps(result.to_dict()) + "\n")
        self.results.append(result)

    def should_keep(self, metric_value: float, direction: str = "lower") -> bool:
        """Determine if result should be kept based on previous results."""
        if not self.results:
            return True

        # Get best kept result
        kept_results = [r for r in self.results if r.status == "kept"]
        if not kept_results:
            return True

        best = kept_results[0].metric_value
        for r in kept_results[1:]:
            if direction == "lower":
                if r.metric_value < best:
                    best = r.metric_value
            else:
                if r.metric_value > best:
                    best = r.metric_value

        if direction == "lower":
            return metric_value <= best
        return metric_value >= best

    def git_commit(self, message: str) -> Optional[str]:
        """Commit changes and return hash."""
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=self.session_dir,
                capture_output=True,
                check=False,
            )
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.session_dir,
                capture_output=True,
                check=False,
            )
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.session_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception:
            return None

    def git_revert(self, commit_hash: str) -> bool:
        """Revert to specific commit."""
        try:
            subprocess.run(
                ["git", "reset", "--hard", commit_hash],
                cwd=self.session_dir,
                capture_output=True,
                check=True,
            )
            return True
        except Exception:
            return False

    def get_summary(self) -> Dict[str, Any]:
        """Get experiment summary."""
        total = len(self.results)
        kept = sum(1 for r in self.results if r.status == "kept")
        reverted = sum(1 for r in self.results if r.status == "reverted")

        return {
            "total_experiments": total,
            "kept": kept,
            "reverted": reverted,
            "success_rate": kept / total if total > 0 else 0,
        }
