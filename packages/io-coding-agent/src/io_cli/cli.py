"""Command-line entry point for IO."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from io_tui import TerminalUI

from .doctor import doctor_report
from .main import build_theme, format_prompt_result, run_prompt
from .models import list_models
from .session import SessionManager


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="io", description="IO Agent coding CLI")
    subparsers = parser.add_subparsers(dest="command")

    ask = subparsers.add_parser("ask", help="Run a single prompt")
    ask.add_argument("prompt", help="Prompt to send to the agent")
    ask.add_argument("--model", help="Override model id")
    ask.add_argument("--provider", help="Override provider")
    ask.add_argument("--base-url", help="Override provider base URL")
    ask.add_argument("--cwd", type=Path, help="Workspace path", default=Path.cwd())
    ask.add_argument("--session", type=Path, help="Use a specific session file")
    ask.add_argument("--toolset", action="append", dest="toolsets", help="Toolset to enable")
    ask.add_argument("--json", action="store_true", help="Emit JSON output")
    ask.add_argument("--no-extensions", action="store_true", help="Skip loading extensions")

    subparsers.add_parser("models", help="List known models")

    sessions = subparsers.add_parser("sessions", help="List session files for the current cwd")
    sessions.add_argument("--cwd", type=Path, default=Path.cwd())

    search = subparsers.add_parser("search-sessions", help="Search indexed session history")
    search.add_argument("query")
    search.add_argument("--cwd", type=Path, default=Path.cwd())

    doctor = subparsers.add_parser("doctor", help="Print a diagnostic report")
    doctor.add_argument("--cwd", type=Path, default=Path.cwd())

    repl = subparsers.add_parser("repl", help="Start an interactive prompt loop")
    repl.add_argument("--model", help="Override model id")
    repl.add_argument("--provider", help="Override provider")
    repl.add_argument("--cwd", type=Path, help="Workspace path", default=Path.cwd())
    repl.add_argument("--no-extensions", action="store_true", help="Skip loading extensions")

    return parser


def _run_repl(args: argparse.Namespace) -> int:
    ui = TerminalUI(theme=build_theme())
    ui.render_banner()
    while True:
        try:
            prompt = ui.prompt()
        except (EOFError, KeyboardInterrupt):
            break
        if not prompt.strip():
            continue
        if prompt.strip() in {"/quit", "/exit"}:
            break
        result = asyncio.run(
            run_prompt(
                prompt,
                cwd=args.cwd,
                model=args.model,
                provider=args.provider,
                load_extensions=not args.no_extensions,
            )
        )
        ui.render_message("assistant", format_prompt_result(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ask":
        result = asyncio.run(
            run_prompt(
                args.prompt,
                cwd=args.cwd,
                model=args.model,
                provider=args.provider,
                base_url=args.base_url,
                session_path=args.session,
                toolsets=args.toolsets,
                load_extensions=not args.no_extensions,
            )
        )
        print(format_prompt_result(result, as_json=args.json))
        return 0

    if args.command == "models":
        for model in list_models():
            print(model)
        return 0

    if args.command == "sessions":
        for path in SessionManager.list_for_cwd(args.cwd):
            print(path)
        return 0

    if args.command == "search-sessions":
        result = asyncio.run(
            run_prompt(
                f"TOOL[session_search] {json.dumps({'query': args.query, 'limit': 10})}",
                cwd=args.cwd,
                model="mock/io-test",
                provider="mock",
                toolsets=["safe"],
            )
        )
        print(format_prompt_result(result))
        return 0

    if args.command == "doctor":
        print(json.dumps(doctor_report(cwd=args.cwd), indent=2, sort_keys=True))
        return 0

    if args.command == "repl":
        return _run_repl(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

