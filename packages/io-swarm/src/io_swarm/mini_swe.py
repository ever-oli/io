"""Mini-SWE Agent - Software engineering benchmarking.

Benchmarks agent performance on software engineering tasks.
Integrates with existing session DB and logging infrastructure.
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

from .manager import SwarmManager, SwarmTask, TaskStatus
from .trajectory import CompressionConfig, TrajectoryCompressor

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    task_id: str
    benchmark_name: str
    success: bool
    duration_seconds: float
    iterations: int
    tokens_used: int = 0
    trajectory_file: Optional[Path] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "benchmark_name": self.benchmark_name,
            "success": self.success,
            "duration_seconds": self.duration_seconds,
            "iterations": self.iterations,
            "tokens_used": self.tokens_used,
            "trajectory_file": str(self.trajectory_file) if self.trajectory_file else None,
            "metrics": self.metrics,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }


class MiniSWEAgent:
    """Mini Software Engineering agent for benchmarking.

    Runs agents on SWE-bench style tasks and records performance metrics.
    Integrates with IO's existing session DB for trajectory logging.
    """

    def __init__(
        self,
        output_dir: Path,
        compress_trajectories: bool = True,
    ):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.swarm = SwarmManager()
        self.compressor = TrajectoryCompressor() if compress_trajectories else None
        self.results: List[BenchmarkResult] = []

    def run_benchmark(
        self,
        benchmark_name: str,
        task_description: str,
        command: List[str],
        project_dir: Path,
        timeout: int = 1800,
        expected_result: Optional[str] = None,
    ) -> BenchmarkResult:
        """Run a single benchmark task.

        Args:
            benchmark_name: Name of the benchmark (e.g., "mathlib-001")
            task_description: What the agent should do
            command: Command to run the agent
            project_dir: Working directory
            timeout: Max seconds to run
            expected_result: Expected output for verification

        Returns:
            BenchmarkResult with metrics
        """
        logger.info(f"[Mini-SWE] Starting benchmark: {benchmark_name}")
        start_time = time.time()

        # Spawn the agent
        task = self.swarm.spawn(
            command=command,
            description=f"[Benchmark {benchmark_name}] {task_description[:80]}",
            project_dir=project_dir,
            interactive=False,
        )

        # Wait for completion with timeout
        success = self._wait_for_task(task, timeout)
        duration = time.time() - start_time

        # Collect metrics from task
        iterations = task.metrics.get("iterations", 1) if hasattr(task, "metrics") else 1
        tokens_used = task.metrics.get("tokens_used", 0) if hasattr(task, "metrics") else 0

        # Verify result if expected output provided
        verified = True
        if expected_result and task.process:
            # Check last output
            output = "".join(task._output_buffer[-100:]) if hasattr(task, "_output_buffer") else ""
            verified = expected_result in output

        # Export trajectory if available
        trajectory_file = None
        if hasattr(task, "session_id") and task.session_id:
            trajectory_file = self._export_trajectory(task, benchmark_name)

        result = BenchmarkResult(
            task_id=task.task_id,
            benchmark_name=benchmark_name,
            success=success and verified,
            duration_seconds=duration,
            iterations=iterations,
            tokens_used=tokens_used,
            trajectory_file=trajectory_file,
            metrics={
                "exit_code": task.exit_code,
                "project_dir": str(project_dir),
            },
            error_message=task.error_message,
        )

        self.results.append(result)
        logger.info(f"[Mini-SWE] Benchmark {benchmark_name}: {'✓' if result.success else '✗'}")

        return result

    def run_swe_bench_task(
        self,
        task_id: str,
        repo_path: Path,
        problem_statement: str,
        agent_command: List[str],
        timeout: int = 3600,
    ) -> BenchmarkResult:
        """Run a SWE-bench style task.

        Args:
            task_id: SWE-bench task ID (e.g., "django-1234")
            repo_path: Path to repository
            problem_statement: Description of the issue
            agent_command: How to invoke the agent
            timeout: Max runtime
        """
        logger.info(f"[Mini-SWE] Running SWE-bench task: {task_id}")

        # Run the benchmark
        result = self.run_benchmark(
            benchmark_name=task_id,
            task_description=problem_statement,
            command=agent_command,
            project_dir=repo_path,
            timeout=timeout,
        )

        return result

    def run_mathlib_benchmark(
        self,
        theorem_name: str,
        theorem_statement: str,
        project_dir: Path,
        timeout: int = 1800,
    ) -> BenchmarkResult:
        """Run a Mathlib formalization benchmark.

        Args:
            theorem_name: Name of the theorem
            theorem_statement: The statement to prove
            project_dir: Mathlib or project directory
            timeout: Max runtime
        """
        from .workflows import spawn_autoprove

        logger.info(f"[Mini-SWE] Running Mathlib benchmark: {theorem_name}")

        # Use autoprove for autonomous proving
        task = spawn_autoprove(
            theorem=theorem_statement,
            project_dir=project_dir,
            max_iterations=100,
            interactive=False,
        )

        # Wait and collect results
        start_time = time.time()
        success = self._wait_for_task(task, timeout)
        duration = time.time() - start_time

        result = BenchmarkResult(
            task_id=task.task_id,
            benchmark_name=f"mathlib-{theorem_name}",
            success=success and task.status == TaskStatus.COMPLETE,
            duration_seconds=duration,
            iterations=100,
            trajectory_file=self._export_trajectory(task, theorem_name),
        )

        self.results.append(result)
        return result

    def _wait_for_task(self, task: SwarmTask, timeout: int) -> bool:
        """Wait for task to complete with timeout."""
        start = time.time()
        while time.time() - start < timeout:
            if task.status in (TaskStatus.COMPLETE, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return task.status == TaskStatus.COMPLETE
            time.sleep(0.5)

        # Timeout - cancel task
        self.swarm.cancel(task.task_id)
        return False

    def _export_trajectory(
        self,
        task: SwarmTask,
        name: str,
    ) -> Optional[Path]:
        """Export task trajectory to file."""
        trajectory_file = self.output_dir / f"{name}_{task.task_id}.jsonl"

        # Build trajectory from task output
        trajectory = []

        # Add system message
        trajectory.append(
            {
                "role": "system",
                "content": f"Task: {task.description}",
            }
        )

        # Add output buffer if available
        if hasattr(task, "_output_buffer"):
            for line in task._output_buffer:
                trajectory.append(
                    {
                        "role": "assistant",
                        "content": line,
                    }
                )

        # Write trajectory
        with open(trajectory_file, "w") as f:
            for entry in trajectory:
                f.write(json.dumps(entry) + "\n")

        # Compress if configured
        if self.compressor:
            compressed_file = trajectory_file.with_suffix(".compressed.jsonl")
            self.compressor.compress_file(trajectory_file, compressed_file)
            return compressed_file

        return trajectory_file

    def export_results(
        self,
        output_file: Optional[Path] = None,
    ) -> Path:
        """Export all benchmark results to JSON."""
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.output_dir / f"benchmark_results_{timestamp}.json"

        data = {
            "total": len(self.results),
            "successful": sum(1 for r in self.results if r.success),
            "failed": sum(1 for r in self.results if not r.success),
            "results": [r.to_dict() for r in self.results],
        }

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"[Mini-SWE] Exported {len(self.results)} results to {output_file}")
        return output_file

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        total = len(self.results)
        successful = sum(1 for r in self.results if r.success)

        return {
            "total_benchmarks": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": successful / total if total > 0 else 0,
            "avg_duration": sum(r.duration_seconds for r in self.results) / total
            if total > 0
            else 0,
            "total_tokens": sum(r.tokens_used for r in self.results),
        }


def run_swe_bench_suite(
    task_file: Path,
    output_dir: Path,
    agent_type: str = "autoprove",
    parallel: int = 1,
) -> Dict[str, Any]:
    """Run a full SWE-bench suite from task file.

    Args:
        task_file: JSON file with tasks
        output_dir: Where to save results
        agent_type: Which agent to use
        parallel: Number of parallel workers

    Returns:
        Summary statistics
    """
    # Load tasks
    with open(task_file) as f:
        tasks = json.load(f)

    agent = MiniSWEAgent(output_dir)

    for task_data in tasks:
        agent.run_swe_bench_task(
            task_id=task_data["task_id"],
            repo_path=Path(task_data["repo_path"]),
            problem_statement=task_data["problem_statement"],
            agent_command=task_data.get("agent_command", ["io", "agent", "run"]),
        )

    # Export results
    agent.export_results()

    return agent.get_summary()
