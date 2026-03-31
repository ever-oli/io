"""IO Swarm - Background agent orchestration (Gotenks fusion)."""

__version__ = "0.1.0"

from .manager import SwarmManager, SwarmTask, TaskStatus
from .projects import LeanProject, ProjectRegistry
from .signing import CosignSigner, SigningResult
from .tui import (
    print_swarm_status,
    print_task_detail,
    render_swarm_summary,
    render_swarm_table,
    status_indicator,
)
from .workflows import (
    spawn_draft,
    spawn_formalize,
    spawn_golf,
    spawn_prove,
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
]
