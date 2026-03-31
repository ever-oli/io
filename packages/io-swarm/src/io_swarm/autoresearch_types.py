"""Auto-research loop - Autonomous experiment optimization.

Inspired by pi-autoresearch and karpathy/autoresearch.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExperimentResult:
    """Result of a single experiment run."""

    experiment_id: str
    metric_value: float
    metric_name: str
    unit: str
    direction: str
    status: str
    commit_hash: Optional[str] = None
    description: str = ""
    duration_seconds: float = 0.0
    confidence_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "metric_value": self.metric_value,
            "metric_name": self.metric_name,
            "unit": self.unit,
            "direction": self.direction,
            "status": self.status,
            "commit_hash": self.commit_hash,
            "description": self.description,
            "duration_seconds": self.duration_seconds,
            "confidence_score": self.confidence_score,
            "created_at": self.created_at.isoformat(),
        }
