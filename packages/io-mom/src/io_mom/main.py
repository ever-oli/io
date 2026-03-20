"""Slack-oriented runtime wrapper for IO Mom."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from io_cli.main import format_prompt_result, run_prompt
from io_cli.gateway import GatewayManager
from io_cli.gateway_models import Platform
from io_cli.gateway_session import SessionSource, build_session_context_prompt
from io_cli.toolsets import enabled_toolsets_for_platform


@dataclass(slots=True)
class Workspace:
    channel_id: str
    cwd: Path
    home: Path | None = None
    channel_name: str = "local"
    user_id: str = "local-user"
    user_name: str = "Local User"
    is_dm: bool = False


@dataclass(slots=True)
class SlackBotService:
    workspace: Workspace

    async def handle_message(self, text: str) -> str:
        manager = GatewayManager(home=self.workspace.home)
        context = manager.build_session_context(
            SessionSource(
                platform=Platform.SLACK,
                chat_id=self.workspace.channel_id,
                chat_name=self.workspace.channel_name,
                chat_type="dm" if self.workspace.is_dm else "channel",
                user_id=self.workspace.user_id,
                user_name=self.workspace.user_name,
            )
        )
        toolsets = enabled_toolsets_for_platform({}, platform="slack") or ["io-slack"]
        result = await run_prompt(
            text,
            cwd=self.workspace.cwd,
            home=self.workspace.home,
            toolsets=toolsets,
            system_prompt_suffix=build_session_context_prompt(context),
            session_source="mom",
        )
        return format_prompt_result(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mom", description="IO Slack/workspace runtime")
    parser.add_argument("prompt", nargs="?", default="hello from mom")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--home", type=Path, default=None)
    parser.add_argument("--channel-id", default="local")
    parser.add_argument("--channel-name", default="local")
    parser.add_argument("--user-id", default="local-user")
    parser.add_argument("--user-name", default="Local User")
    parser.add_argument("--dm", action="store_true")
    args = parser.parse_args(argv)
    service = SlackBotService(
        workspace=Workspace(
            channel_id=args.channel_id,
            cwd=args.cwd,
            home=args.home,
            channel_name=args.channel_name,
            user_id=args.user_id,
            user_name=args.user_name,
            is_dm=args.dm,
        )
    )
    print(asyncio.run(service.handle_message(args.prompt)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
