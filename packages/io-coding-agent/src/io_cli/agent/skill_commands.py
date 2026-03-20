"""Hermes-style slash skill expansion: `/slug [args]` → user message with full SKILL.md.

Matches the user-guide contract: every discovered skill is a slash command; the model
receives the skill document inline for that turn (same idea as webhook skill injection).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..skills import skill_command_slug, skill_slash_command_map

# Avoid blowing context on enormous skills; remainder still has path for skill_view.
_MAX_SKILL_BODY_CHARS = 256_000


def _normalize_slash_key(key: str) -> str:
    k = key.strip()
    if not k.startswith("/"):
        k = "/" + k
    rest = k[1:].replace("_", "-").lower()
    return f"/{rest}"


def get_skill_commands(
    *,
    home: Path | None = None,
    cwd: Path | None = None,
    platform: str | None = "cli",
) -> dict[str, dict[str, Any]]:
    """Slash keys (``/slug``) → metadata; same registry as REPL completion."""
    return skill_slash_command_map(home=home, cwd=cwd, platform=platform)


def _resolve_slash_key(
    token: str,
    mapping: dict[str, dict[str, Any]],
) -> str | None:
    """Map route token or user input to a canonical ``/slug`` present in *mapping*."""
    n = _normalize_slash_key(token)
    if n in mapping:
        return n
    bare = token.strip().lstrip("/").replace("_", "-").lower()
    key = f"/{bare}"
    if key in mapping:
        return key
    for k, meta in mapping.items():
        skill_name = str(meta.get("skill_name") or "")
        if skill_name and skill_command_slug(skill_name) == bare:
            return k
    return None


def build_skill_invocation_message(
    slash_key: str,
    *,
    user_instruction: str = "",
    home: Path | None = None,
    cwd: Path | None = None,
    platform: str | None = "cli",
) -> str | None:
    """Return expanded user text for the agent, or ``None`` if *slash_key* is not a skill."""
    mapping = get_skill_commands(home=home, cwd=cwd, platform=platform)
    canon = _resolve_slash_key(slash_key, mapping)
    if canon is None:
        return None
    info = mapping[canon]
    path = Path(str(info["path"]))
    skill_name = str(info.get("skill_name") or canon.lstrip("/"))
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    truncated = ""
    body = raw
    if len(body) > _MAX_SKILL_BODY_CHARS:
        body = body[:_MAX_SKILL_BODY_CHARS]
        truncated = (
            f"\n\n[Truncated SKILL.md to {_MAX_SKILL_BODY_CHARS} characters; "
            f"use skill_view(\"{skill_name}\") for the rest.]\n"
        )

    slug = canon.lstrip("/")
    args = user_instruction.strip()
    if args:
        user_block = args
    else:
        user_block = (
            "(No additional text after the slash command. Follow this skill’s guidance; "
            "if the user’s intent is unclear, ask briefly what they want.)"
        )

    return (
        f"The user invoked the skill **{skill_name}** via `/{slug}`.\n\n"
        "The full SKILL.md for this skill is included below. Treat it as authoritative for "
        "this turn; use `skill_view` only if you need a linked reference file under this skill.\n\n"
        f"--- BEGIN SKILL.md ({path}) ---\n{body}{truncated}"
        f"--- END SKILL.md ---\n\n### User request\n{user_block}"
    )
