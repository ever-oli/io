"""IO-compatible skills tools backed by IO's skill layout."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import yaml

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import ensure_io_home, get_project_root
from ..skills import discover_skills


MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ALLOWED_SUBDIRS = {"references", "templates", "scripts", "assets"}


def _split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    if not content.startswith("---"):
        return {}, content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return {}, content
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        frontmatter = {}
    if not isinstance(frontmatter, dict):
        frontmatter = {}
    return frontmatter, match.group(2)


def _parse_skill_summary(skill_md: Path) -> tuple[str, str, dict[str, Any], str]:
    content = skill_md.read_text(encoding="utf-8")
    frontmatter, body = _split_frontmatter(content)
    name = str(frontmatter.get("name") or skill_md.parent.name).strip() or skill_md.parent.name
    description = str(frontmatter.get("description") or "").strip()
    if not description:
        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            description = line
            break
    return name, description[:MAX_DESCRIPTION_LENGTH], frontmatter, content


def _skill_roots(home: Path | None, cwd: Path | None) -> list[tuple[str, Path]]:
    resolved_home = ensure_io_home(home)
    roots = [
        ("repo", get_project_root() / "skills"),
        ("repo-optional", get_project_root() / "optional-skills"),
        ("home", resolved_home / "skills"),
    ]
    if cwd is not None:
        roots.append(("project", cwd / ".io" / "skills"))
    return roots


def _category_for(skill_dir: Path, root: Path) -> str | None:
    try:
        relative = skill_dir.relative_to(root)
    except ValueError:
        return None
    if len(relative.parts) > 1:
        return relative.parts[0]
    return None


def _linked_files(skill_dir: Path) -> dict[str, list[str]]:
    linked: dict[str, list[str]] = {}
    for subdir_name in sorted(ALLOWED_SUBDIRS):
        subdir = skill_dir / subdir_name
        if not subdir.exists():
            continue
        files = [
            str(path.relative_to(skill_dir)).replace("\\", "/")
            for path in sorted(subdir.rglob("*"))
            if path.is_file()
        ]
        if files:
            linked[subdir_name] = files
    return linked


def _find_skill(
    name: str,
    *,
    home: Path | None,
    cwd: Path | None,
) -> tuple[str, Path, Path] | None:
    query = name.strip()
    if not query:
        return None

    discovered = {skill.name: skill for skill in discover_skills(home=home, cwd=cwd)}
    if query in discovered:
        skill = discovered[query]
        return skill.source, skill.path.parent, skill.path

    for source, root in reversed(_skill_roots(home, cwd)):
        if not root.exists():
            continue
        direct_dir = root / query
        direct_skill = direct_dir / "SKILL.md"
        if direct_skill.exists():
            return source, direct_dir, direct_skill
        for candidate in sorted(root.rglob("SKILL.md")):
            skill_dir = candidate.parent
            try:
                relative = str(skill_dir.relative_to(root)).replace("\\", "/")
            except ValueError:
                relative = skill_dir.name
            if skill_dir.name == query or relative == query:
                return source, skill_dir, candidate
    return None


def _find_root_for_path(
    path: Path,
    *,
    home: Path | None,
    cwd: Path | None,
) -> Path | None:
    for _source, root in _skill_roots(home, cwd):
        if path.is_relative_to(root):
            return root
    return None


def _validate_frontmatter(content: str) -> str | None:
    if not content.strip():
        return "Content cannot be empty."
    if not content.startswith("---"):
        return "SKILL.md must start with YAML frontmatter (---)."
    frontmatter, body = _split_frontmatter(content)
    if not frontmatter:
        return "SKILL.md frontmatter is invalid or not closed."
    if "name" not in frontmatter:
        return "Frontmatter must include 'name' field."
    if "description" not in frontmatter:
        return "Frontmatter must include 'description' field."
    description = str(frontmatter["description"])
    if len(description) > MAX_DESCRIPTION_LENGTH:
        return f"Description exceeds {MAX_DESCRIPTION_LENGTH} characters."
    if not body.strip():
        return "SKILL.md must have content after the frontmatter."
    return None


def _validate_skill_name(name: str) -> str | None:
    if not name:
        return "Skill name is required."
    if len(name) > MAX_NAME_LENGTH:
        return f"Skill name exceeds {MAX_NAME_LENGTH} characters."
    if not VALID_NAME_RE.match(name):
        return (
            f"Invalid skill name '{name}'. Use lowercase letters, numbers, "
            "hyphens, dots, and underscores."
        )
    return None


def _validate_support_path(file_path: str) -> str | None:
    if not file_path:
        return "file_path is required."
    normalized = Path(file_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        return "Path traversal is not allowed."
    if not normalized.parts or normalized.parts[0] not in ALLOWED_SUBDIRS:
        allowed = ", ".join(sorted(ALLOWED_SUBDIRS))
        return f"File must be under one of: {allowed}."
    if len(normalized.parts) < 2:
        return "Provide a file path, not just a directory."
    return None


def _load_support_file(skill_dir: Path, file_path: str) -> tuple[Path | None, str | None]:
    normalized = Path(file_path)
    if normalized.is_absolute() or ".." in normalized.parts:
        return None, "Path traversal is not allowed."
    target = (skill_dir / normalized).resolve()
    try:
        target.relative_to(skill_dir.resolve())
    except ValueError:
        return None, "Path traversal is not allowed."
    return target, None


def check_skills_requirements() -> bool:
    return True


def skills_list(
    category: str | None = None,
    task_id: str | None = None,
    *,
    home: Path | None = None,
    cwd: Path | None = None,
) -> str:
    del task_id
    skills = []
    for skill in discover_skills(home=home, cwd=cwd):
        if category and skill.category != category:
            continue
        payload = skill.to_dict()
        payload.pop("enabled", None)
        skills.append(payload)
    categories = sorted(
        {str(skill.get("category")) for skill in skills if skill.get("category")}
    )
    result: dict[str, Any] = {
        "success": True,
        "skills": skills,
        "categories": categories,
        "count": len(skills),
        "hint": "Use skill_view(name) to see full content, tags, and linked files",
    }
    if not skills:
        result["message"] = "No skills found in skills directories."
    return json.dumps(result, ensure_ascii=False)


def skill_view(
    name: str,
    file_path: str | None = None,
    task_id: str | None = None,
    *,
    home: Path | None = None,
    cwd: Path | None = None,
) -> str:
    del task_id
    located = _find_skill(name, home=home, cwd=cwd)
    if located is None:
        available = [skill.name for skill in discover_skills(home=home, cwd=cwd)[:20]]
        return json.dumps(
            {
                "success": False,
                "error": f"Skill '{name}' not found.",
                "available_skills": available,
                "hint": "Use skills_list to see all available skills",
            },
            ensure_ascii=False,
        )

    source, skill_dir, skill_md = located
    try:
        skill_name, description, frontmatter, content = _parse_skill_summary(skill_md)
    except UnicodeDecodeError:
        return json.dumps(
            {"success": False, "error": f"Skill file is not UTF-8 text: {skill_md}"},
            ensure_ascii=False,
        )

    if file_path:
        target, error = _load_support_file(skill_dir, file_path)
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        if target is None or not target.exists():
            return json.dumps(
                {"success": False, "error": f"Linked file '{file_path}' not found in skill '{name}'."},
                ensure_ascii=False,
            )
        try:
            file_content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return json.dumps(
                {"success": False, "error": f"Linked file is not UTF-8 text: {target}"},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "success": True,
                "name": skill_name,
                "description": description,
                "path": str(skill_md),
                "source": source,
                "category": _category_for(skill_dir, _find_root_for_path(skill_md, home=home, cwd=cwd) or skill_dir),
                "file": str(target.relative_to(skill_dir)).replace("\\", "/"),
                "content": file_content,
            },
            ensure_ascii=False,
        )

    linked_files = _linked_files(skill_dir)
    result: dict[str, Any] = {
        "success": True,
        "name": skill_name,
        "description": description,
        "content": content,
        "path": str(skill_md),
        "source": source,
        "category": None,
        "linked_files": linked_files or None,
        "usage_hint": (
            "To view linked files, call skill_view(name, file_path) where file_path is "
            "e.g. 'references/api.md' or 'assets/config.yaml'"
        )
        if linked_files
        else None,
    }
    root = _find_root_for_path(skill_md, home=home, cwd=cwd)
    if root is not None:
        result["category"] = _category_for(skill_dir, root)
    metadata = frontmatter.get("metadata")
    if isinstance(metadata, dict):
        result["metadata"] = metadata
    if isinstance(metadata, dict):
        io_metadata = metadata.get("io", {})
    else:
        io_metadata = {}
    tags = frontmatter.get("tags") or (
        io_metadata.get("tags") if isinstance(io_metadata, dict) else None
    )
    if tags:
        result["tags"] = tags
    related = frontmatter.get("related_skills") or (
        io_metadata.get("related_skills")
        if isinstance(io_metadata, dict)
        else None
    )
    if related:
        result["related_skills"] = related
    return json.dumps(result, ensure_ascii=False)


def skill_manage(
    action: str,
    name: str,
    content: str | None = None,
    category: str | None = None,
    file_path: str | None = None,
    file_content: str | None = None,
    old_string: str | None = None,
    new_string: str | None = None,
    replace_all: bool = False,
    *,
    home: Path | None = None,
    cwd: Path | None = None,
) -> str:
    normalized = action.strip().lower()
    resolved_home = ensure_io_home(home)

    if normalized == "create":
        error = _validate_skill_name(name)
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        if _find_skill(name, home=home, cwd=cwd) is not None:
            return json.dumps(
                {"success": False, "error": f"A skill named '{name}' already exists."},
                ensure_ascii=False,
            )
        if content is None:
            return json.dumps(
                {"success": False, "error": "content is required for 'create'."},
                ensure_ascii=False,
            )
        error = _validate_frontmatter(content)
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        skill_dir = resolved_home / "skills"
        if category:
            skill_dir = skill_dir / category
        skill_dir = skill_dir / name
        skill_dir.mkdir(parents=True, exist_ok=False)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(content, encoding="utf-8")
        return json.dumps(
            {
                "success": True,
                "action": "create",
                "name": name,
                "path": str(skill_md),
                "message": f"Skill '{name}' created.",
            },
            ensure_ascii=False,
        )

    located = _find_skill(name, home=home, cwd=cwd)
    if located is None:
        return json.dumps(
            {
                "success": False,
                "error": f"Skill '{name}' not found. Use skills_list() to see available skills.",
            },
            ensure_ascii=False,
        )
    _source, skill_dir, skill_md = located

    if normalized == "edit":
        if content is None:
            return json.dumps(
                {"success": False, "error": "content is required for 'edit'."},
                ensure_ascii=False,
            )
        error = _validate_frontmatter(content)
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        skill_md.write_text(content, encoding="utf-8")
        return json.dumps(
            {
                "success": True,
                "action": "edit",
                "name": name,
                "path": str(skill_md),
                "message": f"Skill '{name}' updated.",
            },
            ensure_ascii=False,
        )

    if normalized == "patch":
        if old_string is None or old_string == "":
            return json.dumps(
                {"success": False, "error": "old_string is required for 'patch'."},
                ensure_ascii=False,
            )
        if new_string is None:
            return json.dumps(
                {"success": False, "error": "new_string is required for 'patch'."},
                ensure_ascii=False,
            )
        target = skill_md
        if file_path:
            error = _validate_support_path(file_path)
            if error:
                return json.dumps({"success": False, "error": error}, ensure_ascii=False)
            target, error = _load_support_file(skill_dir, file_path)
            if error:
                return json.dumps({"success": False, "error": error}, ensure_ascii=False)
            if target is None or not target.exists():
                return json.dumps(
                    {"success": False, "error": f"Linked file '{file_path}' not found."},
                    ensure_ascii=False,
                )
        text = target.read_text(encoding="utf-8")
        occurrences = text.count(old_string)
        if occurrences == 0:
            return json.dumps(
                {"success": False, "error": "old_string was not found in the target file."},
                ensure_ascii=False,
            )
        if not replace_all and occurrences != 1:
            return json.dumps(
                {
                    "success": False,
                    "error": f"old_string matched {occurrences} times. Use replace_all=true or provide more context.",
                },
                ensure_ascii=False,
            )
        updated = text.replace(old_string, new_string, -1 if replace_all else 1)
        target.write_text(updated, encoding="utf-8")
        return json.dumps(
            {
                "success": True,
                "action": "patch",
                "name": name,
                "path": str(target),
                "replacements": occurrences if replace_all else 1,
            },
            ensure_ascii=False,
        )

    if normalized == "delete":
        shutil.rmtree(skill_dir)
        return json.dumps(
            {
                "success": True,
                "action": "delete",
                "name": name,
                "path": str(skill_dir),
                "message": f"Skill '{name}' deleted.",
            },
            ensure_ascii=False,
        )

    if normalized == "write_file":
        error = _validate_support_path(file_path or "")
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        if file_content is None:
            return json.dumps(
                {"success": False, "error": "file_content is required for 'write_file'."},
                ensure_ascii=False,
            )
        target, error = _load_support_file(skill_dir, file_path or "")
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        if target is None:
            return json.dumps({"success": False, "error": "Invalid file_path."}, ensure_ascii=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file_content, encoding="utf-8")
        return json.dumps(
            {
                "success": True,
                "action": "write_file",
                "name": name,
                "path": str(target),
                "message": f"Wrote {target.relative_to(skill_dir)}.",
            },
            ensure_ascii=False,
        )

    if normalized == "remove_file":
        error = _validate_support_path(file_path or "")
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        target, error = _load_support_file(skill_dir, file_path or "")
        if error:
            return json.dumps({"success": False, "error": error}, ensure_ascii=False)
        if target is None or not target.exists():
            return json.dumps(
                {"success": False, "error": f"Linked file '{file_path}' not found."},
                ensure_ascii=False,
            )
        target.unlink()
        return json.dumps(
            {
                "success": True,
                "action": "remove_file",
                "name": name,
                "path": str(target),
                "message": f"Removed {target.relative_to(skill_dir)}.",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "success": False,
            "error": (
                f"Unknown action '{action}'. Use: create, edit, patch, delete, "
                "write_file, remove_file"
            ),
        },
        ensure_ascii=False,
    )


SKILLS_LIST_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": "Optional category filter to narrow results",
        }
    },
    "required": [],
}


SKILL_VIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "The skill name or relative path (use skills_list to see available skills)",
        },
        "file_path": {
            "type": "string",
            "description": "Optional linked file within the skill, e.g. 'references/api.md'.",
        },
    },
    "required": ["name"],
}


SKILL_MANAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["create", "patch", "edit", "delete", "write_file", "remove_file"],
        },
        "name": {"type": "string"},
        "content": {"type": "string"},
        "old_string": {"type": "string"},
        "new_string": {"type": "string"},
        "replace_all": {"type": "boolean", "default": False},
        "category": {"type": "string"},
        "file_path": {"type": "string"},
        "file_content": {"type": "string"},
    },
    "required": ["action", "name"],
}


class SkillsListTool(Tool):
    name = "skills_list"
    description = (
        "List available skills (name + description). Use skill_view(name) to load full content."
    )
    input_schema = SKILLS_LIST_SCHEMA

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        payload = skills_list(
            category=str(arguments.get("category") or "").strip() or None,
            home=context.home,
            cwd=context.cwd,
        )
        return ToolResult(content=payload)


class SkillViewTool(Tool):
    name = "skill_view"
    description = (
        "Load a skill's full content or one of its linked files (references, templates, scripts, assets)."
    )
    input_schema = SKILL_VIEW_SCHEMA

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        payload = skill_view(
            str(arguments.get("name", "")),
            file_path=str(arguments.get("file_path") or "").strip() or None,
            home=context.home,
            cwd=context.cwd,
        )
        result = json.loads(payload)
        return ToolResult(content=payload, is_error=not bool(result.get("success")))


class SkillManageTool(Tool):
    name = "skill_manage"
    description = (
        "Manage skills (create, patch, edit, delete, write_file, remove_file). "
        "New skills are stored under ~/.io/skills/."
    )
    input_schema = SKILL_MANAGE_SCHEMA
    never_parallel = True

    def approval_reason(self, arguments: dict[str, object]) -> str | None:
        action = str(arguments.get("action", "")).strip().lower()
        if action in {"delete", "remove_file"}:
            return f"Skill management action '{action}' mutates or removes skill files."
        return None

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        payload = skill_manage(
            action=str(arguments.get("action", "")),
            name=str(arguments.get("name", "")),
            content=arguments.get("content") if isinstance(arguments.get("content"), str) else None,
            category=arguments.get("category") if isinstance(arguments.get("category"), str) else None,
            file_path=arguments.get("file_path") if isinstance(arguments.get("file_path"), str) else None,
            file_content=arguments.get("file_content") if isinstance(arguments.get("file_content"), str) else None,
            old_string=arguments.get("old_string") if isinstance(arguments.get("old_string"), str) else None,
            new_string=arguments.get("new_string") if isinstance(arguments.get("new_string"), str) else None,
            replace_all=bool(arguments.get("replace_all", False)),
            home=context.home,
            cwd=context.cwd,
        )
        result = json.loads(payload)
        return ToolResult(content=payload, is_error=not bool(result.get("success")))


GLOBAL_TOOL_REGISTRY.register(SkillsListTool())
GLOBAL_TOOL_REGISTRY.register(SkillViewTool())
GLOBAL_TOOL_REGISTRY.register(SkillManageTool())
