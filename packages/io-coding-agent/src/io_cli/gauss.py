"""OpenGauss CLI bridge — subprocess passthrough to gauss / gauss-agent.

Run Gauss beside IO::

    io gauss chat
    io gauss gateway run
    io gauss --help

Requires: pip install gauss-agent (or uv add gauss-agent). Config: gauss.bin, gauss.enabled.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _gauss_section(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("gauss")
    return raw if isinstance(raw, dict) else {}


def resolve_gauss_bin(config: dict[str, Any], home: Path | None) -> str | None:
    """Resolve gauss executable: config gauss.bin, then PATH, then ~/.io/bin/gauss."""
    gcfg = _gauss_section(config)
    bin_name = str(gcfg.get("bin", "gauss")).strip()
    if not bin_name:
        bin_name = "gauss"

    resolved = shutil.which(bin_name)
    if resolved:
        return resolved
    if home:
        candidate = home / "bin" / os.path.basename(bin_name.split()[0])
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def run_gauss_passthrough(argv: list[str], *, config: dict[str, Any], home: Path | None) -> int:
    """Run gauss with argv. Returns exit code. Passes stdin/stdout/stderr through."""
    gcfg = _gauss_section(config)
    if gcfg.get("enabled") is False:
        print(
            "gauss is disabled (gauss.enabled: false). Enable in config to run.",
            file=sys.stderr,
        )
        return 1

    resolved = resolve_gauss_bin(config, home)
    if not resolved:
        print(
            "gauss not found. Install: pip install gauss-agent (or uv add gauss-agent). "
            "Set gauss.bin in config if using a different command.",
            file=sys.stderr,
        )
        return 127

    full_argv = [resolved] + argv
    proc = subprocess.run(full_argv)
    return proc.returncode if proc.returncode is not None else 0
