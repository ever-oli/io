"""Parity checks vs Nuggets TypeScript (github.com/NeoVertex1/nuggets).

Golden values for PRNG and fuzzy ratios are produced by the upstream algorithms;
see ``docs/nuggets_parity.md`` for regeneration notes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pytest

from io_cli.nuggets.hrr_core import mulberry32, seed_from_name
from io_cli.nuggets.memory import Nugget
from io_cli.nuggets.nuggets_fuzzy import sequence_match_ratio
from io_cli.nuggets.promote import MEMORY_HEADER, promote_facts
from io_cli.nuggets.shelf import NuggetShelf


def test_seed_from_name_and_mulberry32_match_ts_golden() -> None:
    """First 8 outputs for ``seedFromName('golden')`` — verified against Node (Nuggets core)."""
    seed = seed_from_name("golden")
    assert seed == 1684828007
    rng = mulberry32(seed)
    got = [rng() for _ in range(8)]
    want = [
        0.5733123274985701,
        0.13999683409929276,
        0.8826770391315222,
        0.3016311794053763,
        0.15975603857077658,
        0.25157642154954374,
        0.31447811401449144,
        0.7645705668255687,
    ]
    assert got == want


@pytest.mark.parametrize(
    ("a", "b", "want"),
    [
        ("hello", "helo", 8 / 9),
        ("foo", "foo", 1.0),
        ("", "", 1.0),
        ("a", "abc", 0.5),
    ],
)
def test_sequence_match_ratio_matches_ts(a: str, b: str, want: float) -> None:
    assert sequence_match_ratio(a, b) == pytest.approx(want)


def test_fuzzy_differs_from_python_sequencematcher() -> None:
    """Nuggets greedy block matcher diverges from ``difflib`` on many pairs (e.g. random search)."""
    a, b = "vozppl", "pkohee"
    nug = sequence_match_ratio(a, b)
    sm = SequenceMatcher(None, a, b).ratio()
    assert nug == pytest.approx(1.0 / 3.0)
    assert sm == pytest.approx(1.0 / 6.0)
    assert nug != pytest.approx(sm)


def test_status_capacity_rounding_matches_js_math_round(tmp_path: Path) -> None:
    """``Math.round(usedPct * 10) / 10`` for positive values (Nuggets ``status()``)."""
    n = Nugget("s", d=100, banks=1, auto_save=False, save_dir=tmp_path)
    # 3 facts, cap_est = 1 * floor(sqrt(100)) = 10 -> 30.0%
    for i in range(3):
        n.remember(f"k{i}", "v")
    st = n.status()
    assert st["capacity_used_pct"] == 30.0


def test_promote_memory_md_header_matches_nuggets_copy() -> None:
    assert "Auto-promoted from nuggets (3+ recalls across sessions)" in MEMORY_HEADER
    assert "holographic" not in MEMORY_HEADER


def test_promote_render_matches_expected_shape(tmp_path: Path) -> None:
    shelf = NuggetShelf(save_dir=tmp_path / "n", auto_save=True)
    shelf.create("learnings", d=32, banks=2)
    shelf.remember("learnings", "stack", "python")
    for sid in ("s1", "s2", "s3"):
        shelf.recall("stack", nugget_name="learnings", session_id=sid)
    promote_facts(shelf, memories_dir=tmp_path / "m")
    text = (tmp_path / "m" / "MEMORY.md").read_text(encoding="utf-8")
    assert text == (
        "# Memory\n\nAuto-promoted from nuggets (3+ recalls across sessions).\n\n"
        "## learnings\n\n"
        "- **stack**: python\n"
    )


def test_rebuild_memory_bit_identical_python_to_python(tmp_path: Path) -> None:
    """Same code path twice → identical float arrays (internal reproducibility)."""
    n = Nugget("parity", d=32, banks=1, ensembles=1, auto_save=False, save_dir=tmp_path)
    n.remember("k", "v")
    n._rebuild()
    re1 = np.array(n._E[0].banks[0].memory[0], dtype=np.float64, copy=True)
    n._dirty = True
    n._rebuild()
    re2 = n._E[0].banks[0].memory[0]
    assert np.array_equal(re1, re2)


def test_memory_re_head_matches_committed_golden_d32(tmp_path: Path) -> None:
    """Locks Python hologram head for the standard D=32 parity trace."""
    golden_path = Path(__file__).resolve().parent / "fixtures" / "nuggets" / "memory_re_head_d32_parity.json"
    want = json.loads(golden_path.read_text(encoding="utf-8"))
    n = Nugget("parity", d=32, banks=1, ensembles=1, auto_save=False, save_dir=tmp_path)
    n.remember("k", "v")
    n._rebuild()
    got = [float(x) for x in n._E[0].banks[0].memory[0][:8]]
    assert got == want


@pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")
def test_memory_re_head_matches_standalone_ts_within_ulp(tmp_path: Path) -> None:
    """Cross-runtime: Nuggets-algorithm JS mirror vs NumPy (see ts_rebuild_d32_one_fact.mjs)."""
    script = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "nuggets"
        / "ts_rebuild_d32_one_fact.mjs"
    )
    out = subprocess.check_output(["node", str(script)], text=True).strip()
    ts_head = json.loads(out)
    n = Nugget("parity", d=32, banks=1, ensembles=1, auto_save=False, save_dir=tmp_path)
    n.remember("k", "v")
    n._rebuild()
    py_head = np.array([float(x) for x in n._E[0].banks[0].memory[0][:8]], dtype=np.float64)
    assert np.allclose(py_head, np.array(ts_head, dtype=np.float64), rtol=0.0, atol=5e-15)


def test_fuzzy_threshold_borderline_key_resolution(tmp_path: Path) -> None:
    """Threshold 0.55: pick key only if Nuggets-style ratio >= 0.55."""
    n = Nugget("t", d=128, banks=2, auto_save=False, save_dir=tmp_path)
    n.remember("my_long_key_name", "value_a")
    # Craft query so ratio is below 0.55 under Nuggets matcher (no exact/substring hit)
    r = n.recall("zzz_unrelated_query_zzz")
    assert r["found"] is False
