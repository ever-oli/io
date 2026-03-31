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
from .model_router import model_router_status, recommend_model_route, set_model_router_auto
from .session import SessionManager
from .agent.skill_commands import build_skill_invocation_message
from .skills_hub import SkillsHubError, format_skills_hub_output, run_skills_hub_command


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
        lines = [
            "IO commands (REPL / gateway parity):",
            *gateway_help_lines(),
            "",
            "Send normal text to chat with the agent.",
        ]
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
                    runtime_state = str(
                        runtime_platforms.get(platform_name, {}).get("state", "inactive")
                    )
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
            lines.append("Configured: " + (", ".join(configured) if configured else "(none)"))
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
        lines = [
            "IO commands (REPL / gateway parity):",
            *gateway_help_lines(),
            "",
            "Send normal text to chat with the agent.",
        ]
        return True, "\n".join(lines)

    if canonical in {"new", "reset"}:
        session = SessionManager.create(cwd, home=home)
        return (
            True,
            f"Started a new session.\nSession ID: {session.session_id}\nSession file: {session.session_path()}",
        )

    if canonical == "provider":
        if arguments:
            selected = arguments.strip()
            known = {"auto"}
            providers = auth_status(home).get("providers", {})
            if isinstance(providers, dict):
                known.update(str(name) for name in providers)
            if selected not in known and not selected.startswith("custom:"):
                return (
                    True,
                    f"Unknown provider '{selected}'. Known providers: {', '.join(sorted(known))}",
                )
            config = load_config(home)
            config.setdefault("model", {})
            config["model"]["provider"] = selected
            save_config(config, home)
            return True, f"Default provider set to {selected}."
        if repl_interactive:
            from .provider_picker import run_provider_picker_dialog

            config = load_config(home)
            choice, why = run_provider_picker_dialog(home=home, config=config)
            if choice is None:
                hints = {
                    "no_providers": "No providers known — run `io auth status` or configure keys.",
                    "notty": "Interactive picker needs a terminal (TTY). Use `/provider openrouter` or `io auth`.",
                    "cancelled": "Provider picker cancelled.",
                    "no_matches": "Unknown or ambiguous provider — use `/provider` and pick with Tab, or `/provider <id>`.",
                }
                return True, hints.get(why, "Provider picker closed.")
            known = {"auto"}
            provs = auth_status(home).get("providers", {})
            if isinstance(provs, dict):
                known.update(str(name) for name in provs)
            if choice not in known and not choice.startswith("custom:"):
                return (
                    True,
                    f"Unknown provider '{choice}'. Known providers: {', '.join(sorted(known))}",
                )
            config.setdefault("model", {})
            config["model"]["provider"] = choice
            save_config(config, home)
            return True, f"Default provider set to {choice}."
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

    if canonical == "model-router":
        config = load_config(home)
        command = arguments.strip()
        lowered = command.lower()
        if lowered in {"on", "off"}:
            set_model_router_auto(config, lowered == "on")
            save_config(config, home)
            return (
                True,
                f"Model router auto-routing {'enabled' if lowered == 'on' else 'disabled'}.",
            )
        if lowered.startswith("auto "):
            value = lowered.split(None, 1)[1].strip()
            if value not in {"on", "off"}:
                return True, "Usage: /model-router auto on|off"
            set_model_router_auto(config, value == "on")
            save_config(config, home)
            return True, f"Model router auto-routing {'enabled' if value == 'on' else 'disabled'}."
        if lowered.startswith("recommend "):
            task = command.split(None, 1)[1].strip()
            payload = recommend_model_route(task, config=config, home=home, env=env)
            selected = payload["selected"]
            lines = [
                f"Selected route: {selected['provider']} / {selected['model']}",
                f"Reason: {payload['simple_reason']}",
                f"Simple prompt: {'yes' if payload['simple_prompt'] else 'no'}",
            ]
            fallbacks = payload.get("fallbacks") or []
            if fallbacks:
                lines.append(
                    "Fallbacks: "
                    + ", ".join(
                        f"{item['provider']}/{item['model']}"
                        for item in fallbacks
                        if isinstance(item, dict)
                    )
                )
            return True, "\n".join(lines)
        payload = model_router_status(config=config, home=home, env=env)
        runtime_payload = payload.get("runtime") or {}
        cheap_payload = payload.get("cheap_model") or {}
        lines = [
            f"Auto-routing: {'enabled' if payload.get('enabled') else 'disabled'}",
            f"Current runtime: {runtime_payload.get('provider')} / {runtime_payload.get('model')}",
        ]
        if cheap_payload:
            lines.append(
                f"Cheap model: {cheap_payload.get('provider')} / {cheap_payload.get('model')}"
            )
        fallbacks = payload.get("fallbacks") or []
        lines.append(
            "Fallbacks: "
            + (
                ", ".join(
                    f"{item['provider']}/{item['model']}"
                    for item in fallbacks
                    if isinstance(item, dict)
                )
                if fallbacks
                else "(none)"
            )
        )
        return True, "\n".join(lines)

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
                return (
                    True,
                    "Reasoning display is now visible."
                    if show
                    else "Reasoning display is now hidden.",
                )
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

    if canonical == "skills":
        try:
            payload = run_skills_hub_command(arguments, home=home, cwd=cwd)
        except SkillsHubError as exc:
            return True, str(exc)
        if payload.get("message") and payload.get("success"):
            return True, str(payload["message"])
        return True, format_skills_hub_output(payload)

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

    # Claudetenks fusion commands
    if canonical == "compact":
        """Trigger context compression immediately."""
        from io_agent.smart_compressor import SmartCompressor
        from .session import SessionManager

        session_manager = SessionManager.open(session_file)
        messages = session_manager.read_messages()

        if len(messages) < 10:
            return True, "Not enough context to compact (need 10+ messages)."

        compressor = SmartCompressor()
        result = compressor.compress(messages, force=True)

        if not result:
            return True, "Context compression did not yield savings."

        # Update session with compressed messages
        session_manager.write_messages(result.compressed_messages)

        report_lines = [
            "📦 Context Compacted",
            f"Messages removed: {result.messages_removed}",
            f"Messages preserved: {result.messages_preserved}",
            f"Estimated tokens saved: ~{result.tokens_saved}",
        ]
        if result.key_points:
            report_lines.append("\nKey points preserved:")
            for point in result.key_points[:5]:
                report_lines.append(f"  • {point}")

        return True, "\n".join(report_lines)

    if canonical == "memory":
        """Manage persistent memory."""
        from .memory_store import MemoryStore

        mem = MemoryStore(home=home)
        args_parts = arguments.split(maxsplit=1)
        subcommand = args_parts[0].lower() if args_parts else "list"
        rest = args_parts[1] if len(args_parts) > 1 else ""

        if subcommand == "add":
            if not rest:
                return True, "Usage: /memory add <content>"
            memory = mem.add(rest, category="fact", source="user")
            return True, f"✓ Memory added: {memory.id}"

        elif subcommand == "search":
            if not rest:
                return True, "Usage: /memory search <query>"
            results = mem.search(rest, limit=10)
            if not results:
                return True, "No memories found."
            lines = ["Memories:"]
            for m in results:
                lines.append(f"  [{m.category}] {m.content[:60]}... ({m.id})")
            return True, "\n".join(lines)

        elif subcommand == "list":
            stats = mem.get_stats()
            lines = [
                f"Total memories: {stats['total_memories']}",
                "By category:",
            ]
            for cat, count in stats["by_category"].items():
                lines.append(f"  {cat}: {count}")
            if stats["most_accessed"]:
                lines.append("\nMost accessed:")
                for m in stats["most_accessed"][:3]:
                    lines.append(f"  • {m.content[:50]}... ({m.access_count}x)")
            return True, "\n".join(lines)

        elif subcommand == "delete":
            if not rest:
                return True, "Usage: /memory delete <id-or-pattern>"
            # Try exact ID first, then pattern
            if mem.delete(rest):
                return True, f"✓ Memory {rest} deleted"
            count = mem.delete_by_pattern(rest)
            if count:
                return True, f"✓ Deleted {count} memories matching '{rest}'"
            return True, f"No memories found for: {rest}"

        elif subcommand == "clear":
            # This is dangerous - require confirmation
            if rest != "--force":
                return True, "⚠️  This will delete ALL memories. Use: /memory clear --force"
            # Implementation would clear all - skipping for safety
            return True, "Memory clear not yet implemented (safety check)"

        else:
            return True, "Usage: /memory [add|search|list|delete|clear] <args>"

    if canonical == "plan":
        """Plan mode - structured step-by-step planning."""
        from .plan_manager import PlanManager, PlanStepStatus

        plan_mgr = PlanManager(home=home)
        args_parts = arguments.split(maxsplit=1)
        subcommand = args_parts[0].lower() if args_parts else "show"
        rest = args_parts[1] if len(args_parts) > 1 else ""

        if subcommand == "create":
            if not rest:
                return True, "Usage: /plan create <title> | step 1 | step 2 | ..."

            # Parse: title | step1 | step2 | ...
            parts = [p.strip() for p in rest.split("|")]
            if len(parts) < 2:
                return True, "Usage: /plan create <title> | step 1 | step 2 | ..."

            title = parts[0]
            steps = parts[1:]

            plan = plan_mgr.create_plan(
                title=title, description=f"Plan created from user request", steps=steps
            )
            plan_mgr.set_active_plan(plan)

            return (
                True,
                f"✓ Plan created: {plan.title}\n   ID: {plan.id}\n   Steps: {len(plan.steps)}\n\nUse /plan next to start executing",
            )

        elif subcommand == "show":
            plan = plan_mgr.get_active_plan()
            if not plan:
                # Try to load from ID
                if rest:
                    plan = plan_mgr.load_plan(rest)
                if not plan:
                    plans = plan_mgr.list_plans()
                    if not plans:
                        return True, "No plans found. Create one with: /plan create"
                    plan = plans[0]
                    plan_mgr.set_active_plan(plan)

            return True, plan_mgr.format_plan(plan)

        elif subcommand == "list":
            plans = plan_mgr.list_plans()
            if not plans:
                return True, "No plans found."

            lines = ["Plans:"]
            for p in plans:
                status_icon = (
                    "✓" if p.status == "completed" else "◐" if p.status == "active" else "✗"
                )
                lines.append(f"  {status_icon} {p.title} ({p.progress_percentage():.0f}%) - {p.id}")
            return True, "\n".join(lines)

        elif subcommand == "next":
            plan = plan_mgr.get_active_plan()
            if not plan:
                return True, "No active plan. Use /plan show or /plan create"

            current = plan.get_current_step()
            if not current:
                return True, "Plan completed! 🎉"

            # Execute the current step
            step_prompt = current.description
            result = await run_prompt(
                step_prompt,
                cwd=cwd,
                home=home,
                model=repl_args.model,
                provider=repl_args.provider,
                load_extensions=load_extensions,
                on_event=on_event,
            )

            # Update step status
            plan_mgr.update_step_status(
                plan.id, current.id, PlanStepStatus.COMPLETED, result=result.text
            )

            # Advance to next
            plan = plan_mgr.advance_to_next_step(plan.id)

            lines = [
                f"✓ Completed: {current.description}",
                "",
            ]

            if plan and plan.get_current_step():
                next_step = plan.get_current_step()
                lines.extend(
                    [
                        f"Next step: {next_step.description}",
                        "Run /plan next to continue",
                    ]
                )
            else:
                lines.append("🎉 Plan completed!")

            return True, "\n".join(lines)

        elif subcommand == "edit":
            # Format: /plan edit <step_number> <new_description>
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                return True, "Usage: /plan edit <step_number> <new_description>"

            plan = plan_mgr.get_active_plan()
            if not plan:
                return True, "No active plan."

            try:
                step_num = int(parts[0]) - 1
                if step_num < 0 or step_num >= len(plan.steps):
                    return True, f"Invalid step number. Plan has {len(plan.steps)} steps."

                step = plan.steps[step_num]
                plan_mgr.edit_step(plan.id, step.id, parts[1])
                return True, f"✓ Step {step_num + 1} updated"
            except ValueError:
                return True, "Usage: /plan edit <step_number> <new_description>"

        elif subcommand == "add":
            plan = plan_mgr.get_active_plan()
            if not plan:
                return True, "No active plan."

            if not rest:
                return True, "Usage: /plan add <step_description>"

            plan_mgr.add_step(plan.id, rest)
            return True, f"✓ Step added to plan"

        elif subcommand == "delete":
            plan = plan_mgr.get_active_plan()
            if not plan:
                return True, "No active plan."

            if not rest:
                return True, "Usage: /plan delete <step_number>"

            try:
                step_num = int(rest) - 1
                if step_num < 0 or step_num >= len(plan.steps):
                    return True, f"Invalid step number. Plan has {len(plan.steps)} steps."

                step = plan.steps[step_num]
                plan_mgr.delete_step(plan.id, step.id)
                return True, f"✓ Step {step_num + 1} deleted"
            except ValueError:
                return True, "Usage: /plan delete <step_number>"

        elif subcommand == "cancel":
            plan = plan_mgr.get_active_plan()
            if not plan:
                return True, "No active plan."

            plan_mgr.cancel_plan(plan.id)
            return True, f"✓ Plan '{plan.title}' cancelled"

        else:
            return True, "Usage: /plan [create|show|list|next|edit|add|delete|cancel]"

    if canonical == "permissions":
        """Manage tool permissions."""
        from .permissions import PermissionContext, ToolPermissionRule, SAFE_PROFILE

        perms = PermissionContext(home=home)
        args_parts = arguments.split(maxsplit=2)
        subcommand = args_parts[0].lower() if args_parts else "list"

        if subcommand == "list":
            rules = perms.get_rules_summary()
            if not rules:
                return (
                    True,
                    "No permission rules set. All tools use default behavior (prompt if dangerous).",
                )
            lines = ["Permission rules:"]
            for rule in rules:
                lines.append(f"  [{rule['action']}] {rule['tool_pattern']}")
                if rule["reason"]:
                    lines.append(f"    Reason: {rule['reason']}")
            return True, "\n".join(lines)

        elif subcommand == "allow":
            if len(args_parts) < 2:
                return True, "Usage: /permissions allow <tool-pattern> [reason]"
            pattern = args_parts[1]
            reason = args_parts[2] if len(args_parts) > 2 else ""
            perms.add_rule(ToolPermissionRule(pattern, "allow", reason=reason), persist=True)
            return True, f"✓ Rule added: allow {pattern}"

        elif subcommand == "deny":
            if len(args_parts) < 2:
                return True, "Usage: /permissions deny <tool-pattern> [reason]"
            pattern = args_parts[1]
            reason = args_parts[2] if len(args_parts) > 2 else "Denied by user"
            perms.add_rule(ToolPermissionRule(pattern, "deny", reason=reason), persist=True)
            return True, f"✓ Rule added: deny {pattern}"

        elif subcommand == "prompt":
            if len(args_parts) < 2:
                return True, "Usage: /permissions prompt <tool-pattern> [reason]"
            pattern = args_parts[1]
            reason = args_parts[2] if len(args_parts) > 2 else ""
            perms.add_rule(ToolPermissionRule(pattern, "prompt", reason=reason), persist=True)
            return True, f"✓ Rule added: prompt for {pattern}"

        elif subcommand == "reset-safe":
            # Load safe defaults
            for rule in SAFE_PROFILE:
                perms.add_rule(rule, persist=True)
            return True, "✓ Safe permission profile loaded"

        else:
            return True, "Usage: /permissions [list|allow|deny|prompt|reset-safe] <args>"

    if canonical == "ide":
        """IDE integration commands."""
        from .tools.ide_tools import IDEConnection

        args_parts = arguments.split(maxsplit=1)
        subcommand = args_parts[0].lower() if args_parts else "status"
        rest = args_parts[1] if len(args_parts) > 1 else ""

        if subcommand == "status":
            # Check which IDEs are available
            lines = ["🖥️ IDE Integration Status", ""]

            # Check for VS Code
            try:
                import subprocess

                result = subprocess.run(["which", "code"], capture_output=True)
                if result.returncode == 0:
                    lines.append("✓ VS Code: Available")
                else:
                    lines.append("  VS Code: Not found")
            except Exception:
                lines.append("  VS Code: Not found")

            # Check for JetBrains
            try:
                result = subprocess.run(["which", "idea"], capture_output=True)
                if result.returncode == 0:
                    lines.append("✓ JetBrains (IntelliJ): Available")
                else:
                    lines.append("  JetBrains: Not found")
            except Exception:
                lines.append("  JetBrains: Not found")

            # Check for Cursor
            try:
                result = subprocess.run(["which", "cursor"], capture_output=True)
                if result.returncode == 0:
                    lines.append("✓ Cursor: Available")
                else:
                    lines.append("  Cursor: Not found")
            except Exception:
                lines.append("  Cursor: Not found")

            lines.extend(
                [
                    "",
                    "Usage:",
                    "  /ide connect <vscode|jetbrains|cursor|windsurf>",
                    "  /ide open <file> [line] [column]",
                    "  /ide diff <file>",
                    "  /ide sync <file> <line> [column]",
                ]
            )

            return True, "\n".join(lines)

        elif subcommand == "connect":
            ide_type = rest.strip() if rest else "auto"
            if not ide_type:
                return True, "Usage: /ide connect <vscode|jetbrains|cursor|windsurf|auto>"

            return (
                True,
                f"Connecting to {ide_type}... (use ide_connect tool for full functionality)",
            )

        elif subcommand == "open":
            if not rest:
                return True, "Usage: /ide open <file-path> [line] [column]"

            parts = rest.split()
            file_path = parts[0]
            line = int(parts[1]) if len(parts) > 1 else 1
            column = int(parts[2]) if len(parts) > 2 else 1

            return (
                True,
                f"Opening {file_path} at line {line}, column {column}... (use ide_open tool)",
            )

        elif subcommand == "diff":
            if not rest:
                return True, "Usage: /ide diff <file-path>"

            return True, f"Showing diff for {rest}... (use ide_diff tool)"

        elif subcommand == "sync":
            if not rest:
                return True, "Usage: /ide sync <file-path> <line> [column]"

            parts = rest.split()
            if len(parts) < 2:
                return True, "Usage: /ide sync <file-path> <line> [column]"

            file_path = parts[0]
            line = int(parts[1])
            column = int(parts[2]) if len(parts) > 2 else 1

            return (
                True,
                f"Syncing cursor to {file_path}:{line}:{column}... (use ide_sync_selection tool)",
            )

        else:
            return True, "Usage: /ide [connect|open|diff|sync|status]"

    if canonical == "voice":
        """Voice control commands."""
        args_parts = arguments.split(maxsplit=1)
        subcommand = args_parts[0].lower() if args_parts else "status"
        rest = args_parts[1] if len(args_parts) > 1 else ""

        if subcommand == "status":
            lines = [
                "🎙️ Voice System",
                "",
                "Status: Ready",
                "",
                "Available commands:",
                "  /voice record [duration]     - Record audio (default: 5s)",
                "  /voice transcribe            - Transcribe last recording",
                "  /voice speak <text>          - Speak text",
                "  /voice config                - Show voice configuration",
                "  /voice list-voices           - List available voices",
                "",
                "Or use voice_* tools directly for more control.",
            ]
            return True, "\n".join(lines)

        elif subcommand == "record":
            duration = int(rest) if rest and rest.isdigit() else 5
            return True, f"Recording {duration}s of audio... (use voice_record tool)"

        elif subcommand == "transcribe":
            return True, "Transcribing last recording... (use voice_transcribe tool)"

        elif subcommand == "speak":
            if not rest:
                return True, "Usage: /voice speak <text>"
            return True, f"Speaking: {rest[:50]}... (use voice_speak tool)"

        elif subcommand == "config":
            lines = [
                "🎙️ Voice Configuration",
                "",
                "STT Provider: whisper (OpenAI)",
                "TTS Provider: system (native)",
                "Auto-read responses: off",
                "",
                "To configure:",
                "  voice_config stt_provider=whisper tts_provider=system",
                "  voice_config auto_tts=true",
            ]
            return True, "\n".join(lines)

        elif subcommand == "list-voices":
            return True, "Listing available voices... (use voice_list_voices tool)"

        else:
            return True, "Usage: /voice [record|transcribe|speak|config|status|list-voices]"

    if canonical == "analytics":
        """Analytics and usage reports."""
        args_parts = arguments.split(maxsplit=1)
        subcommand = args_parts[0].lower() if args_parts else "status"
        rest = args_parts[1] if len(args_parts) > 1 else ""

        if subcommand == "status":
            lines = [
                "📊 Analytics",
                "",
                "Status: Tracking enabled",
                "Database: ~/.io/analytics.db",
                "",
                "Available commands:",
                "  /analytics report [period]   - Show usage report (today/week/month)",
                "  /analytics insights          - Get AI-powered insights",
                "  /analytics export [format]   - Export data (json/csv)",
                "",
                "Or use analytics_* tools for detailed control.",
            ]
            return True, "\n".join(lines)

        elif subcommand == "report":
            period = rest if rest else "week"
            return True, f"Generating {period} report... (use analytics_report tool)"

        elif subcommand == "insights":
            return True, "Analyzing usage patterns... (use analytics_insights tool)"

        elif subcommand == "export":
            fmt = rest if rest else "json"
            return True, f"Exporting analytics to {fmt}... (use analytics_export tool)"

        else:
            return True, "Usage: /analytics [report|status|export|insights]"

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

    return (
        True,
        f"/{canonical} is not implemented in REPL yet. Try `io {canonical} --help` or /help.",
    )
