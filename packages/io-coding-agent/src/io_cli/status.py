"""Status helpers for the IO CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from io_agent import resolve_runtime

from .auth import auth_status
from .colors import Colors, color
from .cron import CronManager
from .config import (
    ensure_io_home,
    get_config_path,
    get_env_path,
    get_project_root,
    load_config,
    load_env,
    read_active_profile,
)
from .gateway import GatewayManager
from .model_router import model_router_status
from .session import SessionManager


def status_report(home: Path | None = None, cwd: Path | None = None) -> dict[str, object]:
    home = ensure_io_home(home)
    cwd = (cwd or Path.cwd()).resolve()
    config = load_config(home)
    env = {**load_env(home), **os.environ}
    runtime = resolve_runtime(config=config, home=home, env=env)
    sessions = SessionManager.list_for_cwd(cwd, home=home)
    router = model_router_status(config=config, home=home, env=env)
    return {
        "home": str(home),
        "active_profile": read_active_profile(),
        "cwd": str(cwd),
        "runtime": {
            "provider": runtime.provider,
            "model": runtime.model,
            "base_url": runtime.base_url,
            "api_mode": runtime.api_mode,
            "source": runtime.source,
        },
        "config_path": str(get_config_path(home)),
        "env_path": str(get_env_path(home)),
        "toolsets": config.get("toolsets", []),
        "model_router": router,
        "terminal": {
            "backend": str(config.get("terminal", {}).get("backend", "local")),
            "docker_image": str(config.get("terminal", {}).get("docker_image", "")),
            "singularity_image": str(config.get("terminal", {}).get("singularity_image", "")),
            "modal_image": str(config.get("terminal", {}).get("modal_image", "")),
            "daytona_image": str(config.get("terminal", {}).get("daytona_image", "")),
            "ssh_host": str(config.get("terminal", {}).get("ssh_host", "")),
            "ssh_user": str(config.get("terminal", {}).get("ssh_user", "")),
        },
        "sessions_for_cwd": len(sessions),
        "auth": auth_status(home),
        "gateway": GatewayManager(home=home).status(),
        "cron": CronManager(home=home).status(),
    }


def check_mark(ok: bool) -> str:
    return color("Φ", Colors.GREEN) if ok else color("Φ", Colors.RED)


def redact_key(key: str) -> str:
    if not key:
        return "(not set)"
    if len(key) < 12:
        return "***"
    return key[:4] + "..." + key[-4:]


def render_status_text(
    *,
    show_all: bool = False,
    home: Path | None = None,
    cwd: Path | None = None,
) -> str:
    report = status_report(home=home, cwd=cwd)
    env = {**load_env(home), **os.environ}
    runtime = report["runtime"]
    auth = report["auth"]
    gateway = report["gateway"]
    cron = report["cron"]
    terminal = report["terminal"]
    terminal_target = ""
    if terminal["backend"] == "docker":
        terminal_target = terminal["docker_image"]
    elif terminal["backend"] == "singularity":
        terminal_target = terminal["singularity_image"]
    elif terminal["backend"] == "modal":
        terminal_target = terminal["modal_image"]
    elif terminal["backend"] == "daytona":
        terminal_target = terminal["daytona_image"]
    elif terminal["backend"] == "ssh":
        host = terminal["ssh_host"]
        user = terminal["ssh_user"]
        terminal_target = f"{user}@{host}" if host and user else host or "(unconfigured)"
    lines = [
        "",
        color("ΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦ", Colors.CYAN),
        color("Φ                    Φ IO Agent Status                   Φ", Colors.CYAN),
        color("ΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦΦ", Colors.CYAN),
        "",
        color("Φ Environment", Colors.CYAN, Colors.BOLD),
        f"  Project:      {get_project_root()}",
        f"  Python:       {sys.version.split()[0]}",
        f"  .env file:    {check_mark(Path(report['env_path']).exists())} {'exists' if Path(report['env_path']).exists() else 'not found'}",
        f"  Profile:      {report['active_profile']}",
        f"  Model:        {runtime['model']}",
        f"  Provider:     {runtime['provider']}",
        "",
        color("Φ API Keys", Colors.CYAN, Colors.BOLD),
    ]
    keys = {
        "OpenRouter": "OPENROUTER_API_KEY",
        "OpenAI": "OPENAI_API_KEY",
        "Anthropic": "ANTHROPIC_API_KEY",
        "Z.AI/GLM": "GLM_API_KEY",
        "Kimi": "KIMI_API_KEY",
        "MiniMax": "MINIMAX_API_KEY",
        "GitHub": "GITHUB_TOKEN",
    }
    for name, env_var in keys.items():
        value = env.get(env_var, "")
        lines.append(f"  {name:<12}  {check_mark(bool(value))} {value if show_all else redact_key(value)}")
    lines.extend(
        [
            "",
            color("Φ Auth Providers", Colors.CYAN, Colors.BOLD),
        ]
    )
    providers = auth.get("providers", {})
    for provider_name in ("nous", "openai-codex", "openrouter", "openai", "anthropic", "copilot"):
        if provider_name not in providers:
            continue
        provider = providers[provider_name]
        label = str(provider.get("label", provider_name))
        logged_in = bool(provider.get("logged_in"))
        lines.append(f"  {label:<16} {check_mark(logged_in)} {'logged in' if logged_in else 'not configured'}")
    lines.extend(
        [
            "",
            color("Φ Runtime", Colors.CYAN, Colors.BOLD),
            f"  Base URL:     {runtime['base_url'] or '(default)'}",
            f"  API Mode:     {runtime['api_mode']}",
            f"  Source:       {runtime['source']}",
            f"  Router:       {'enabled' if report['model_router'].get('enabled') else 'disabled'}",
            f"  Toolsets:     {', '.join(report['toolsets']) if report['toolsets'] else '(none)'}",
            f"  Terminal:     {terminal['backend']}",
            f"  Target:       {terminal_target or '(default)'}",
            "",
            color("Φ Gateway", Colors.CYAN, Colors.BOLD),
            f"  State:        {gateway['desired_state']}",
            f"  Runtime:      {gateway.get('runtime', {}).get('gateway_state') or ('running' if gateway.get('runtime_available') else 'stopped')}",
            f"  Platforms:    {', '.join(gateway['configured_platforms']) if gateway['configured_platforms'] else '(none)'}",
            f"  Installed:    {', '.join(gateway['installed_scopes']) if gateway['installed_scopes'] else '(none)'}",
            "",
            color("Φ Cron", Colors.CYAN, Colors.BOLD),
            f"  Jobs:         {cron['jobs_enabled']} enabled, {cron['jobs_total']} total",
            f"  Scheduler:    {'available' if cron['scheduler_available'] else 'manual only'}",
            "",
            color("Φ Sessions", Colors.CYAN, Colors.BOLD),
            f"  Current cwd:  {report['sessions_for_cwd']} session(s)",
        ]
    )
    return "\n".join(lines)
