"""Command-line entry point for IO."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time
from pathlib import Path
import sys

import yaml

from io_tui import TerminalUI, format_io_window_title, set_terminal_title

from .banner import build_welcome_banner, prefetch_update_check
from .commands import COMMANDS_BY_CATEGORY
from .cron import CronManager
from .doctor import doctor_report
from .config import ensure_io_home, get_config_value, load_config, load_env, save_config, set_config_value
from .gateway import GatewayManager
from .gateway_runner import run_gateway
from .main import build_theme, format_prompt_result, run_prompt
from .repl_prompt import build_repl_prompt_extras
from .repl_slash import handle_repl_slash_command
from io_ai import fuzzy_filter

from .models import format_available_models_table, list_auth_available_model_refs, list_models
from .pairing import pairing_command
from .skills import discover_skills, inspect_skill, save_skill_toggle, search_skills
from .session import SessionManager
from .status import render_status_text, status_report
from .toolsets import enabled_tools_for_platform, set_toolset_enabled, toolsets_status
from .tool_trace import format_tool_trace_lines, should_trace_tool
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

    models = subparsers.add_parser(
        "models",
        help="List models: default = configured providers only (pi-style table); --all = full catalog",
    )
    models.add_argument("--provider", help="Filter to one provider id")
    models.add_argument(
        "--all",
        action="store_true",
        dest="models_catalog_all",
        help="List the full static/dynamic catalog (not restricted to providers with API keys)",
    )
    models.add_argument(
        "--search",
        dest="models_search",
        default="",
        metavar="QUERY",
        help="Fuzzy filter on provider + model id (matches pi-tui token/subsequence scoring)",
    )
    models.add_argument("--verbose", action="store_true", help="Emit JSON with metadata (--all semantics)")

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

    auth = subparsers.add_parser(
        "auth",
        help="Inspect provider auth or run GitHub Copilot device login (Hermes-style)",
    )
    auth.add_argument("--home", type=Path, default=None, help="IO home directory (default ~/.io)")
    auth_subparsers = auth.add_subparsers(dest="auth_command")
    auth_subparsers.add_parser("status", help="Show auth status (JSON)")
    auth_subparsers.add_parser(
        "copilot-login",
        help="OAuth device flow for GitHub Copilot; saves token to ~/.io/auth.json",
    )
    auth_mcp_login = auth_subparsers.add_parser(
        "mcp-login",
        help="Store MCP server OAuth/API token in ~/.io/mcp_auth.json",
    )
    auth_mcp_login.add_argument("server", help="MCP server name")
    auth_mcp_login.add_argument("token", help="Bearer/API token for this MCP server")
    auth_mcp_login.add_argument(
        "--expires-at",
        help="Optional ISO timestamp for token expiry, e.g. 2026-12-31T00:00:00+00:00",
    )
    auth_mcp_logout = auth_subparsers.add_parser(
        "mcp-logout",
        help="Remove MCP server token from ~/.io/mcp_auth.json",
    )
    auth_mcp_logout.add_argument("server", help="MCP server name")
    auth_subparsers.add_parser("mcp-status", help="Show MCP auth status (JSON)")

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

    lean = subparsers.add_parser(
        "lean",
        help="Lean / Aristotle subprocess bridge (lean.*_argv; see io gauss for OpenGauss)",
    )
    lean_sub = lean.add_subparsers(dest="lean_command", required=True)
    lean_doctor = lean_sub.add_parser("doctor", help="Check uv / aristotle availability")
    lean_doctor.add_argument("--cwd", type=Path, default=Path.cwd(), help="Working directory for checks")
    lean_submit = lean_sub.add_parser("submit", help="Submit a theorem statement to Aristotle")
    lean_submit.add_argument(
        "statement",
        nargs="+",
        help="Theorem or proof goal (quote multi-word statements in the shell)",
    )
    lean_submit.add_argument("--cwd", type=Path, default=Path.cwd(), help="Working directory for uv")
    lean_submit.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Lean project root (default: config lean.default_project_dir relative to --cwd)",
    )
    lean_submit.add_argument(
        "--project",
        dest="lean_project",
        default=None,
        metavar="NAME",
        help="Named project from ~/.io/lean/registry.yaml (io lean project add …)",
    )
    lean_submit.add_argument(
        "--backend",
        dest="lean_backend",
        default=None,
        metavar="NAME",
        help="Named prover from lean.backends (see io lean backends list)",
    )
    lean_submit.add_argument(
        "--dry-run",
        action="store_true",
        help="Print argv JSON only; do not execute",
    )
    lean_prove = lean_sub.add_parser(
        "prove",
        help="Lean prove (lean.prove_argv; default uv run aristotle prove)",
    )
    lean_prove.add_argument(
        "statement",
        nargs="+",
        help="Theorem scope or statement (depends on your prove backend)",
    )
    lean_prove.add_argument("--cwd", type=Path, default=Path.cwd(), help="Working directory for uv")
    lean_prove.add_argument("--project-dir", type=Path, default=None)
    lean_prove.add_argument(
        "--project",
        dest="lean_project",
        default=None,
        metavar="NAME",
        help="Named project from ~/.io/lean/registry.yaml",
    )
    lean_prove.add_argument(
        "--backend",
        dest="lean_backend",
        default=None,
        metavar="NAME",
        help="Named prover from lean.backends",
    )
    lean_prove.add_argument("--dry-run", action="store_true")

    lean_draft = lean_sub.add_parser(
        "draft",
        help="Lean draft (set lean.draft_argv)",
    )
    lean_draft.add_argument("statement", nargs="+", help="Draft prompt or scope for your backend")
    lean_draft.add_argument("--cwd", type=Path, default=Path.cwd())
    lean_draft.add_argument("--project-dir", type=Path, default=None)
    lean_draft.add_argument(
        "--project",
        dest="lean_project",
        default=None,
        metavar="NAME",
        help="Named project from ~/.io/lean/registry.yaml",
    )
    lean_draft.add_argument(
        "--backend",
        dest="lean_backend",
        default=None,
        metavar="NAME",
    )
    lean_draft.add_argument("--dry-run", action="store_true")

    lean_formalize = lean_sub.add_parser(
        "formalize",
        help="Lean formalize (lean.formalize_argv)",
    )
    lean_formalize.add_argument("statement", nargs="+", help="Formalize goal for your backend")
    lean_formalize.add_argument("--cwd", type=Path, default=Path.cwd())
    lean_formalize.add_argument("--project-dir", type=Path, default=None)
    lean_formalize.add_argument(
        "--project",
        dest="lean_project",
        default=None,
        metavar="NAME",
    )
    lean_formalize.add_argument(
        "--backend",
        dest="lean_backend",
        default=None,
        metavar="NAME",
    )
    lean_formalize.add_argument("--dry-run", action="store_true")

    lean_swarm = lean_sub.add_parser(
        "swarm",
        help="Lean swarm hook (lean.swarm_argv)",
    )
    lean_swarm.add_argument("statement", nargs="+", help="Swarm / orchestration payload")
    lean_swarm.add_argument("--cwd", type=Path, default=Path.cwd())
    lean_swarm.add_argument("--project-dir", type=Path, default=None)
    lean_swarm.add_argument(
        "--project",
        dest="lean_project",
        default=None,
        metavar="NAME",
    )
    lean_swarm.add_argument(
        "--backend",
        dest="lean_backend",
        default=None,
        metavar="NAME",
    )
    lean_swarm.add_argument("--dry-run", action="store_true")

    lean_be = lean_sub.add_parser(
        "backends",
        help="Show lean.backends (multi-prover / Aristotle vs Gauss CLIs)",
    )
    lean_be_sub = lean_be.add_subparsers(dest="lean_backends_command", required=True)
    lean_be_sub.add_parser("list", help="Print configured backend names and default")

    lean_proj = lean_sub.add_parser(
        "project",
        help="Manage named Lean roots (OpenGauss-style project pins)",
    )
    lean_proj.add_argument("--cwd", type=Path, default=Path.cwd(), help="Resolve relative paths against this cwd")
    lean_proj_sub = lean_proj.add_subparsers(dest="lean_project_command", required=True)
    lean_proj_sub.add_parser("list", help="List registered projects and current pin")
    lean_proj_sub.add_parser("show", help="Dump registry YAML")
    lean_proj_use = lean_proj_sub.add_parser("use", help="Set the current default project name")
    lean_proj_use.add_argument("name")
    lean_proj_add = lean_proj_sub.add_parser("add", help="Register a name -> path")
    lean_proj_add.add_argument("name")
    lean_proj_add.add_argument("path")
    lean_proj_add.add_argument(
        "--current",
        action="store_true",
        help="Also set this project as current (for lean.prefer_registry_current)",
    )
    lean_proj_rm = lean_proj_sub.add_parser("remove", help="Remove a registered name")
    lean_proj_rm.add_argument("name")

    gauss = subparsers.add_parser(
        "gauss",
        help="Run OpenGauss CLI (gauss chat, gateway, etc.) — pip install gauss-agent",
    )
    gauss.add_argument(
        "gauss_args",
        nargs=argparse.REMAINDER,
        default=[],
        help="Arguments passed to gauss (e.g. chat, gateway run, --help)",
    )

    security = subparsers.add_parser("security", help="Security utilities (Tirith installer, …)")
    security_sub = security.add_subparsers(dest="security_command", required=True)
    sec_tirith = security_sub.add_parser(
        "tirith-install",
        help="Install tirith into ~/.io/bin via cargo install --root ~/.io (Rust crate)",
    )
    sec_tirith.add_argument("--home", type=Path, default=None, help="IO home directory (default ~/.io)")

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

    soul = subparsers.add_parser(
        "soul",
        help="Show which SOUL/soul.md is loaded (debug persona for chat/gateway)",
    )
    soul_sub = soul.add_subparsers(dest="soul_command", required=True)
    soul_status = soul_sub.add_parser(
        "status",
        help="Resolved path, source (workspace vs io_home), and first lines preview",
    )
    soul_status.add_argument(
        "--cwd",
        type=Path,
        default=Path.cwd(),
        help="Working directory to resolve soul (gateway uses $HOME unless you set soul.workspace_root)",
    )

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

    research = subparsers.add_parser("research", help="Trajectory / RL export helpers (lightweight, no extra deps)")
    research_sub = research.add_subparsers(dest="research_command", required=True)
    research_list = research_sub.add_parser("list", help="List recent exportable sessions from ~/.io/state.db")
    research_list.add_argument("--home", type=Path, default=None, help="IO home directory (default: ~/.io)")
    research_list.add_argument("--limit", type=int, default=50, help="Maximum recent sessions to inspect")
    research_export = research_sub.add_parser("export", help="Export indexed sessions from ~/.io/state.db to JSONL")
    research_export.add_argument("--home", type=Path, default=None, help="IO home directory (default: ~/.io)")
    research_export.add_argument("--out", type=Path, required=True, help="Output JSONL file path")
    research_export.add_argument("--limit", type=int, default=200, help="Maximum recent sessions to export")
    research_summary = research_sub.add_parser("summary", help="Summarize an exported trajectory JSONL")
    research_summary.add_argument("--path", type=Path, required=True, help="Trajectory JSONL file path")

    return parser


def _run_repl(args: argparse.Namespace) -> int:
    set_terminal_title(format_io_window_title(args.cwd.resolve()))
    ui = TerminalUI(theme=build_theme())
    home = ensure_io_home(None)
    config = load_config(home)
    runtime = resolve_runtime(config=config, home=home, env={**load_env(home), **os.environ})
    prefetch_update_check(home=home)
    display_cfg = config.get("display", {}) or {}
    repl_multiline = bool(display_cfg.get("repl_multiline", True))
    repl_mode = str(display_cfg.get("repl_multiline_mode", "single_ctrl_j") or "single_ctrl_j").lower()
    if repl_mode not in {"meta_submit", "single_ctrl_j", "buffer"}:
        repl_mode = "single_ctrl_j"
    buffer_sentinel = str(display_cfg.get("repl_buffer_sentinel", "END") or "END")
    show_stream = bool(display_cfg.get("streaming", False))
    show_tool_trace = bool(display_cfg.get("tool_trace", True))
    tool_trace_mode = str(display_cfg.get("tool_trace_mode", "compact") or "compact")
    tool_trace_icon_preset = str(display_cfg.get("tool_trace_icon_preset", "emoji") or "emoji")
    tool_trace_icon_overrides = (
        display_cfg.get("tool_trace_icon_overrides")
        if isinstance(display_cfg.get("tool_trace_icon_overrides"), dict)
        else {}
    )
    tool_trace_show_duration = bool(display_cfg.get("tool_trace_show_duration", True))
    tool_trace_suppress = (
        display_cfg.get("tool_trace_suppress_tools")
        if isinstance(display_cfg.get("tool_trace_suppress_tools"), list)
        else []
    )
    ui.console.print(
        build_welcome_banner(
            ui.console,
            model=runtime.model,
            cwd=str(args.cwd),
            enabled_toolsets=config.get("toolsets", []),
            home=home,
        )
    )
    repl_completer, repl_auto_suggest = build_repl_prompt_extras(home, args.cwd.resolve())
    ui.console.print(
        "[dim]Tip: type [bold]/[/] then [bold]Tab[/] for slash commands; "
        "[bold]/model[/] opens a line with fuzzy [bold]Tab[/] dropdown (configured providers); "
        "[bold]/model anthropic:claude-…[/] sets in one shot; [bold]/skill-slug[/] inlines that skill’s SKILL.md "
        "(optional text after the slug is the user request).[/]"
    )
    if repl_mode == "buffer":
        ui.console.print(
            f"[dim]Multiline buffer: lines until a lone [bold]{buffer_sentinel}[/] line submits "
            f"(good for pastes).[/]"
        )
    elif repl_mode == "meta_submit" and repl_multiline:
        ui.console.print(
            "[dim]Multiline (full editor): [bold]Enter[/] newline; "
            "[bold]Esc Enter[/] or [bold]Option+Enter[/] (Meta+Enter) to submit.[/]"
        )
    elif repl_mode == "single_ctrl_j" and repl_multiline:
        ui.console.print(
            "[dim]Pi-style input: [bold]Enter[/] submits; [bold]Ctrl-J[/] inserts newline "
            "(like many shells).[/]"
        )
    pending_followup: str | None = None
    while True:
        try:
            if pending_followup is not None:
                prompt = pending_followup
                pending_followup = None
            else:
                prompt = ui.prompt(
                    completer=repl_completer,
                    auto_suggest=repl_auto_suggest,
                    multiline=repl_multiline,
                    multiline_mode=repl_mode,  # type: ignore[arg-type]
                    buffer_sentinel=buffer_sentinel,
                )
        except (EOFError, KeyboardInterrupt):
            break
        if not prompt.strip():
            continue
        if prompt.strip() in {"/quit", "/exit"}:
            break
        if prompt.strip().startswith("/"):
            handled, slash_message = asyncio.run(
                handle_repl_slash_command(
                    prompt,
                    home=home,
                    cwd=args.cwd,
                    repl_args=args,
                    load_extensions=not args.no_extensions,
                    on_event=None,
                    repl_interactive=True,
                )
            )
            if handled:
                ui.render_message("assistant", slash_message)
                continue
            if slash_message.strip():
                prompt = slash_message

        ui.console.print("[dim]Φ thinking...[/]")
        stream_state: dict[str, bool] = {"had_delta": False, "got_token_delta": False}
        tool_started_at: dict[str, float] = {}
        interrupt_registry: dict[str, object] = {}

        def _sigint(_signum: int, _frame: object | None) -> None:
            agent = interrupt_registry.get("agent")
            if agent is not None and hasattr(agent, "interrupt_requested"):
                agent.interrupt_requested = True  # type: ignore[attr-defined]

        prev_sig = signal.signal(signal.SIGINT, _sigint)
        try:
            with ui.console.status("[bold #FFBF00]Φ thinking...[/]") as thinking_status:

                def _on_event(event_type: str, payload: dict[str, object]) -> None:
                    if event_type == "turn_start":
                        stream_state["had_delta"] = False
                        iteration = int(payload.get("iteration", 0))
                        thinking_status.update(f"[bold #FFBF00]Φ thinking...[/] [dim]turn {iteration}[/]")
                    elif event_type == "message_delta" and show_stream:
                        delta = str(payload.get("delta", "") or "")
                        if delta:
                            ui.console.print(delta, end="")
                            stream_state["had_delta"] = True
                            stream_state["got_token_delta"] = True
                    elif event_type == "tool_call_start":
                        if show_tool_trace:
                            tool = str(payload.get("tool", "tool"))
                            arguments = payload.get("arguments")
                            tool_started_at[tool] = time.monotonic()
                            if isinstance(arguments, dict) and should_trace_tool(tool, suppress_tools=tool_trace_suppress):
                                for line in format_tool_trace_lines(
                                    tool,
                                    arguments,
                                    mode=tool_trace_mode,
                                    icon_preset=tool_trace_icon_preset,
                                    icon_overrides=tool_trace_icon_overrides,
                                ):
                                    ui.console.print(line, style="dim")
                        if show_stream and stream_state.get("had_delta"):
                            ui.console.print()
                            stream_state["had_delta"] = False
                        tool = str(payload.get("tool", "tool"))
                        thinking_status.update(f"[bold #FFBF00]Φ working[/] [dim]running {tool}...[/]")
                    elif event_type == "tool_output_delta" and show_stream:
                        ui.console.print(str(payload.get("delta", "") or ""), end="", style="dim")
                    elif event_type == "tool_call_end":
                        tool = str(payload.get("tool", "tool"))
                        if show_tool_trace and tool_trace_show_duration and should_trace_tool(tool, suppress_tools=tool_trace_suppress):
                            started = tool_started_at.get(tool)
                            duration = (time.monotonic() - started) if started is not None else None
                            done_line = format_tool_trace_lines(
                                tool,
                                {},
                                mode="compact",
                                icon_preset=tool_trace_icon_preset,
                                icon_overrides=tool_trace_icon_overrides,
                                duration_seconds=duration,
                            )[0]
                            ui.console.print(done_line + " done", style="dim")
                        thinking_status.update(f"[bold #FFBF00]Φ thinking...[/] [dim]finished {tool}[/]")

                result = asyncio.run(
                    run_prompt(
                        prompt,
                        cwd=args.cwd,
                        model=args.model,
                        provider=args.provider,
                        load_extensions=not args.no_extensions,
                        on_event=_on_event,
                        interrupt_registry=interrupt_registry,
                    )
                )
        finally:
            signal.signal(signal.SIGINT, prev_sig)

        if show_stream and stream_state.get("had_delta"):
            ui.console.print()

        if show_stream:
            if not stream_state.get("got_token_delta"):
                ui.console.print(format_prompt_result(result))
        else:
            ui.render_message("assistant", format_prompt_result(result))

        if result.interrupted:
            ui.console.print("[yellow]Interrupted.[/] Enter a follow-up to continue (empty to skip).")
            try:
                nxt = ui.prompt(
                    "[dim]Follow-up ›[/] ",
                    multiline=repl_multiline,
                    multiline_mode=repl_mode,  # type: ignore[arg-type]
                    buffer_sentinel=buffer_sentinel,
                )
            except (EOFError, KeyboardInterrupt):
                break
            if nxt.strip():
                pending_followup = nxt
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
        home = ensure_io_home(None)
        cfg = load_config(home)
        if args.verbose:
            payload = list_models(provider=args.provider, detailed=True)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.models_catalog_all:
            payload = list_models(provider=args.provider, detailed=False)
            for model in payload:
                print(model)
            return 0

        refs = list_auth_available_model_refs(home=home, config=cfg, provider=args.provider)
        q = str(args.models_search or "").strip()
        if q:
            refs = fuzzy_filter(refs, q, lambda m: f"{m.provider} {m.remote_id} {m.id}")
        if not refs:
            print(
                "No models available for configured providers. "
                "Add API keys (see `io auth status`, ~/.io/.env), or use `io models --all` for the full catalog."
            )
        else:
            print(format_available_models_table(refs))
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

    if args.command == "soul":
        from .config import soul_status_payload

        if args.soul_command == "status":
            home = ensure_io_home(None)
            payload = soul_status_payload(home=home, cwd=args.cwd)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        return 1

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
        home = ensure_io_home(args.home)
        if args.auth_command == "mcp-login":
            from .mcp_runtime import MCPAuthStore, mcp_auth_status

            MCPAuthStore(home=home).set_token(
                str(args.server),
                str(args.token),
                expires_at=(str(args.expires_at).strip() if args.expires_at else None),
            )
            print(json.dumps(mcp_auth_status(home), indent=2, sort_keys=True))
            return 0
        if args.auth_command == "mcp-logout":
            from .mcp_runtime import MCPAuthStore, mcp_auth_status

            MCPAuthStore(home=home).clear_token(str(args.server))
            print(json.dumps(mcp_auth_status(home), indent=2, sort_keys=True))
            return 0
        if args.auth_command == "mcp-status":
            from .mcp_runtime import mcp_auth_status

            print(json.dumps(mcp_auth_status(home), indent=2, sort_keys=True))
            return 0
        if args.auth_command == "copilot-login":
            from io_ai.auth import AuthStore
            from io_ai.copilot_auth import copilot_device_code_login, save_copilot_token_to_auth

            store = AuthStore(home=home)
            token = copilot_device_code_login()
            if not token:
                return 1
            save_copilot_token_to_auth(store, token)
            print(
                "Saved Copilot token to ~/.io/auth.json under copilot.api_key. "
                "Run `io auth status` to verify (copilot.logged_in should be true)."
            )
            return 0

        from .auth import auth_status

        print(json.dumps(auth_status(home), indent=2, sort_keys=True))
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

    if args.command == "gauss":
        from .gauss import run_gauss_passthrough

        home = ensure_io_home(None)
        config = load_config(home)
        gauss_args = getattr(args, "gauss_args", []) or []
        return run_gauss_passthrough(gauss_args, config=config, home=home)

    if args.command == "security":
        if args.security_command == "tirith-install":
            from .security.tirith import install_tirith_via_cargo

            home = ensure_io_home(args.home)
            config = load_config(home)
            sec = config.get("security") if isinstance(config.get("security"), dict) else {}
            tir = sec.get("tirith") if isinstance(sec.get("tirith"), dict) else {}
            pkg = str(tir.get("cargo_install_package", "tirith"))
            code, dest, out = install_tirith_via_cargo(home, package=pkg)
            if out:
                print(out)
            if code == 0:
                print(f"tirith installed (expected path): {dest}")
                return 0
            print(f"cargo install failed with exit {code}", file=sys.stderr)
            return 1
        return 1

    if args.command == "lean":
        from .lean import (
            format_lean_backends_list,
            format_lean_doctor,
            format_submit_result,
            run_lean_draft,
            run_lean_formalize,
            run_lean_prove,
            run_lean_submit,
            run_lean_swarm,
        )
        from . import lean_projects as lean_projects_mod

        home = ensure_io_home(None)
        config = load_config(home)
        if args.lean_command == "backends":
            if args.lean_backends_command == "list":
                print(format_lean_backends_list(config))
                return 0
            return 1
        if args.lean_command == "doctor":
            print(format_lean_doctor(config, cwd=args.cwd, home=home))
            return 0
        if args.lean_command == "project":
            lp = lean_projects_mod
            cwd = args.cwd
            try:
                cmd = args.lean_project_command
                if cmd == "list":
                    print(lp.format_registry_list(home, cwd=cwd))
                elif cmd == "show":
                    print(lp.cmd_project_show(home, cwd=cwd))
                elif cmd == "use":
                    print(lp.cmd_project_use(home, args.name))
                elif cmd == "add":
                    print(
                        lp.cmd_project_add(
                            home,
                            args.name,
                            args.path,
                            cwd=cwd,
                            set_current=bool(args.current),
                        )
                    )
                elif cmd == "remove":
                    print(lp.cmd_project_remove(home, args.name))
                else:
                    return 1
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            return 0
        if args.lean_command == "submit":
            statement = " ".join(args.statement)
            result = run_lean_submit(
                statement,
                config=config,
                cwd=args.cwd,
                home=home,
                project_dir=args.project_dir,
                project_name=args.lean_project,
                backend=args.lean_backend,
                dry_run=args.dry_run,
            )
            print(format_submit_result(result))
            return 0 if result.exit_code == 0 else 1
        if args.lean_command == "prove":
            statement = " ".join(args.statement)
            result = run_lean_prove(
                statement,
                config=config,
                cwd=args.cwd,
                home=home,
                project_dir=args.project_dir,
                project_name=args.lean_project,
                backend=args.lean_backend,
                dry_run=args.dry_run,
            )
            print(format_submit_result(result))
            return 0 if result.exit_code == 0 else 1
        if args.lean_command == "draft":
            statement = " ".join(args.statement)
            result = run_lean_draft(
                statement,
                config=config,
                cwd=args.cwd,
                home=home,
                project_dir=args.project_dir,
                project_name=args.lean_project,
                backend=args.lean_backend,
                dry_run=args.dry_run,
            )
            print(format_submit_result(result))
            return 0 if result.exit_code == 0 else 1
        if args.lean_command == "formalize":
            statement = " ".join(args.statement)
            result = run_lean_formalize(
                statement,
                config=config,
                cwd=args.cwd,
                home=home,
                project_dir=args.project_dir,
                project_name=args.lean_project,
                backend=args.lean_backend,
                dry_run=args.dry_run,
            )
            print(format_submit_result(result))
            return 0 if result.exit_code == 0 else 1
        if args.lean_command == "swarm":
            statement = " ".join(args.statement)
            result = run_lean_swarm(
                statement,
                config=config,
                cwd=args.cwd,
                home=home,
                project_dir=args.project_dir,
                project_name=args.lean_project,
                backend=args.lean_backend,
                dry_run=args.dry_run,
            )
            print(format_submit_result(result))
            return 0 if result.exit_code == 0 else 1
        return 1

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

    if args.command == "research":
        from .trajectory_export import export_trajectories_jsonl, list_exportable_sessions, summarize_export_jsonl

        if args.research_command == "list":
            h = ensure_io_home(args.home)
            rows = list_exportable_sessions(home=h, limit_sessions=args.limit)
            print(json.dumps(rows, indent=2, sort_keys=True))
            return 0
        if args.research_command == "export":
            h = ensure_io_home(args.home)
            lines = export_trajectories_jsonl(home=h, out=args.out, limit_sessions=args.limit)
            print(f"Exported {lines} sessions to {args.out}")
            return 0
        if args.research_command == "summary":
            print(json.dumps(summarize_export_jsonl(args.path), indent=2, sort_keys=True))
            return 0
        return 1

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
