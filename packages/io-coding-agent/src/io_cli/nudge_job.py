"""Optional periodic memory nudge (gateway tick); disabled by default."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any


def maybe_run_periodic_nudge(home: Path, config: dict[str, Any]) -> None:
    """If nuggets.periodic_nudge.enabled, run at most once per interval_hours via `io ask` subprocess."""
    nug = config.get("nuggets")
    if not isinstance(nug, dict):
        return
    sec = nug.get("periodic_nudge")
    if not isinstance(sec, dict) or not sec.get("enabled"):
        return
    interval = float(sec.get("interval_hours", 24) or 24)
    interval = max(1.0, interval)
    marker = home / "state" / "last_periodic_nudge"
    marker.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if marker.exists():
        try:
            last = float(marker.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            last = 0.0
        if now - last < interval * 3600.0:
            return
    prompt = str(
        sec.get("prompt")
        or "Summarize recent work as 3–7 bullets suitable for ~/.io/memories/MEMORY.md; do not run destructive tools."
    )
    model = str(sec.get("model") or "mock/io-test")
    provider = str(sec.get("provider") or "mock")
    env = {**os.environ, "IO_HOME": str(home)}
    try:
        subprocess.run(
            ["io", "ask", prompt, "--model", model, "--provider", provider, "--no-extensions"],
            env=env,
            cwd=str(home),
            check=False,
            timeout=int(sec.get("timeout_sec", 300) or 300),
        )
    except Exception:
        return
    try:
        marker.write_text(str(now), encoding="utf-8")
    except OSError:
        pass
