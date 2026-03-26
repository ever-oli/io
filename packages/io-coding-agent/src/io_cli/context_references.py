"""Expand safe ``@path`` references in user prompts."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

_AT_REF_RE = re.compile(r"(?<!\S)@([^\s]+)")
_BLOCKED_PARTS = {".git", ".svn", ".hg", "node_modules", ".venv", "__pycache__"}


def _is_within(base: Path, child: Path) -> bool:
    try:
        child.relative_to(base)
        return True
    except ValueError:
        return False


def expand_at_references(
    text: str,
    *,
    cwd: Path,
    max_files: int = 8,
    max_chars_per_file: int = 8000,
    max_total_chars: int = 32000,
) -> str:
    """Expand ``@path`` tokens into inline context blocks.

    Security policy:
    - only files under ``cwd`` are allowed
    - directories are ignored
    - unreadable/non-text files are ignored
    """
    refs: list[str] = [m.group(1) for m in _AT_REF_RE.finditer(text or "")]
    # Also support quoted @refs with spaces, e.g. @"docs/notes today.md"
    try:
        for token in shlex.split(text or ""):
            if token.startswith("@"):
                refs.append(token[1:])
    except ValueError:
        # Keep regex-only extraction on malformed quoting.
        pass
    if not refs:
        return text

    seen: set[str] = set()
    blocks: list[str] = []
    total = 0
    skipped: list[str] = []
    for raw in refs:
        if len(blocks) >= max_files:
            break
        token = raw.strip().strip("\"'`")
        if not token:
            continue
        path = Path(token).expanduser()
        if not path.is_absolute():
            path = (cwd / path).resolve()
        else:
            path = path.resolve()
        if not _is_within(cwd, path):
            skipped.append(f"@{token}: outside cwd")
            continue
        if not path.exists() or not path.is_file():
            skipped.append(f"@{token}: not a file")
            continue
        if any(part in _BLOCKED_PARTS for part in path.parts):
            skipped.append(f"@{token}: blocked path")
            continue
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped.append(f"@{token}: unreadable as utf-8 text")
            continue
        if len(content) > max_chars_per_file:
            content = content[:max_chars_per_file] + "\n... [truncated]"
        if total + len(content) > max_total_chars:
            skipped.append(f"@{token}: total reference budget exceeded")
            continue
        total += len(content)
        rel = str(path.relative_to(cwd))
        blocks.append(f"BEGIN @{rel}\n{content}\nEND @{rel}")

    if not blocks:
        return text
    out = f"{text.rstrip()}\n\n" + "\n\n".join(blocks)
    if skipped:
        out += "\n\nIgnored @refs:\n- " + "\n- ".join(skipped[:12])
    return out

