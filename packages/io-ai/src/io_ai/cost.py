"""Simple pricing support for local usage accounting."""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import Usage


@dataclass(frozen=True)
class Pricing:
    input_per_1m: float
    output_per_1m: float


DEFAULT_PRICING: dict[str, Pricing] = {
    "mock/io-test": Pricing(0.0, 0.0),
    "openai/gpt-5-mini": Pricing(0.25, 2.0),
    "openrouter/openai/gpt-5-mini": Pricing(0.25, 2.0),
    "anthropic/claude-sonnet-4-5": Pricing(3.0, 15.0),
}


@dataclass
class CostTracker:
    pricing: dict[str, Pricing] = field(default_factory=lambda: dict(DEFAULT_PRICING))

    def estimate(self, model_id: str, usage: Usage) -> Usage:
        pricing = self.pricing.get(model_id, Pricing(0.0, 0.0))
        usage.cost_usd = (
            (usage.input_tokens / 1_000_000.0) * pricing.input_per_1m
            + (usage.output_tokens / 1_000_000.0) * pricing.output_per_1m
        )
        return usage

