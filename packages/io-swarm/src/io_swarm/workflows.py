"""Lean workflow commands - /prove, /draft, /formalize, etc.

Spawns background agents for Lean formalization workflows.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .manager import SwarmManager, SwarmTask

logger = logging.getLogger(__name__)


def spawn_prove(
    theorem: str,
    project_dir: Path,
    backend: str = "aristotle",
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = False,
) -> SwarmTask:
    """Spawn a proof agent for the given theorem."""
    manager = SwarmManager()

    # Build command from config
    argv = _build_argv("prove", backend, config)
    argv.append(theorem)

    description = f"Prove: {theorem[:50]}..." if len(theorem) > 50 else f"Prove: {theorem}"

    return manager.spawn(
        command=argv,
        description=description,
        project_dir=project_dir,
        interactive=interactive,
    )


def spawn_draft(
    topic: str,
    project_dir: Path,
    backend: str = "aristotle",
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = False,
) -> SwarmTask:
    """Spawn a drafting agent for the given topic."""
    manager = SwarmManager()

    argv = _build_argv("draft", backend, config)
    argv.append(topic)

    description = f"Draft: {topic[:50]}..." if len(topic) > 50 else f"Draft: {topic}"

    return manager.spawn(
        command=argv,
        description=description,
        project_dir=project_dir,
        interactive=interactive,
    )


def spawn_formalize(
    statement: str,
    project_dir: Path,
    backend: str = "aristotle",
    config: Optional[Dict[str, Any]] = None,
    interactive: bool = False,
) -> SwarmTask:
    """Spawn a formalization agent."""
    manager = SwarmManager()

    argv = _build_argv("formalize", backend, config)
    argv.append(statement)

    description = (
        f"Formalize: {statement[:50]}..." if len(statement) > 50 else f"Formalize: {statement}"
    )

    return manager.spawn(
        command=argv,
        description=description,
        project_dir=project_dir,
        interactive=interactive,
    )


def spawn_review(
    scope: str,
    project_dir: Path,
    backend: str = "aristotle",
    config: Optional[Dict[str, Any]] = None,
) -> SwarmTask:
    """Spawn a review agent."""
    manager = SwarmManager()

    argv = _build_argv("review", backend, config)
    argv.append(scope)

    return manager.spawn(
        command=argv,
        description=f"Review: {scope}",
        project_dir=project_dir,
        interactive=False,
    )


def spawn_golf(
    theorem: str,
    project_dir: Path,
    backend: str = "aristotle",
    config: Optional[Dict[str, Any]] = None,
) -> SwarmTask:
    """Spawn a proof golf agent."""
    manager = SwarmManager()

    argv = _build_argv("golf", backend, config)
    argv.append(theorem)

    return manager.spawn(
        command=argv,
        description=f"Golf: {theorem[:50]}...",
        project_dir=project_dir,
        interactive=False,
    )


def _build_argv(
    verb: str,
    backend: str,
    config: Optional[Dict[str, Any]],
) -> List[str]:
    """Build command argv for given verb and backend."""
    if config is None:
        config = {}

    lean_config = config.get("lean", {})

    # Check for backend-specific config
    backends = lean_config.get("backends", {})
    if backend in backends:
        backend_cfg = backends[backend]
        argv_key = f"{verb}_argv"
        if argv_key in backend_cfg:
            return list(backend_cfg[argv_key])

    # Fall back to global config
    argv_key = f"{verb}_argv"
    if argv_key in lean_config:
        return list(lean_config[argv_key])

    # Default to aristotle via uv
    return ["uv", "run", "aristotle", verb]
