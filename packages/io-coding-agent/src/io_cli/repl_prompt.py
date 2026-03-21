"""REPL prompt: tab completion, ghost suggestions, skills, pi-style /model completion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from io_agent import resolve_runtime
from io_ai import ModelRegistry, provider_label

from .auth import auth_status
from .commands import SlashCommandAutoSuggest, SlashCommandCompleter, gateway_only_slash_completions
from .config import load_config, load_env
from .skills import skill_slash_command_map


def _model_completer_payload(*, home: Path) -> dict[str, Any]:
    """Providers with credentials only (pi-mono ``getAvailable`` semantics for the picker)."""
    registry = ModelRegistry()
    status = auth_status(home)
    providers: dict[str, str] = {}
    for _pid, pdata in (status.get("providers") or {}).items():
        if isinstance(pdata, dict) and pdata.get("logged_in"):
            prov = str(pdata.get("provider", _pid))
            providers[prov] = provider_label(prov)

    def models_for(provider_id: str) -> list[str]:
        return [m.remote_id for m in registry.provider_models(provider_id)]

    config = load_config(home)
    env = {**load_env(home), **os.environ}
    runtime = resolve_runtime(config=config, home=home, env=env)
    current = str(runtime.provider or "")
    return {
        "current_provider": current,
        "providers": providers,
        "models_for": models_for,
    }


def build_repl_prompt_extras(home: Path, cwd: Path) -> tuple[SlashCommandCompleter, SlashCommandAutoSuggest]:
    """Return completer + auto-suggest for ``TerminalUI.prompt`` (slash / skills / models)."""
    extra = gateway_only_slash_completions()

    def skills_provider() -> dict[str, dict[str, Any]]:
        return skill_slash_command_map(home=home, cwd=cwd, platform="cli")

    def model_provider() -> dict[str, Any]:
        return _model_completer_payload(home=home)

    completer = SlashCommandCompleter(
        skill_commands_provider=skills_provider,
        model_completer_provider=model_provider,
        extra_slash_commands=extra,
    )
    suggest = SlashCommandAutoSuggest(completer=completer)
    return completer, suggest
