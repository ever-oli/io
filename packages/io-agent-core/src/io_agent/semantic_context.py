"""Lightweight semantic context and repo-map helpers.

This is intentionally simple (token-overlap scoring) as a first parity step.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_TOKEN_RE = re.compile(r"[a-zA-Z0-9_]{2,}")
_SKIP_DIRS = {".git", ".hg", ".svn", "node_modules", ".venv", "__pycache__", ".mypy_cache"}
_TEXT_EXTS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".cpp",
    ".h",
}


def _tokenize(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text or "")}


@dataclass(slots=True)
class SemanticHit:
    path: Path
    score: float
    preview: str


def _iter_text_files(root: Path, *, max_files: int = 800) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() not in _TEXT_EXTS:
                continue
            out.append(p)
            if len(out) >= max_files:
                return out
    return out


def semantic_search(
    query: str,
    *,
    root: Path,
    max_hits: int = 5,
    max_file_chars: int = 12000,
) -> list[SemanticHit]:
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    hits: list[SemanticHit] = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        text = text[:max_file_chars]
        tokens = _tokenize(text)
        if not tokens:
            continue
        overlap = q_tokens.intersection(tokens)
        if not overlap:
            continue
        score = float(len(overlap)) / float(len(q_tokens))
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
        hits.append(SemanticHit(path=path, score=score, preview=first_line[:180]))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:max_hits]


def build_repo_map(*, root: Path, max_entries: int = 30) -> list[str]:
    rows: list[tuple[int, str]] = []
    for path in _iter_text_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        weight = len(text)
        if path.suffix == ".py":
            weight += text.count("def ") * 20 + text.count("class ") * 40 + text.count("import ") * 10
        rel = str(path.relative_to(root))
        rows.append((weight, rel))
    rows.sort(key=lambda t: t[0], reverse=True)
    return [rel for _w, rel in rows[:max_entries]]

