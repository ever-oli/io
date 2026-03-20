"""CLI entry point for the IO ACP adapter."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path


def _setup_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def _load_env() -> None:
    from ..config import ensure_io_home, load_env

    io_home = ensure_io_home(Path(os.getenv("IO_HOME", Path.home() / ".io")))
    loaded = load_env(io_home)
    for key, value in loaded.items():
        os.environ.setdefault(key, value)


def main() -> None:
    _setup_logging()
    _load_env()
    logger = logging.getLogger(__name__)
    logger.info("Starting IO ACP adapter")

    import acp

    from .server import IOACPAgent

    agent = IOACPAgent()
    try:
        asyncio.run(acp.run_agent(agent))
    except KeyboardInterrupt:
        logger.info("Shutting down (KeyboardInterrupt)")
    except Exception:
        logger.exception("ACP agent crashed")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
