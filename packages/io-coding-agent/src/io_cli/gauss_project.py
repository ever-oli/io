"""Optional OpenGauss-style ``.gauss/project.yaml`` lean root hints.

If present next to the resolved project directory, IO can redirect ``--project-dir`` to a
nested Lean root (Gauss repos often keep metadata under ``.gauss/``).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_GAUSS_NAMES = ("project.yaml", "project.yml")


def _lean_section(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("lean")
    return raw if isinstance(raw, dict) else {}


def _resolve_relative(base: Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    return (base / p).resolve() if not p.is_absolute() else p.resolve()


def _first_path_key(data: dict[str, Any]) -> str | None:
    for key in (
        "lean_root",
        "lean_project_dir",
        "lean_dir",
        "lean_path",
    ):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    paths = data.get("paths")
    if isinstance(paths, dict):
        for key in ("lean", "lean_root", "lean_project"):
            val = paths.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    lean_block = data.get("lean")
    if isinstance(lean_block, dict):
        for key in ("root", "path", "project_dir"):
            val = lean_block.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return None


def _lean_root_from_gauss_file(gauss_file: Path, project_dir: Path) -> Path | None:
    try:
        raw = yaml.safe_load(gauss_file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError) as exc:
        logger.debug("gauss project yaml unreadable %s: %s", gauss_file, exc)
        return None
    if not isinstance(raw, dict):
        return None
    path_str = _first_path_key(raw)
    if path_str is None:
        return None
    return _resolve_relative(project_dir, path_str)


def resolve_lean_root_with_gauss(project_dir: Path, config: dict[str, Any]) -> Path:
    """If ``lean.respect_gauss_project_yaml`` and ``project_dir/.gauss/project.yaml`` exist, return nested lean root."""
    lean = _lean_section(config)
    if not bool(lean.get("respect_gauss_project_yaml", True)):
        return project_dir.resolve()

    base = project_dir.resolve()
    for name in _GAUSS_NAMES:
        candidate = base / ".gauss" / name
        if not candidate.is_file():
            continue
        nested = _lean_root_from_gauss_file(candidate, base)
        if nested is not None:
            return nested
    return base
