"""Smoke tests for Nuggets-style HRR memory (small D for speed)."""

from __future__ import annotations

from pathlib import Path

from io_cli.nuggets.memory import Nugget
from io_cli.nuggets.promote import promote_facts
from io_cli.nuggets.shelf import NuggetShelf


def test_nugget_remember_recall_small_d(tmp_path: Path) -> None:
    n = Nugget(
        "test",
        d=512,
        banks=2,
        ensembles=1,
        auto_save=False,
        save_dir=tmp_path,
    )
    n.remember("favorite_color", "blue")
    r = n.recall("favorite_color", session_id="")
    assert r["found"] is True
    assert r["answer"] == "blue"
    assert r["confidence"] > 0.0


def test_nugget_save_load_roundtrip(tmp_path: Path) -> None:
    n = Nugget(
        "roundtrip",
        d=256,
        banks=2,
        auto_save=True,
        save_dir=tmp_path,
    )
    n.remember("city", "Paris")
    path = tmp_path / "roundtrip.nugget.json"
    assert path.exists()
    n2 = Nugget.load(path, auto_save=False)
    r = n2.recall("city")
    assert r["found"] is True
    assert r["answer"] == "Paris"


def test_promote_facts_writes_memory_md(tmp_path: Path) -> None:
    save = tmp_path / "nuggets"
    memories = tmp_path / "memories"
    shelf = NuggetShelf(save_dir=save, auto_save=True)
    shelf.create("learnings", d=256, banks=2)
    shelf.remember("learnings", "stack", "python")
    for sid in ("s1", "s2", "s3"):
        shelf.recall("stack", nugget_name="learnings", session_id=sid)
    n = promote_facts(shelf, memories_dir=memories)
    assert n >= 1
    md = (memories / "MEMORY.md").read_text(encoding="utf-8")
    assert "learnings" in md
    assert "stack" in md
    assert "python" in md
