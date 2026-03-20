"""Command-line entry point for IO."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

import yaml

from io_tui import TerminalUI

from .banner import build_welcome_banner, prefetch_update_check
from .commands import COMMANDS_BY_CATEGORY
from .cron import CronManager
from .doctor import doctor_report
from .config import ensure_io_home, get_config_value, load_config, load_env, save_config, set_config_value
from .gateway import GatewayManager
from .gateway_runner import run_gateway
from .main import build_theme, format_prompt_result, run_prompt
from .models import list_models
from .pairing import pairing_command
from .skills import discover_skills, inspect_skill, save_skill_toggle, search_skills
from .session import SessionManager
from .status import render_status_text, status_report
from .toolsets import enabled_tools_for_platform, set_toolset_enabled, toolsets_status
from .tools_config import toolsets_command
from .tools.registry import get_tool_registry
from io_agent import resolve_runtime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="io", description="IO coding agent by Most Wanted Research")
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

    models = subparsers.add_parser("models", help="List known models")
    models.add_argument("--provider", help="Filter to a provider")
    models.add_argument("--verbose", action="store_true", help="Include metadata")

    sessions = subparsers.add_parser("sessions", help="Manage session files")
    sessions.add_argument("--cwd", type=Path, default=Path.cwd())
    sessions_subparsers = sessions.add_subparsers(dest="sessions_command")
    sessions_subparsers.add_parser("list", help="List session files for the current cwd")
    sessions_show = sessions_subparsers.add_parser("show", help="Show session metadata")
    sessions_show.add_argument("session_file", type=Path)
    sessions_tree = sessions_subparsers.add_parser("tree", help="Render a session branch tree")
    sessions_tree.add_argument("session_file", type=Path)
    sessions_delete = sessions_subparsers.add_parser("delete", help="Delete a session file")
    sessions_delete.add_argument("session_file", type=Path)

    search = subparsers.add_parser("search-sessions", help="Search indexed session history")
    search.add_argument("query")
    search.add_argument("--cwd", type=Path, default=Path.cwd())

    doctor = subparsers.add_parser("doctor", help="Print a diagnostic report")
    doctor.add_argument("--cwd", type=Path, default=Path.cwd())

    status = subparsers.add_parser("status", help="Show runtime and auth status")
    status.add_argument("--pretty", action="store_true", help="Render a IO-style text status view")
    status.add_argument("--all", action="store_true", help="Show full secrets in pretty mode")

    setup = subparsers.add_parser("setup", help="Bootstrap ~/.io and print the home path")
    setup.add_argument("--home", type=Path, help="Override IO home directory")

    auth = subparsers.add_parser("auth", help="Inspect provider auth state")
    auth_subparsers = auth.add_subparsers(dest="auth_command")
    auth_subparsers.add_parser("status", help="Show auth status")

    config = subparsers.add_parser("config", help="Inspect or change config")
    config_subparsers = config.add_subparsers(dest="config_command")
    config_subparsers.add_parser("show", help="Show merged config")
    config_get = config_subparsers.add_parser("get", help="Read one config value")
    config_get.add_argument("path", help="Dot path, e.g. model.default")
    config_set = config_subparsers.add_parser("set", help="Write one config value")
    config_set.add_argument("path", help="Dot path, e.g. display.streaming")
    config_set.add_argument("value", help="YAML scalar/object value")

    tools = subparsers.add_parser("tools", help="Inspect or configure enabled toolsets")
    tools_subparsers = tools.add_subparsers(dest="tools_command")
    tools_list = tools_subparsers.add_parser("list", help="List enabled toolsets and tools")
    tools_list.add_argument("--platform", default="cli")
    tools_enable = tools_subparsers.add_parser("enable", help="Enable a toolset for a platform")
    tools_enable.add_argument("toolset")
    tools_enable.add_argument("--platform", default="cli")
    tools_disable = tools_subparsers.add_parser("disable", help="Disable a toolset for a platform")
    tools_disable.add_argument("toolset")
    tools_disable.add_argument("--platform", default="cli")

    subparsers.add_parser("toolsets", help="List toolsets using the IO-style compatibility view")

    skills = subparsers.add_parser("skills", help="Discover and configure skills")
    skills_subparsers = skills.add_subparsers(dest="skills_command")
    skills_list = skills_subparsers.add_parser("list", help="List discovered skills")
    skills_list.add_argument("--platform", default="cli")
    skills_list.add_argument("--cwd", type=Path, default=Path.cwd())
    skills_search = skills_subparsers.add_parser("search", help="Search discovered skills")
    skills_search.add_argument("query")
    skills_search.add_argument("--platform", default="cli")
    skills_search.add_argument("--cwd", type=Path, default=Path.cwd())
    skills_inspect = skills_subparsers.add_parser("inspect", help="Print the SKILL.md for one skill")
    skills_inspect.add_argument("name")
    skills_inspect.add_argument("--platform", default="cli")
    skills_inspect.add_argument("--cwd", type=Path, default=Path.cwd())
    skills_enable = skills_subparsers.add_parser("enable", help="Enable a skill")
    skills_enable.add_argument("name")
    skills_enable.add_argument("--platform", default="cli")
    skills_disable = skills_subparsers.add_parser("disable", help="Disable a skill")
    skills_disable.add_argument("name")
    skills_disable.add_argument("--platform", default="cli")

    gateway = subparsers.add_parser("gateway", help="Manage gateway configuration surfaces")
    gateway_subparsers = gateway.add_subparsers(dest="gateway_command")
    gateway_subparsers.add_parser("status", help="Show gateway state")
    gateway_setup = gateway_subparsers.add_parser("setup", help="Configure gateway defaults")
    gateway_setup.add_argument("--platform", action="append", dest="platforms")
    gateway_setup.add_argument("--home-channel")
    gateway_setup.add_argument("--token")
    gateway_setup.add_argument("--api-key")
    gateway_install = gateway_subparsers.add_parser("install", help="Mark a gateway service scope as installed")
    gateway_install.add_argument("--scope", default="user")
    gateway_uninstall = gateway_subparsers.add_parser("uninstall", help="Remove installed gateway scopes")
    gateway_uninstall.add_argument("--scope")
    gateway_subparsers.add_parser("start", help="Request the gateway runtime")
    gateway_subparsers.add_parser("stop", help="Mark the gateway runtime as stopped")
    gateway_run = gateway_subparsers.add_parser("run", help="Run the gateway foreground loop")
    gateway_run.add_argument("--once", action="store_true", help="Run one gateway iteration and exit")
    gateway_run.add_argument("--poll-interval", type=float, default=2.0)
    gateway_run.add_argument("--max-loops", type=int)

    subparsers.add_parser("acp", help="Run the Agent Client Protocol adapter")

    pairing = subparsers.add_parser("pairing", help="Manage DM pairing approvals")
    pairing_subparsers = pairing.add_subparsers(dest="pairing_action")
    pairing_subparsers.add_parser("list", help="Show pending and approved users")
    pairing_approve = pairing_subparsers.add_parser("approve", help="Approve a pairing code")
    pairing_approve.add_argument("platform")
    pairing_approve.add_argument("code")
    pairing_revoke = pairing_subparsers.add_parser("revoke", help="Revoke an approved user")
    pairing_revoke.add_argument("platform")
    pairing_revoke.add_argument("user_id")
    pairing_subparsers.add_parser("clear-pending", help="Clear all pending pairing codes")

    cron = subparsers.add_parser("cron", help="Manage persisted cron jobs")
    cron_subparsers = cron.add_subparsers(dest="cron_command")
    cron_subparsers.add_parser("list", help="List cron jobs")
    cron_subparsers.add_parser("status", help="Show cron status")
    cron_create = cron_subparsers.add_parser("create", help="Create a job")
    cron_create.add_argument("--schedule", required=True)
    cron_create.add_argument("--prompt", required=True)
    cron_create.add_argument("--name")
    cron_create.add_argument("--cwd", type=Path, default=Path.cwd())
    cron_create.add_argument("--deliver", action="append")
    cron_create.add_argument("--skill", action="append", dest="skills")
    cron_edit = cron_subparsers.add_parser("edit", help="Edit a job")
    cron_edit.add_argument("job_id")
    cron_edit.add_argument("--schedule")
    cron_edit.add_argument("--prompt")
    cron_edit.add_argument("--name")
    cron_edit.add_argument("--cwd", type=Path)
    cron_edit.add_argument("--deliver", action="append")
    cron_edit.add_argument("--skill", action="append", dest="skills")
    cron_pause = cron_subparsers.add_parser("pause", help="Pause a job")
    cron_pause.add_argument("job_id")
    cron_resume = cron_subparsers.add_parser("resume", help="Resume a job")
    cron_resume.add_argument("job_id")
    cron_run = cron_subparsers.add_parser("run", help="Run a job immediately")
    cron_run.add_argument("job_id")
    cron_run.add_argument("--model")
    cron_run.add_argument("--provider")
    cron_remove = cron_subparsers.add_parser("remove", help="Remove a job")
    cron_remove.add_argument("job_id")
    cron_tick = cron_subparsers.add_parser("tick", help="Run all enabled jobs once")
    cron_tick.add_argument("--model")
    cron_tick.add_argument("--provider")

    subparsers.add_parser("commands", help="List slash commands from the ported IO registry")

    chat = subparsers.add_parser("chat", help="Start an interactive prompt loop")
    chat.add_argument("--model", help="Override model id")
    chat.add_argument("--provider", help="Override provider")
    chat.add_argument("--cwd", type=Path, help="Workspace path", default=Path.cwd())
    chat.add_argument("--no-extensions", action="store_true", help="Skip loading extensions")

    repl = subparsers.add_parser("repl", help="Start an interactive prompt loop")
    repl.add_argument("--model", help="Override model id")
    repl.add_argument("--provider", help="Override provider")
    repl.add_argument("--cwd", type=Path, help="Workspace path", default=Path.cwd())
    repl.add_argument("--no-extensions", action="store_true", help="Skip loading extensions")

    return parser


def _run_repl(args: argparse.Namespace) -> int:
    ui = TerminalUI(theme=build_theme())
    home = ensure_io_home(None)
    config = load_config(home)
    runtime = resolve_runtime(config=config, home=home, env={**load_env(home), **os.environ})
    prefetch_update_check(home=home)
    ui.console.print(
        build_welcome_banner(
            ui.console,
            model=runtime.model,
            cwd=str(args.cwd),
            enabled_toolsets=config.get("toolsets", []),
            home=home,
        )
    )
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
        payload = list_models(provider=args.provider, detailed=args.verbose)
        if args.verbose:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for model in payload:
                print(model)
        return 0

    if args.command == "sessions":
        if args.sessions_command in {None, "list"}:
            for path in SessionManager.list_for_cwd(args.cwd):
                print(path)
            return 0
        if args.sessions_command == "show":
            manager = SessionManager.open(args.session_file)
            print(json.dumps(manager.describe(), indent=2, sort_keys=True))
            return 0
        if args.sessions_command == "tree":
            manager = SessionManager.open(args.session_file)
            print(manager.format_tree())
            return 0
        if args.sessions_command == "delete":
            SessionManager.delete(args.session_file)
            print(args.session_file)
            return 0
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

    if args.command == "status":
        if args.pretty:
            print(render_status_text(show_all=args.all))
        else:
            print(json.dumps(status_report(), indent=2, sort_keys=True))
        return 0

    if args.command == "setup":
        print(ensure_io_home(args.home))
        return 0

    if args.command == "auth":
        from .auth import auth_status

        print(json.dumps(auth_status(), indent=2, sort_keys=True))
        return 0

    if args.command == "config":
        config = load_config()
        if args.config_command in {None, "show"}:
            print(json.dumps(config, indent=2, sort_keys=True))
            return 0
        if args.config_command == "get":
            value = get_config_value(config, args.path)
            if isinstance(value, (dict, list)):
                print(json.dumps(value, indent=2, sort_keys=True))
            else:
                print(value)
            return 0
        if args.config_command == "set":
            new_value = yaml.safe_load(args.value)
            save_config(set_config_value(config, args.path, new_value))
            print(args.path)
            return 0

    if args.command == "tools":
        config = load_config()
        if args.tools_command in {None, "list"}:
            payload = {
                "platform": args.platform,
                "toolsets": toolsets_status(config, args.platform),
                "tools": enabled_tools_for_platform(
                    config,
                    platform=args.platform,
                    registry=get_tool_registry(),
                ),
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.tools_command == "enable":
            save_config(set_toolset_enabled(config, args.toolset, True, platform=args.platform))
            print(args.toolset)
            return 0
        if args.tools_command == "disable":
            save_config(set_toolset_enabled(config, args.toolset, False, platform=args.platform))
            print(args.toolset)
            return 0

    if args.command == "toolsets":
        print(json.dumps(toolsets_command("cli"), indent=2, sort_keys=True))
        return 0

    if args.command == "skills":
        if args.skills_command in {None, "list"}:
            payload = [skill.to_dict() for skill in discover_skills(cwd=args.cwd, platform=args.platform)]
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.skills_command == "search":
            payload = search_skills(args.query, cwd=args.cwd, platform=args.platform)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.skills_command == "inspect":
            payload = inspect_skill(args.name, cwd=args.cwd, platform=args.platform)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.skills_command == "enable":
            save_skill_toggle(args.name, enabled=True, platform=args.platform)
            print(args.name)
            return 0
        if args.skills_command == "disable":
            save_skill_toggle(args.name, enabled=False, platform=args.platform)
            print(args.name)
            return 0

    if args.command == "gateway":
        manager = GatewayManager()
        if args.gateway_command in {None, "status"}:
            print(json.dumps(manager.status(), indent=2, sort_keys=True))
            return 0
        if args.gateway_command == "setup":
            print(
                json.dumps(
                    manager.configure(
                        platforms=args.platforms,
                        home_channel=args.home_channel,
                        token=args.token,
                        api_key=args.api_key,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.gateway_command == "install":
            print(json.dumps(manager.install(scope=args.scope), indent=2, sort_keys=True))
            return 0
        if args.gateway_command == "uninstall":
            print(json.dumps(manager.uninstall(scope=args.scope), indent=2, sort_keys=True))
            return 0
        if args.gateway_command == "start":
            print(json.dumps(manager.start(), indent=2, sort_keys=True))
            return 0
        if args.gateway_command == "stop":
            print(json.dumps(manager.stop(), indent=2, sort_keys=True))
            return 0
        if args.gateway_command == "run":
            print(
                json.dumps(
                    run_gateway(
                        once=args.once,
                        poll_interval=args.poll_interval,
                        max_loops=args.max_loops,
                    ),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

    if args.command == "acp":
        from .acp_adapter.entry import main as acp_main

        acp_main()
        return 0

    if args.command == "pairing":
        pairing_command(args)
        return 0

    if args.command == "cron":
        manager = CronManager()
        if args.cron_command in {None, "list"}:
            print(json.dumps(manager.list_jobs(), indent=2, sort_keys=True))
            return 0
        if args.cron_command == "status":
            print(json.dumps(manager.status(), indent=2, sort_keys=True))
            return 0
        if args.cron_command == "create":
            payload = manager.create_job(
                prompt=args.prompt,
                schedule=args.schedule,
                cwd=args.cwd,
                name=args.name,
                deliver=args.deliver,
                skills=args.skills,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.cron_command == "edit":
            payload = manager.update_job(
                args.job_id,
                schedule=args.schedule,
                prompt=args.prompt,
                name=args.name,
                cwd=str(args.cwd.resolve()) if args.cwd else None,
                deliver=args.deliver,
                skills=args.skills,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.cron_command == "pause":
            print(json.dumps(manager.pause_job(args.job_id), indent=2, sort_keys=True))
            return 0
        if args.cron_command == "resume":
            print(json.dumps(manager.resume_job(args.job_id), indent=2, sort_keys=True))
            return 0
        if args.cron_command == "run":
            print(
                json.dumps(
                    manager.run_job_sync(args.job_id, model=args.model, provider=args.provider),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.cron_command == "remove":
            print(json.dumps(manager.remove_job(args.job_id), indent=2, sort_keys=True))
            return 0
        if args.cron_command == "tick":
            print(json.dumps(manager.tick_sync(model=args.model, provider=args.provider), indent=2, sort_keys=True))
            return 0

    if args.command == "commands":
        print(json.dumps(COMMANDS_BY_CATEGORY, indent=2, sort_keys=True))
        return 0

    if args.command in {"chat", "repl"}:
        return _run_repl(args)

    if args.command is None and sys.stdin.isatty():
        repl_args = argparse.Namespace(
            cwd=Path.cwd(),
            model=None,
            provider=None,
            no_extensions=False,
        )
        return _run_repl(repl_args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
