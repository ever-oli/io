"""REPL slash-command dispatch (Hermes/gateway parity for local `io` interactive mode).

Without this layer, inputs like `/reasoning high` are sent to the model as plain text.
Gateway Telegram already dispatches these via ``GatewayRunner``; the REPL must do the same.
"""

from __future__ import annotations

import argparse
import os
import shlex
from pathlib import Path
from typing import Any, Callable

from io_agent import resolve_runtime

from .auth import auth_status
from .commands import GATEWAY_KNOWN_COMMANDS, gateway_help_lines, resolve_command
from .config import load_config, load_env, save_config
from .models import apply_user_model_selection_to_config
from .gateway import GatewayManager
from .main import run_prompt
from .session import SessionManager
from .agent.skill_commands import build_skill_invocation_message


def parse_slash_command(text: str) -> tuple[str, str] | None:
    """Match ``GatewayRunner._parse_command_text`` (single source of behavior)."""
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    first, _, remainder = stripped.partition(" ")
    name = first[1:]
    if "@" in name:
        name = name.split("@", 1)[0]
    name = name.replace("_", "-").lower()
    return name, remainder.strip()


def _repl_session_file(cwd: Path, home: Path) -> Path:
    return SessionManager.continue_recent(cwd, home=home).session_path()


async def handle_repl_slash_command(
    text: str,
    *,
    home: Path,
    cwd: Path,
    repl_args: argparse.Namespace,
    load_extensions: bool,
    on_event: Callable[[str, dict[str, Any]], None] | None,
    repl_interactive: bool = False,
) -> tuple[bool, str]:
    """If this is a known slash command, handle it and return ``(True, message)``.

    Otherwise return ``(False, "")`` so the caller should run the agent on the original
    *text*, or ``(False, expanded)`` when *text* was a **skill slash** (Hermes-style:
    full SKILL.md is inlined for the agent).
    Unknown ``/foo`` returns ``(True, error_or_help_text)`` — same as gateway (do not
    send mistaken slash input to the model).
    """
    parsed = parse_slash_command(text)
    if parsed is None:
        return False, ""

    raw_name, arguments = parsed
    if raw_name == "start":
        lines = ["IO commands (REPL / gateway parity):", *gateway_help_lines(), "", "Send normal text to chat with the agent."]
        return True, "\n".join(lines)

    command = resolve_command(raw_name)
    if command is None:
        expanded = build_skill_invocation_message(
            f"/{raw_name}",
            user_instruction=arguments,
            home=home,
            cwd=cwd,
            platform="cli",
        )
        if expanded:
            return False, expanded
        return (
            True,
            f"Unknown command '/{raw_name}'. Send /help for commands that work in the REPL.",
        )

    canonical = command.name
    env = {**load_env(home), **os.environ}

    # Gateway-only commands that still make sense in REPL
    if canonical == "platforms":
        manager = GatewayManager(home=home)
        status = manager.status()
        lines = [
            "Gateway platforms",
            f"Desired state: {status.get('desired_state', 'stopped')}",
            f"Runtime: {status.get('runtime', {}).get('gateway_state') or 'stopped'}",
        ]
        configured = list(status.get("configured_platforms", []))
        if not configured:
            lines.append("Configured platforms: (none)")
        else:
            lines.append("Configured platforms:")
            runtime_platforms = status.get("runtime", {}).get("platforms", {})
            home_channels = status.get("home_channels", {})
            for platform_name in configured:
                runtime_state = "inactive"
                if isinstance(runtime_platforms, dict):
                    runtime_state = str(runtime_platforms.get(platform_name, {}).get("state", "inactive"))
                home_channel = None
                if isinstance(home_channels, dict):
                    home_channel = home_channels.get(platform_name, {}).get("chat_id")
                suffix = f", home={home_channel}" if home_channel else ""
                lines.append(f"- {platform_name}: {runtime_state}{suffix}")
        return True, "\n".join(lines)

    if canonical == "gateway":
        from .config import ensure_io_home
        from .gateway_spawn import spawn_gateway_run_detached

        home = ensure_io_home(None)
        parts = arguments.strip().split()
        sub = parts[0].lower() if parts else "status"
        if sub in ("start", "run"):
            _pid, _log, msg = spawn_gateway_run_detached(home)
            return True, msg
        if sub == "status":
            manager = GatewayManager(home=home)
            status = manager.status()
            lines = [
                "Gateway",
                f"Desired state: {status.get('desired_state', 'stopped')}",
                f"Runtime: {status.get('runtime', {}).get('gateway_state') or 'stopped'}",
            ]
            configured = list(status.get("configured_platforms", []))
            lines.append(
                "Configured: " + (", ".join(configured) if configured else "(none)")
            )
            return True, "\n".join(lines)
        return True, "Usage: /gateway start|run|status"

    if canonical == "gauss":
        from .config import ensure_io_home
        from .gauss import run_gauss_passthrough

        home = ensure_io_home(None)
        config = load_config(home)
        gargv = shlex.split(arguments) if arguments.strip() else []
        code = run_gauss_passthrough(gargv, config=config, home=home)
        return True, f"gauss exited with code {code}"

    if canonical in {"help", "start"}:
        lines = ["IO commands (REPL / gateway parity):", *gateway_help_lines(), "", "Send normal text to chat with the agent."]
        return True, "\n".join(lines)

    if canonical in {"new", "reset"}:
        session = SessionManager.create(cwd, home=home)
        return True, f"Started a new session.\nSession ID: {session.session_id}\nSession file: {session.session_path()}"

    if canonical == "provider":
        if arguments:
            selected = arguments.strip()
            known = {"auto"}
            providers = auth_status(home).get("providers", {})
            if isinstance(providers, dict):
                known.update(str(name) for name in providers)
            if selected not in known and not selected.startswith("custom:"):
                return True, f"Unknown provider '{selected}'. Known providers: {', '.join(sorted(known))}"
            config = load_config(home)
            config.setdefault("model", {})
            config["model"]["provider"] = selected
            save_config(config, home)
            return True, f"Default provider set to {selected}."
        status = auth_status(home)
        providers = status.get("providers", {})
        active = str(status.get("active_provider") or "none")
        lines = [f"Active provider: {active}"]
        if isinstance(providers, dict):
            for provider_name in sorted(providers):
                provider = providers[provider_name]
                label = str(provider.get("label", provider_name))
                logged_in = "configured" if provider.get("logged_in") else "not configured"
                lines.append(f"- {label}: {logged_in}")
        return True, "\n".join(lines)

    if canonical == "model":
        if arguments:
            selected = arguments.strip()
            config = load_config(home)
            model_cfg = apply_user_model_selection_to_config(
                selected, home=home, config=config, env=env
            )
            config["model"] = model_cfg
            save_config(config, home)
            rid = str(model_cfg.get("default", selected))
            return True, f"Default model set to {rid}."
        if repl_interactive:
            from .model_picker import run_model_picker_dialog

            config = load_config(home)
            choice, why = run_model_picker_dialog(home=home, config=config, env=env)
            if choice is None:
                hints = {
                    "no_providers": "No models for configured providers — add API keys (`io auth status`) or use `io models --all`.",
                    "notty": "Interactive picker needs a terminal (stdin TTY). Use `/model provider:model-id` or `io models`.",
                    "cancelled": "Model picker cancelled.",
                    "no_matches": "Unknown or ambiguous model — use `/model` and pick with Tab, or `/model provider:model-id`.",
                    "dialog_cancelled": "Model picker cancelled.",
                }
                return True, hints.get(why, "Model picker closed.")
            model_cfg = apply_user_model_selection_to_config(
                choice, home=home, config=config, env=env
            )
            config["model"] = model_cfg
            save_config(config, home)
            rid = str(model_cfg.get("default", choice))
            return True, f"Default model set to {rid}."
        config = load_config(home)
        runtime = resolve_runtime(config=config, home=home, env=env)
        return True, f"Current model: {runtime.model}\nCurrent provider: {runtime.provider}"

    if canonical == "reasoning":
        config = load_config(home)
        model_cfg = config.setdefault("model", {})
        display_cfg = config.setdefault("display", {})
        effort_values = {"none", "minimal", "low", "medium", "high", "xhigh"}
        flag_values = {"on", "show", "off", "hide"}
        selected = arguments.strip().lower()
        if selected:
            if selected in effort_values:
                model_cfg["reasoning_effort"] = selected
                save_config(config, home)
                return True, f"Reasoning effort set to {selected}."
            if selected in flag_values:
                show = selected in {"on", "show"}
                display_cfg["show_reasoning"] = show
                save_config(config, home)
                return True, "Reasoning display is now visible." if show else "Reasoning display is now hidden."
            return (
                True,
                "Usage: /reasoning [none|minimal|low|medium|high|xhigh|show|hide|on|off]",
            )
        runtime = resolve_runtime(config=config, home=home, env=env)
        effort = str(model_cfg.get("reasoning_effort", "(default)"))
        show = bool(display_cfg.get("show_reasoning", False))
        return (
            True,
            f"Reasoning effort: {effort}\nReasoning display: {'visible' if show else 'hidden'}\nModel: {runtime.model}",
        )

    if canonical == "lean":
        import asyncio

        from .lean import (
            format_lean_doctor,
            format_submit_result,
            parse_lean_slash_arguments,
            run_lean_draft,
            run_lean_formalize,
            run_lean_prove,
            run_lean_submit,
            run_lean_swarm,
        )
        from .lean_projects import handle_lean_project_slash

        config = load_config(home)
        try:
            sub, statement, _extra, lean_backend = parse_lean_slash_arguments(arguments)
        except ValueError as exc:
            return True, str(exc)
        if sub == "doctor":
            return True, format_lean_doctor(config, cwd=cwd, home=home)
        if sub == "project":
            try:
                return True, handle_lean_project_slash(statement, home=home, cwd=cwd)
            except ValueError as exc:
                return True, str(exc)
        runners = {
            "submit": run_lean_submit,
            "prove": run_lean_prove,
            "draft": run_lean_draft,
            "formalize": run_lean_formalize,
            "swarm": run_lean_swarm,
        }
        runner = runners[sub]
        result = await asyncio.to_thread(
            runner,
            statement,
            config=config,
            cwd=cwd,
            home=home,
            backend=lean_backend,
        )
        return True, format_submit_result(result)

    if canonical == "personality":
        config = load_config(home)
        display_cfg = config.setdefault("display", {})
        selected = arguments.strip()
        if selected:
            display_cfg["personality"] = selected
            save_config(config, home)
            return True, f"Personality set to {selected}."
        current = str(display_cfg.get("personality", "operator"))
        return True, f"Current personality: {current}"

    if canonical in {"status", "usage"}:
        config = load_config(home)
        runtime = resolve_runtime(config=config, home=home, env=env)
        session = SessionManager.continue_recent(cwd, home=home)
        toolsets = list(config.get("toolsets", []))
        if canonical == "status":
            lines = [
                "IO REPL session status",
                f"Session ID: {session.session_id}",
                f"Model: {runtime.model}",
                f"Provider: {runtime.provider}",
                f"Toolsets: {', '.join(toolsets) if toolsets else '(none)'}",
                f"Messages: {len(session.entries)}",
                f"Session file: {session.session_path()}",
            ]
            return True, "\n".join(lines)
        return (
            True,
            "REPL usage: token counts are included after each reply when the provider reports them. "
            "For gateway chat usage, use /status in Telegram or `io gateway status`.",
        )

    session_file = _repl_session_file(cwd, home)

    if canonical == "undo":
        from .gateway_runner import GatewayRunner

        runner = GatewayRunner(home=home)
        _ok, message = runner._undo_last_exchange(session_file)  # noqa: SLF001
        return True, message

    if canonical == "retry":
        from .gateway_runner import GatewayRunner

        runner = GatewayRunner(home=home)
        last_user = runner._last_user_message_content(session_file)  # noqa: SLF001
        if not last_user:
            return True, "No previous user message available to retry."
        result = await run_prompt(
            last_user,
            cwd=cwd,
            home=home,
            session_path=session_file,
            model=repl_args.model,
            provider=repl_args.provider,
            load_extensions=load_extensions,
            on_event=on_event,
        )
        return True, result.text.strip() or "(no response)"

    if command.cli_only:
        return (
            True,
            f"`/{canonical}` is not implemented as a REPL slash command yet. "
            f"Run: `io {canonical} --help` (or `io --help`).",
        )

    if raw_name in GATEWAY_KNOWN_COMMANDS:
        return (
            True,
            f"/{command.name} is not wired in REPL yet. "
            "See /help for supported commands, or use the matching `io` subcommand.",
        )

    return True, f"/{canonical} is not implemented in REPL yet. Try `io {canonical} --help` or /help."
