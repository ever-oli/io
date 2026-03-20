"""Slack/workspace scaffold for IO Mom."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from io_cli.main import format_prompt_result, run_prompt


@dataclass(slots=True)
class Workspace:
    channel_id: str
    cwd: Path


@dataclass(slots=True)
class SlackBotService:
    workspace: Workspace

    async def handle_message(self, text: str) -> str:
        result = await run_prompt(text, cwd=self.workspace.cwd)
        return format_prompt_result(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mom", description="IO Slack/workspace scaffold")
    parser.add_argument("prompt", nargs="?", default="hello from mom")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    service = SlackBotService(workspace=Workspace(channel_id="local", cwd=args.cwd))
    print(asyncio.run(service.handle_message(args.prompt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

