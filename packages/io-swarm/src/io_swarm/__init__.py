"""IO Swarm - Background agent orchestration (Gotenks fusion)."""

__version__ = "0.2.0"

from .manager import SwarmManager, SwarmTask, TaskStatus
from .mini_swe import BenchmarkResult, MiniSWEAgent, run_swe_bench_suite
from .projects import LeanProject, ProjectRegistry
from .signing import CosignSigner, SigningResult
from .trajectory import CompressionConfig, TrajectoryCompressor, TrajectoryMetrics
from .tui import (
    print_swarm_status,
    print_task_detail,
    render_swarm_summary,
    render_swarm_table,
    status_indicator,
)
from .workflows import (
    spawn_autoprove,
    spawn_autoformalize,
    spawn_checkpoint,
    spawn_draft,
    spawn_formalize,
    spawn_golf,
    spawn_prove,
    spawn_refactor,
    spawn_review,
)

__all__ = [
    # Core
    "SwarmManager",
    "SwarmTask",
    "TaskStatus",
    # Projects
    "LeanProject",
    "ProjectRegistry",
    # Signing
    "CosignSigner",
    "SigningResult",
    # Trajectory
    "CompressionConfig",
    "TrajectoryCompressor",
    "TrajectoryMetrics",
    # Mini-SWE
    "MiniSWEAgent",
    "BenchmarkResult",
    "run_swe_bench_suite",
    # TUI
    "render_swarm_table",
    "render_swarm_summary",
    "status_indicator",
    "print_swarm_status",
    "print_task_detail",
    # Workflows
    "spawn_prove",
    "spawn_draft",
    "spawn_formalize",
    "spawn_review",
    "spawn_golf",
    "spawn_autoprove",
    "spawn_autoformalize",
    "spawn_checkpoint",
    "spawn_refactor",
]
