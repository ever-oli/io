"""Text sanitation helpers for model-bound tool output."""

from __future__ import annotations

import re

# CSI sequences: ESC [ ... command
_ANSI_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
# OSC sequences: ESC ] ... (BEL or ST)
_ANSI_OSC_RE = re.compile(r"\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)")
# Single-char escape sequences.
_ANSI_ESC_RE = re.compile(r"\x1B[@-_]")


def strip_ansi(text: str) -> str:
    """Remove ANSI/terminal control sequences from text."""
    if not text:
        return text
    out = _ANSI_CSI_RE.sub("", text)
    out = _ANSI_OSC_RE.sub("", out)
    out = _ANSI_ESC_RE.sub("", out)
    return out
