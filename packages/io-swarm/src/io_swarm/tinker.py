"""Tinker integration - Alternative training framework connector.

Tinker is a lightweight RL framework from Thinking Machines Lab.
Provides simplified training loops for agent fine-tuning.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .atropos import RewardModel, TrainingTrajectory

logger = logging.getLogger(__name__)


@dataclass
class TinkerConfig:
    """Configuration for Tinker training."""

    model_name: str = "gpt-4"
    num_episodes: int = 100
    max_steps_per_episode: int = 50
    learning_rate: float = 3e-4
    gamma: float = 0.99  # Discount factor
    lambda_gae: float = 0.95  # GAE lambda
    clip_ratio: float = 0.2
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    batch_size: int = 32
    output_dir: Path = field(default_factory=lambda: Path("./tinker_output"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "num_episodes": self.num_episodes,
            "max_steps_per_episode": self.max_steps_per_episode,
            "learning_rate": self.learning_rate,
            "gamma": self.gamma,
            "lambda_gae": self.lambda_gae,
            "clip_ratio": self.clip_ratio,
            "value_coef": self.value_coef,
            "entropy_coef": self.entropy_coef,
            "batch_size": self.batch_size,
            "output_dir": str(self.output_dir),
        }


@dataclass
class Episode:
    """A single training episode."""

    episode_id: str
    trajectory: TrainingTrajectory
    total_reward: float
    num_steps: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "trajectory": self.trajectory.to_dict(),
            "total_reward": self.total_reward,
            "num_steps": self.num_steps,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }


class TinkerTrainer:
    """Tinker-style trainer for policy optimization.

    Simplified RL training with episode-based learning.
    """

    def __init__(
        self,
        config: TinkerConfig,
        reward_model: Optional[RewardModel] = None,
        policy_fn: Optional[Callable[[str], str]] = None,
    ):
        self.config = config
        self.reward_model = reward_model
        self.policy_fn = policy_fn
        self.episodes: List[Episode] = []
        self.current_episode = 0

        # Ensure output dir exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[Tinker] Initialized trainer for {config.model_name}")

    def run_episode(
        self,
        initial_state: str,
        agent_step_fn: Callable[[str], str],
    ) -> Episode:
        """Run a single training episode.

        Args:
            initial_state: Starting state/context
            agent_step_fn: Function that takes state and returns action

        Returns:
            Completed Episode
        """
        episode_id = f"ep_{self.current_episode:05d}"
        self.current_episode += 1

        messages = []
        total_reward = 0.0
        state = initial_state

        for step in range(self.config.max_steps_per_episode):
            # Agent takes action
            action = agent_step_fn(state)

            # Record step
            messages.append(
                {
                    "role": "user" if step % 2 == 0 else "assistant",
                    "content": action,
                }
            )

            # Compute reward
            if self.reward_model:
                step_reward = self.reward_model.compute_reward(messages)
                total_reward += step_reward * (self.config.gamma**step)

            # Update state (simplified)
            state = action

            # Check for episode end
            if "DONE" in action or "COMPLETE" in action:
                break

        # Create trajectory
        traj = TrainingTrajectory(
            trajectory_id=episode_id,
            messages=messages,
            reward=total_reward,
            metadata={"steps": len(messages)},
        )

        episode = Episode(
            episode_id=episode_id,
            trajectory=traj,
            total_reward=total_reward,
            num_steps=len(messages),
        )

        self.episodes.append(episode)
        logger.info(
            f"[Tinker] Episode {episode_id}: reward={total_reward:.2f}, steps={len(messages)}"
        )

        return episode

    def train_batch(self, batch_size: Optional[int] = None) -> Dict[str, float]:
        """Train on a batch of episodes.

        Simplified policy gradient update.

        Returns:
            Training metrics
        """
        if batch_size is None:
            batch_size = self.config.batch_size

        if len(self.episodes) < batch_size:
            logger.warning(f"[Tinker] Not enough episodes ({len(self.episodes)} < {batch_size})")
            return {"loss": 0.0}

        # Get recent episodes
        batch = self.episodes[-batch_size:]

        # Compute metrics
        rewards = [ep.total_reward for ep in batch]
        avg_reward = sum(rewards) / len(rewards)

        # Simplified loss (in real implementation, would compute policy gradient)
        loss = -avg_reward  # Negative because we want to maximize reward

        metrics = {
            "loss": loss,
            "avg_reward": avg_reward,
            "max_reward": max(rewards),
            "min_reward": min(rewards),
            "episodes": len(batch),
        }

        logger.info(f"[Tinker] Batch training: loss={loss:.4f}, avg_reward={avg_reward:.2f}")
        return metrics

    def export_episodes(self, output_file: Optional[Path] = None) -> Path:
        """Export all episodes to JSONL."""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.config.output_dir / f"episodes_{timestamp}.jsonl"

        with open(output_file, "w") as f:
            for ep in self.episodes:
                f.write(json.dumps(ep.to_dict()) + "\n")

        logger.info(f"[Tinker] Exported {len(self.episodes)} episodes to {output_file}")
        return output_file

    def get_training_stats(self) -> Dict[str, Any]:
        """Get training statistics."""
        if not self.episodes:
            return {"episodes": 0}

        rewards = [ep.total_reward for ep in self.episodes]
        steps = [ep.num_steps for ep in self.episodes]

        return {
            "episodes": len(self.episodes),
            "avg_reward": sum(rewards) / len(rewards),
            "avg_steps": sum(steps) / len(steps),
            "best_episode": max(self.episodes, key=lambda e: e.total_reward).episode_id,
            "recent_avg": sum(rewards[-10:]) / min(10, len(rewards)),
        }


class PolicyOptimizer:
    """Policy optimization utilities.

    Implements PPO-style policy updates.
    """

    def __init__(
        self,
        learning_rate: float = 3e-4,
        clip_ratio: float = 0.2,
    ):
        self.learning_rate = learning_rate
        self.clip_ratio = clip_ratio

    def compute_advantage(
        self,
        rewards: List[float],
        values: List[float],
        gamma: float = 0.99,
        lam: float = 0.95,
    ) -> List[float]:
        """Compute Generalized Advantage Estimation (GAE).

        Args:
            rewards: List of rewards
            values: List of value estimates
            gamma: Discount factor
            lam: GAE lambda

        Returns:
            List of advantages
        """
        advantages = []
        gae = 0.0

        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value = 0
            else:
                next_value = values[t + 1]

            delta = rewards[t] + gamma * next_value - values[t]
            gae = delta + gamma * lam * gae
            advantages.insert(0, gae)

        return advantages

    def compute_policy_loss(
        self,
        old_log_probs: List[float],
        new_log_probs: List[float],
        advantages: List[float],
    ) -> float:
        """Compute PPO policy loss.

        Args:
            old_log_probs: Log probs from old policy
            new_log_probs: Log probs from new policy
            advantages: Computed advantages

        Returns:
            Policy loss
        """
        loss = 0.0

        for old_lp, new_lp, adv in zip(old_log_probs, new_log_probs, advantages):
            ratio = new_lp - old_lp  # Log space
            clipped_ratio = max(min(ratio, self.clip_ratio), -self.clip_ratio)

            # PPO objective
            obj1 = ratio * adv
            obj2 = clipped_ratio * adv

            loss -= min(obj1, obj2)

        return loss / len(advantages)


def create_tinker_trainer(
    model_name: str,
    output_dir: Path,
    use_lean_rewards: bool = True,
    **kwargs,
) -> TinkerTrainer:
    """Factory function for Tinker trainer.

    Args:
        model_name: Model to train
        output_dir: Output directory
        use_lean_rewards: Use LeanRewardModel
        **kwargs: Additional config

    Returns:
        Configured TinkerTrainer
    """
    from .atropos import LeanRewardModel

    config = TinkerConfig(
        model_name=model_name,
        output_dir=output_dir,
        **kwargs,
    )

    reward_model = LeanRewardModel() if use_lean_rewards else None

    return TinkerTrainer(config, reward_model)
