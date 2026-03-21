"""Promote high-recall nugget facts into IO `memories/MEMORY.md` (inspired by Nuggets `promote.ts`, MIT)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .shelf import NuggetShelf

PROMOTE_THRESHOLD = 3
# Byte-for-byte intent: same as Nuggets `promote.ts` MEMORY_MD_HEADER (IO path differs; text matches).
MEMORY_HEADER = """# Memory

Auto-promoted from nuggets (3+ recalls across sessions).
"""


def _parse_memory_md(content: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current = ""
    for line in content.splitlines():
        stripped = line.strip()
        m = re.match(r"^##\s+(.+)$", stripped)
        if m:
            current = m.group(1).strip()
            sections.setdefault(current, {})
            continue
        fm = re.match(r"^-\s+\*\*(.+?)\*\*:\s*(.+)$", stripped)
        if fm and current:
            sections[current][fm.group(1).strip()] = fm.group(2).strip()
    return sections


def _render_memory_md(sections: dict[str, dict[str, str]]) -> str:
    """Match Nuggets ``renderMemoryMd`` join layout (``promote.ts``)."""
    if not sections:
        return MEMORY_HEADER
    priority = ["learnings", "preferences"]
    ordered: list[str] = [p for p in priority if p in sections]
    ordered.extend(sorted(k for k in sections if k not in priority))
    lines: list[str] = [MEMORY_HEADER]
    for section_name in ordered:
        facts = sections[section_name]
        entries = list(facts.items())
        if not entries:
            continue
        lines.append(f"## {section_name}\n")
        for key, value in entries:
            lines.append(f"- **{key}**: {value}")
        lines.append("")
    return "\n".join(lines)


def promote_facts(shelf: NuggetShelf, *, memories_dir: Path) -> int:
    """Merge facts with hits >= threshold into memories/MEMORY.md. Returns count of new keys."""
    candidates: list[tuple[str, str, str]] = []
    for info in shelf.list():
        name = str(info["name"])
        try:
            nugget = shelf.get(name)
            for fact in nugget.facts():
                if int(fact.get("hits") or 0) >= PROMOTE_THRESHOLD:
                    candidates.append((name, str(fact["key"]), str(fact["value"])))
        except ValueError:
            continue
    if not candidates:
        return 0
    memories_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memories_dir / "MEMORY.md"
    existing = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    sections = _parse_memory_md(existing) if existing.strip() else {}
    new_count = 0
    for nugget_name, key, value in candidates:
        sections.setdefault(nugget_name, {})
        if sections[nugget_name].get(key) != value:
            if key not in sections[nugget_name]:
                new_count += 1
            sections[nugget_name][key] = value
    content = _render_memory_md(sections)
    tmp = memory_path.with_suffix(".md.tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(memory_path)
    return new_count
