"""Skill discovery and configuration helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

import yaml

from .config import ensure_io_home, get_project_root, load_config, save_config
from .toolsets import PLATFORMS


@dataclass(slots=True)
class SkillInfo:
    name: str
    path: Path
    source: str
    category: str
    description: str
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


def _parse_skill_file(path: Path) -> tuple[str, str]:
    content = path.read_text(encoding="utf-8")
    title = path.parent.name
    description = ""

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    body = content
    name_from_frontmatter = False
    if match:
        try:
            frontmatter = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        if isinstance(frontmatter, dict):
            fm_name = frontmatter.get("name")
            if fm_name is not None and str(fm_name).strip():
                title = str(fm_name).strip()
                name_from_frontmatter = True
            description = str(frontmatter.get("description") or "").strip()
        body = match.group(2)

    if description:
        return title, description

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if not name_from_frontmatter:
                heading = line.lstrip("#").strip()
                if heading:
                    title = heading
            continue
        description = line
        break
    return title, description


def _skill_roots(*, home: Path | None = None, cwd: Path | None = None) -> list[tuple[str, Path]]:
    resolved_home = ensure_io_home(home)
    roots = [
        ("repo", get_project_root() / "skills"),
        ("home", resolved_home / "skills"),
    ]
    if cwd is not None:
        roots.append(("project", cwd / ".io" / "skills"))
    return roots


def get_disabled_skills(config: dict[str, Any], platform: str | None = None) -> set[str]:
    skills_cfg = config.get("skills", {})
    global_disabled = set(skills_cfg.get("disabled", []))
    if platform is None:
        return global_disabled
    platform_disabled = skills_cfg.get("platform_disabled", {}).get(platform)
    if platform_disabled is None:
        return global_disabled
    return set(platform_disabled)


def set_skill_enabled(
    config: dict[str, Any],
    name: str,
    enabled: bool,
    *,
    platform: str | None = None,
) -> dict[str, Any]:
    config.setdefault("skills", {})
    disabled = get_disabled_skills(config, platform)
    if enabled:
        disabled.discard(name)
    else:
        disabled.add(name)
    if platform is None:
        config["skills"]["disabled"] = sorted(disabled)
    else:
        config["skills"].setdefault("platform_disabled", {})
        config["skills"]["platform_disabled"][platform] = sorted(disabled)
    return config


def skill_command_slug(name: str) -> str:
    """Stable slash-token for a skill (Hermes-style: lowercase, hyphenated)."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "skill"


def skill_slash_command_map(
    *,
    home: Path | None = None,
    cwd: Path | None = None,
    platform: str | None = "cli",
) -> dict[str, dict[str, Any]]:
    """Map ``/slug`` -> metadata for REPL / gateway slash completion menus."""
    out: dict[str, dict[str, Any]] = {}
    for skill in discover_skills(home=home, cwd=cwd, platform=platform):
        if not skill.enabled:
            continue
        slug = skill_command_slug(skill.name)
        key = f"/{slug}"
        out[key] = {
            "description": skill.description or f"Skill: {skill.name}",
            "skill_name": skill.name,
            "path": str(skill.path),
        }
    return out


def discover_skills(*, home: Path | None = None, cwd: Path | None = None, platform: str | None = None) -> list[SkillInfo]:
    config = load_config(home)
    disabled = get_disabled_skills(config, platform)
    discovered: dict[str, SkillInfo] = {}
    for source, root in _skill_roots(home=home, cwd=cwd):
        if not root.exists():
            continue
        for candidate in sorted(root.rglob("SKILL.md")):
            category = candidate.parent.parent.name if candidate.parent.parent != root else root.name
            name, description = _parse_skill_file(candidate)
            discovered[name] = SkillInfo(
                name=name,
                path=candidate,
                source=source,
                category=category or "general",
                description=description,
                enabled=name not in disabled,
            )
    return sorted(discovered.values(), key=lambda item: item.name.lower())


def inspect_skill(name: str, *, home: Path | None = None, cwd: Path | None = None, platform: str | None = None) -> dict[str, Any]:
    for skill in discover_skills(home=home, cwd=cwd, platform=platform):
        if skill.name == name:
            payload = skill.to_dict()
            payload["content"] = skill.path.read_text(encoding="utf-8")
            return payload
    raise KeyError(name)


def search_skills(query: str, *, home: Path | None = None, cwd: Path | None = None, platform: str | None = None) -> list[dict[str, Any]]:
    lowered = query.lower()
    matches = []
    for skill in discover_skills(home=home, cwd=cwd, platform=platform):
        haystack = "\n".join((skill.name, skill.category, skill.description)).lower()
        if lowered in haystack:
            matches.append(skill.to_dict())
    return matches


def save_skill_toggle(
    name: str,
    *,
    enabled: bool,
    home: Path | None = None,
    platform: str | None = None,
) -> dict[str, Any]:
    if platform is not None and platform not in PLATFORMS:
        raise KeyError(platform)
    config = load_config(home)
    set_skill_enabled(config, name, enabled, platform=platform)
    save_config(config, home)
    return config
