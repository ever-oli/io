"""Trajectory compression for RL training data.

Compresses agent trajectories to fit within token budgets while
preserving training signal quality. Used for RL fine-tuning.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CompressionConfig:
    """Configuration for trajectory compression."""

    # Token limits
    target_max_tokens: int = 15250
    summary_target_tokens: int = 750

    # Protected turns (never compress these)
    protect_first_system: bool = True
    protect_first_human: bool = True
    protect_first_assistant: bool = True
    protect_first_tool: bool = True
    protect_last_n_turns: int = 4

    # Summarization
    summarization_model: str = "google/gemini-3-flash-preview"
    temperature: float = 0.3
    max_retries: int = 3

    # Output
    add_summary_notice: bool = True
    summary_notice_text: str = "\n\n[Previous turns summarized to preserve context]"


@dataclass
class TrajectoryMetrics:
    """Metrics for compression of a single trajectory."""

    original_tokens: int = 0
    compressed_tokens: int = 0
    tokens_saved: int = 0
    compression_ratio: float = 1.0

    original_turns: int = 0
    compressed_turns: int = 0
    turns_removed: int = 0

    was_compressed: bool = False
    still_over_limit: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_tokens": self.original_tokens,
            "compressed_tokens": self.compressed_tokens,
            "tokens_saved": self.tokens_saved,
            "compression_ratio": round(self.compression_ratio, 4),
            "original_turns": self.original_turns,
            "compressed_turns": self.compressed_turns,
            "turns_removed": self.turns_removed,
            "was_compressed": self.was_compressed,
            "still_over_limit": self.still_over_limit,
        }


class TrajectoryCompressor:
    """Compress agent trajectories for RL training."""

    def __init__(self, config: Optional[CompressionConfig] = None):
        self.config = config or CompressionConfig()
        self._token_estimates: Dict[str, int] = {}

    def count_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Simple approximation: ~4 chars per token
        return len(text) // 4

    def count_trajectory_tokens(self, trajectory: List[Dict[str, str]]) -> int:
        """Count total tokens in trajectory."""
        return sum(self.count_tokens(turn.get("content", "")) for turn in trajectory)

    def _find_protected_indices(self, trajectory: List[Dict[str, str]]) -> Tuple[set, int, int]:
        """Find which indices are protected from compression."""
        n = len(trajectory)
        protected = set()

        # Track first occurrences
        first = {"system": None, "human": None, "assistant": None, "tool": None}

        for i, turn in enumerate(trajectory):
            role = turn.get("role", "")
            if role in first and first[role] is None:
                first[role] = i

        # Protect first turns
        if self.config.protect_first_system and first["system"] is not None:
            protected.add(first["system"])
        if self.config.protect_first_human and first["human"] is not None:
            protected.add(first["human"])
        if self.config.protect_first_assistant and first["assistant"] is not None:
            protected.add(first["assistant"])
        if self.config.protect_first_tool and first["tool"] is not None:
            protected.add(first["tool"])

        # Protect last N turns
        for i in range(max(0, n - self.config.protect_last_n_turns), n):
            protected.add(i)

        # Determine compressible region
        head_protected = [i for i in protected if i < n // 2]
        tail_protected = [i for i in protected if i >= n // 2]

        compress_start = max(head_protected) + 1 if head_protected else 0
        compress_end = min(tail_protected) if tail_protected else n

        return protected, compress_start, compress_end

    def compress_trajectory(
        self, trajectory: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], TrajectoryMetrics]:
        """Compress a trajectory to fit within target token budget."""
        metrics = TrajectoryMetrics()
        metrics.original_turns = len(trajectory)
        metrics.original_tokens = self.count_trajectory_tokens(trajectory)

        # Check if compression needed
        if metrics.original_tokens <= self.config.target_max_tokens:
            metrics.compressed_tokens = metrics.original_tokens
            metrics.compressed_turns = len(trajectory)
            return trajectory, metrics

        # Find compressible region
        protected, compress_start, compress_end = self._find_protected_indices(trajectory)

        if compress_start >= compress_end:
            # Nothing to compress
            metrics.compressed_tokens = metrics.original_tokens
            metrics.compressed_turns = len(trajectory)
            metrics.still_over_limit = True
            return trajectory, metrics

        # Build compressed trajectory
        compressed = []

        # Add protected head
        for i in range(compress_start):
            compressed.append(dict(trajectory[i]))

        # Add summary placeholder for compressed region
        compressed.append(
            {
                "role": "system",
                "content": self.config.summary_notice_text,
            }
        )

        # Add protected tail
        for i in range(compress_end, len(trajectory)):
            compressed.append(dict(trajectory[i]))

        # Calculate metrics
        metrics.compressed_turns = len(compressed)
        metrics.compressed_tokens = self.count_trajectory_tokens(compressed)
        metrics.tokens_saved = metrics.original_tokens - metrics.compressed_tokens
        metrics.compression_ratio = metrics.compressed_tokens / max(metrics.original_tokens, 1)
        metrics.turns_removed = metrics.original_turns - metrics.compressed_turns
        metrics.was_compressed = True
        metrics.still_over_limit = metrics.compressed_tokens > self.config.target_max_tokens

        return compressed, metrics

    def compress_file(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
    ) -> List[TrajectoryMetrics]:
        """Compress all trajectories in a JSONL file."""
        if output_path is None:
            output_path = input_path.with_suffix(".compressed.jsonl")

        all_metrics = []
        output_lines = []

        with open(input_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    output_lines.append(line)
                    continue

                # Check if entry has trajectory
                if "trajectory" in entry:
                    compressed, metrics = self.compress_trajectory(entry["trajectory"])
                    entry["trajectory"] = compressed
                    entry["compression"] = metrics.to_dict()
                    all_metrics.append(metrics)
                elif "conversations" in entry:
                    compressed, metrics = self.compress_trajectory(entry["conversations"])
                    entry["conversations"] = compressed
                    entry["compression"] = metrics.to_dict()
                    all_metrics.append(metrics)

                output_lines.append(json.dumps(entry))

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            for line in output_lines:
                f.write(line + "\n")

        return all_metrics

    def get_summary(self, metrics_list: List[TrajectoryMetrics]) -> Dict[str, Any]:
        """Generate summary statistics for multiple compressions."""
        if not metrics_list:
            return {"total": 0}

        total_original = sum(m.original_tokens for m in metrics_list)
        total_compressed = sum(m.compressed_tokens for m in metrics_list)
        total_saved = sum(m.tokens_saved for m in metrics_list)

        compressed_count = sum(1 for m in metrics_list if m.was_compressed)
        over_limit = sum(1 for m in metrics_list if m.still_over_limit)

        return {
            "total": len(metrics_list),
            "compressed": compressed_count,
            "over_limit": over_limit,
            "total_original_tokens": total_original,
            "total_compressed_tokens": total_compressed,
            "total_tokens_saved": total_saved,
            "overall_ratio": round(total_compressed / max(total_original, 1), 4),
        }
