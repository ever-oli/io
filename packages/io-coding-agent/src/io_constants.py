"""IO constants and path utilities."""

from __future__ import annotations

import os
from pathlib import Path


def get_io_home() -> Path:
    """Get the IO home directory (renamed from get_hermes_home for compatibility)."""
    if home := os.environ.get("IO_HOME"):
        return Path(home)
    return Path.home() / ".io"


# Alias for backward compatibility
get_hermes_home = get_io_home


# Default paths
DEFAULT_CONFIG_PATH = get_io_home() / "config.yaml"
DEFAULT_SESSIONS_DIR = get_io_home() / "sessions"
DEFAULT_SKILLS_DIR = get_io_home() / "skills"
DEFAULT_NUGGETS_PATH = get_io_home() / "nuggets"

# Version info
VERSION = "0.3.0"
RELEASE_DATE = "2024"
