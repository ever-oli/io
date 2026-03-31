"""Project management for Lean workflows.

Like Gauss's /project commands - create, init, use, list projects.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class LeanProject:
    """A registered Lean project."""

    name: str
    path: Path
    created_at: datetime
    template_source: Optional[str] = None
    description: Optional[str] = None


class ProjectRegistry:
    """Manages Lean project registry."""

    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self._projects: Dict[str, LeanProject] = {}
        self._load()

    def _load(self) -> None:
        """Load registry from disk."""
        if not self.registry_path.exists():
            return

        try:
            data = yaml.safe_load(self.registry_path.read_text())
            if not isinstance(data, dict):
                return

            for name, proj_data in data.get("projects", {}).items():
                self._projects[name] = LeanProject(
                    name=name,
                    path=Path(proj_data["path"]),
                    created_at=datetime.fromisoformat(
                        proj_data.get("created_at", datetime.now().isoformat())
                    ),
                    template_source=proj_data.get("template_source"),
                    description=proj_data.get("description"),
                )
        except Exception as e:
            logger.warning(f"Failed to load project registry: {e}")

    def _save(self) -> None:
        """Save registry to disk."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "projects": {
                name: {
                    "path": str(proj.path),
                    "created_at": proj.created_at.isoformat(),
                    "template_source": proj.template_source,
                    "description": proj.description,
                }
                for name, proj in self._projects.items()
            }
        }

        self.registry_path.write_text(yaml.safe_dump(data))

    def add(
        self,
        name: str,
        path: Path,
        template_source: Optional[str] = None,
        description: Optional[str] = None,
    ) -> LeanProject:
        """Add a project to the registry."""
        project = LeanProject(
            name=name,
            path=path.resolve(),
            created_at=datetime.now(),
            template_source=template_source,
            description=description,
        )
        self._projects[name] = project
        self._save()
        return project

    def get(self, name: str) -> Optional[LeanProject]:
        """Get project by name."""
        return self._projects.get(name)

    def remove(self, name: str) -> bool:
        """Remove project from registry."""
        if name in self._projects:
            del self._projects[name]
            self._save()
            return True
        return False

    def list_all(self) -> List[LeanProject]:
        """List all registered projects."""
        return list(self._projects.values())

    def find_by_path(self, path: Path) -> Optional[LeanProject]:
        """Find project by path."""
        resolved = path.resolve()
        for proj in self._projects.values():
            if proj.path == resolved:
                return proj
        return None


def resolve_project_dir(
    project_name: Optional[str] = None,
    project_path: Optional[Path] = None,
    cwd: Path = Path.cwd(),
    registry: Optional[ProjectRegistry] = None,
) -> Path:
    """Resolve project directory from name, path, or cwd.

    Priority:
    1. Explicit project_path
    2. Named project from registry
    3. .gauss/project.yaml lookup from cwd
    4. cwd itself
    """
    if project_path is not None:
        return project_path.resolve()

    if project_name is not None and registry is not None:
        proj = registry.get(project_name)
        if proj is not None:
            return proj.path
        raise ValueError(f"Project '{project_name}' not found in registry")

    # Look for .gauss/project.yaml
    gauss_root = _find_gauss_root(cwd)
    if gauss_root is not None:
        return gauss_root

    return cwd.resolve()


def _find_gauss_root(start_dir: Path) -> Optional[Path]:
    """Find Lean root from .gauss/project.yaml."""
    current = start_dir.resolve()

    for _ in range(100):  # Prevent infinite loop
        gauss_file = current / ".gauss" / "project.yaml"
        if gauss_file.exists():
            try:
                data = yaml.safe_load(gauss_file.read_text())
                if isinstance(data, dict):
                    lean_root = data.get("lean_root") or data.get("lean_project_dir")
                    if lean_root:
                        resolved = (current / lean_root).resolve()
                        if resolved.exists():
                            return resolved
                        return current
            except Exception:
                pass

        parent = current.parent
        if parent == current:
            break
        current = parent

    return None
