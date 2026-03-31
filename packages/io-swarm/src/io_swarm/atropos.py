"""Atropos integration - Training environment connector.

Atropos is a NousResearch training framework for RL fine-tuning.
This module provides integration between IO and Atropos.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class AtroposConfig:
    """Configuration for Atropos training run."""

    model_name: str = "gpt-4"
    learning_rate: float = 1e-5
    batch_size: int = 4
    max_steps: int = 1000
    warmup_steps: int = 100
    logging_steps: int = 10
    save_steps: int = 100
    output_dir: Path = field(default_factory=lambda: Path("./atropos_output"))
    trajectory_dir: Optional[Path] = None

    # Reward model config
    reward_model_path: Optional[str] = None
    reward_model_weight: float = 1.0

    # PPO specific
    ppo_epochs: int = 4
    ppo_clip_ratio: float = 0.2
    ppo_value_clip: float = 0.2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "max_steps": self.max_steps,
            "warmup_steps": self.warmup_steps,
            "logging_steps": self.logging_steps,
            "save_steps": self.save_steps,
            "output_dir": str(self.output_dir),
            "trajectory_dir": str(self.trajectory_dir) if self.trajectory_dir else None,
            "reward_model": {
                "path": self.reward_model_path,
                "weight": self.reward_model_weight,
            },
            "ppo": {
                "epochs": self.ppo_epochs,
                "clip_ratio": self.ppo_clip_ratio,
                "value_clip": self.ppo_value_clip,
            },
        }


class RewardModel(Protocol):
    """Protocol for reward models."""

    def compute_reward(self, trajectory: List[Dict[str, str]]) -> float:
        """Compute reward for a trajectory."""
        ...


@dataclass
class TrainingTrajectory:
    """A training trajectory with reward."""

    trajectory_id: str
    messages: List[Dict[str, str]]
    reward: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "messages": self.messages,
            "reward": self.reward,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class AtroposTrainer:
    """Main interface for Atropos training integration.

    Connects IO's trajectory compression with Atropos training loop.
    """

    def __init__(
        self,
        config: AtroposConfig,
        reward_model: Optional[RewardModel] = None,
    ):
        self.config = config
        self.reward_model = reward_model
        self.trajectories: List[TrainingTrajectory] = []
        self.current_step = 0

        # Ensure output dir exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[Atropos] Initialized trainer for {config.model_name}")

    def load_trajectories(self, trajectory_file: Path) -> int:
        """Load trajectories from compressed JSONL file.

        Args:
            trajectory_file: Path to trajectory JSONL

        Returns:
            Number of trajectories loaded
        """
        count = 0
        with open(trajectory_file) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    if "conversations" in data or "trajectory" in data:
                        messages = data.get("conversations") or data.get("trajectory", [])

                        # Compute reward if model available
                        reward = 0.0
                        if self.reward_model:
                            reward = self.reward_model.compute_reward(messages)

                        traj = TrainingTrajectory(
                            trajectory_id=f"traj_{count:06d}",
                            messages=messages,
                            reward=reward,
                            metadata=data.get("metadata", {}),
                        )
                        self.trajectories.append(traj)
                        count += 1

                except json.JSONDecodeError:
                    continue

        logger.info(f"[Atropos] Loaded {count} trajectories")
        return count

    def add_trajectory(
        self,
        messages: List[Dict[str, str]],
        reward: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrainingTrajectory:
        """Add a single trajectory to training set.

        Args:
            messages: List of message dicts with 'role' and 'content'
            reward: Optional reward value (computed if not provided)
            metadata: Optional metadata

        Returns:
            TrainingTrajectory object
        """
        if reward is None and self.reward_model:
            reward = self.reward_model.compute_reward(messages)

        traj = TrainingTrajectory(
            trajectory_id=f"traj_{len(self.trajectories):06d}",
            messages=messages,
            reward=reward or 0.0,
            metadata=metadata or {},
        )
        self.trajectories.append(traj)
        return traj

    def save_trajectories(self, output_file: Optional[Path] = None) -> Path:
        """Save all trajectories to JSONL for Atropos training.

        Args:
            output_file: Output path (default: output_dir/trajectories.jsonl)

        Returns:
            Path to saved file
        """
        if output_file is None:
            output_file = self.config.output_dir / "trajectories.jsonl"

        with open(output_file, "w") as f:
            for traj in self.trajectories:
                f.write(json.dumps(traj.to_dict()) + "\n")

        logger.info(f"[Atropos] Saved {len(self.trajectories)} trajectories to {output_file}")
        return output_file

    def export_atropos_config(self) -> Path:
        """Export Atropos-compatible training config.

        Returns:
            Path to config file
        """
        config_file = self.config.output_dir / "atropos_config.json"

        with open(config_file, "w") as f:
            json.dump(self.config.to_dict(), f, indent=2)

        logger.info(f"[Atropos] Exported config to {config_file}")
        return config_file

    def get_reward_stats(self) -> Dict[str, float]:
        """Get statistics on trajectory rewards."""
        if not self.trajectories:
            return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}

        rewards = [t.reward for t in self.trajectories]
        return {
            "count": len(rewards),
            "mean": sum(rewards) / len(rewards),
            "min": min(rewards),
            "max": max(rewards),
            "std": (sum((r - sum(rewards) / len(rewards)) ** 2 for r in rewards) / len(rewards))
            ** 0.5,
        }


class LeanRewardModel:
    """Reward model for Lean formalization tasks.

    Provides rewards based on:
    - Proof completion (goals accomplished)
    - Proof length (shorter = better)
    - Error count (fewer = better)
    - Compilation success
    """

    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
    ):
        self.weights = weights or {
            "completion": 1.0,
            "length": -0.1,  # Negative = shorter is better
            "errors": -0.5,  # Negative = fewer errors is better
            "compilation": 0.5,
        }

    def compute_reward(self, trajectory: List[Dict[str, str]]) -> float:
        """Compute reward from Lean trajectory.

        Analyzes messages for:
        - "goals accomplished" or "no errors"
        - Error messages
        - Proof length (number of tactics)
        """
        reward = 0.0
        text = "\n".join(msg.get("content", "") for msg in trajectory).lower()

        # Completion reward
        if "goals accomplished" in text or "no errors" in text:
            reward += self.weights["completion"]

        # Compilation success
        if "compiled successfully" in text or "build succeeded" in text:
            reward += self.weights["compilation"]

        # Error penalty
        error_count = text.count("error") + text.count("sorry")
        reward += error_count * self.weights["errors"]

        # Length penalty (simplistic: count tactics)
        tactic_count = text.count("apply") + text.count("intro") + text.count("exact")
        reward += tactic_count * self.weights["length"]

        return reward


def create_atropos_trainer(
    model_name: str,
    output_dir: Path,
    use_lean_rewards: bool = True,
    **kwargs,
) -> AtroposTrainer:
    """Factory function to create Atropos trainer.

    Args:
        model_name: Model to train
        output_dir: Where to save outputs
        use_lean_rewards: Use LeanRewardModel
        **kwargs: Additional config options

    Returns:
        Configured AtroposTrainer
    """
    config = AtroposConfig(
        model_name=model_name,
        output_dir=output_dir,
        **kwargs,
    )

    reward_model = LeanRewardModel() if use_lean_rewards else None

    return AtroposTrainer(config, reward_model)
