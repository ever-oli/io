"""Lean project registry — lightweight OpenGauss-style ``/project`` pins under ``~/.io/lean/``.

Stores named roots for ``--project <name>`` on ``io lean submit|prove`` and optional
default when ``lean.prefer_registry_current`` is true.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9._-]{0,63}$")


def registry_path(home: Path) -> Path:
    return home / "lean" / "registry.yaml"


def _empty_registry() -> dict[str, Any]:
    return {"version": 1, "current": None, "projects": {}}


def load_registry(home: Path) -> dict[str, Any]:
    path = registry_path(home)
    if not path.is_file():
        return _empty_registry()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return _empty_registry()
    if not isinstance(raw, dict):
        return _empty_registry()
    projects = raw.get("projects")
    if not isinstance(projects, dict):
        projects = {}
    cur = raw.get("current")
    return {"version": int(raw.get("version", 1)), "current": cur if isinstance(cur, str) else None, "projects": projects}


def save_registry(home: Path, data: dict[str, Any]) -> None:
    path = registry_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "version": int(data.get("version", 1)),
        "current": data.get("current"),
        "projects": dict(data.get("projects") or {}),
    }
    path.write_text(yaml.safe_dump(out, sort_keys=False, allow_unicode=True), encoding="utf-8")


def validate_name(name: str) -> str:
    name = name.strip()
    if not name or not _NAME_RE.match(name):
        raise ValueError(
            "project name must start with a letter and use only letters, digits, ._- (max 64 chars)"
        )
    return name


def resolve_path(path_str: str, *, cwd: Path) -> Path:
    p = Path(path_str).expanduser()
    return (cwd / p).resolve() if not p.is_absolute() else p.resolve()


def resolve_named_project_path(name: str, *, home: Path, cwd: Path) -> Path:
    reg = load_registry(home)
    projects = reg.get("projects") or {}
    if not isinstance(projects, dict) or name not in projects:
        raise KeyError(f"unknown lean project {name!r}; run: io lean project list")
    entry = projects[name]
    if isinstance(entry, str):
        path_str = entry
    elif isinstance(entry, dict):
        path_str = str(entry.get("path", ""))
    else:
        raise KeyError(f"invalid registry entry for {name!r}")
    if not path_str.strip():
        raise KeyError(f"project {name!r} has no path")
    return resolve_path(path_str, cwd=cwd)


def resolve_effective_project_dir(
    *,
    home: Path,
    cwd: Path,
    config: dict[str, Any],
    project_dir: Path | None,
    project_name: str | None,
) -> tuple[Path | None, str | None]:
    """Pick ``--project-dir`` for Aristotle. Returns ``(path, error)``."""
    lean = config.get("lean") if isinstance(config.get("lean"), dict) else {}

    if project_name:
        name = project_name.strip()
        if not name:
            return None, "empty --project name"
        try:
            return resolve_named_project_path(name, home=home, cwd=cwd), None
        except KeyError as exc:
            return None, str(exc)

    if project_dir is not None:
        return project_dir.resolve(), None

    if bool(lean.get("prefer_registry_current")):
        reg = load_registry(home)
        cur = reg.get("current")
        if isinstance(cur, str) and cur.strip():
            try:
                return resolve_named_project_path(cur.strip(), home=home, cwd=cwd), None
            except KeyError:
                pass

    return None, None  # caller uses default_project_dir


def format_registry_list(home: Path, *, cwd: Path) -> str:
    reg = load_registry(home)
    projects = reg.get("projects") or {}
    cur = reg.get("current")
    lines = ["IO lean projects (registry.yaml)", f"current: {cur or '(none)'}", ""]
    if not projects:
        lines.append("(no projects — io lean project add <name> <path>)")
        return "\n".join(lines)
    for name in sorted(projects):
        mark = "*" if name == cur else " "
        try:
            p = resolve_named_project_path(name, home=home, cwd=cwd)
            exists = "ok" if p.is_dir() else "missing"
        except KeyError:
            p = Path("?")
            exists = "invalid"
        lines.append(f" {mark} {name}: {p} [{exists}]")
    return "\n".join(lines)


def cmd_project_add(home: Path, name: str, path_str: str, *, cwd: Path, set_current: bool = False) -> str:
    name = validate_name(name)
    path = resolve_path(path_str, cwd=cwd)
    reg = load_registry(home)
    projects = dict(reg.get("projects") or {})
    projects[name] = {"path": str(path)}
    reg["projects"] = projects
    if set_current:
        reg["current"] = name
    save_registry(home, reg)
    return f"Registered lean project {name!r} -> {path}" + (" (set as current)" if set_current else "")


def cmd_project_use(home: Path, name: str) -> str:
    name = validate_name(name)
    reg = load_registry(home)
    projects = reg.get("projects") or {}
    if name not in projects:
        raise ValueError(f"unknown project {name!r}")
    reg["current"] = name
    save_registry(home, reg)
    return f"Current lean project is now {name!r}"


def cmd_project_remove(home: Path, name: str) -> str:
    name = validate_name(name)
    reg = load_registry(home)
    projects = dict(reg.get("projects") or {})
    if name not in projects:
        raise ValueError(f"unknown project {name!r}")
    del projects[name]
    reg["projects"] = projects
    if reg.get("current") == name:
        reg["current"] = None
    save_registry(home, reg)
    return f"Removed lean project {name!r}"


def cmd_project_show(home: Path, *, cwd: Path) -> str:
    reg = load_registry(home)
    cur = reg.get("current")
    lines = [f"registry: {registry_path(home)}", f"current: {cur or '(none)'}", ""]
    projects = reg.get("projects") or {}
    lines.append(yaml.safe_dump({"projects": projects}, sort_keys=True, allow_unicode=True))
    return "\n".join(lines)


def handle_lean_project_slash(body: str, *, home: Path, cwd: Path) -> str:
    """Handle ``/lean project …`` remainder (body is e.g. ``list`` or ``use foo``)."""
    parts = body.strip().split()
    if not parts:
        raise ValueError(
            "Usage: /lean project list|show|use <name>|add <name> <path>|remove <name>"
        )
    action = parts[0].lower()
    try:
        if action == "list":
            return format_registry_list(home, cwd=cwd)
        if action == "show":
            return cmd_project_show(home, cwd=cwd)
        if action == "use":
            if len(parts) < 2:
                raise ValueError("Usage: /lean project use <name>")
            return cmd_project_use(home, parts[1])
        if action == "remove":
            if len(parts) < 2:
                raise ValueError("Usage: /lean project remove <name>")
            return cmd_project_remove(home, parts[1])
        if action == "add":
            if len(parts) < 3:
                raise ValueError("Usage: /lean project add <name> <path>")
            return cmd_project_add(home, parts[1], " ".join(parts[2:]), cwd=cwd)
    except ValueError:
        raise
    raise ValueError(
        "Usage: /lean project list|show|use <name>|add <name> <path>|remove <name>"
    )


def registry_summary(home: Path, *, cwd: Path) -> dict[str, Any]:
    reg = load_registry(home)
    names = sorted((reg.get("projects") or {}).keys())
    return {
        "registry_path": str(registry_path(home)),
        "current": reg.get("current"),
        "project_names": names,
        "count": len(names),
    }
