"""Lean formal bridge — subprocess to **Aristotle** (default) via ``lean.*_argv``.

Also: **OpenGauss** is not embedded; use ``io gauss …`` / ``/gauss …`` for the real ``gauss`` CLI.

Named roots: ``~/.io/lean/registry.yaml`` (``--project <name>``).
Optional ``.gauss/project.yaml`` can override the Lean root (``lean.respect_gauss_project_yaml``).
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .gauss_project import resolve_lean_root_with_gauss
from .lean_projects import registry_summary, resolve_effective_project_dir

logger = logging.getLogger(__name__)

LeanMode = Literal["submit", "prove", "draft", "formalize", "swarm"]

_GLOBAL_DEFAULT_ARGV: dict[LeanMode, list[str]] = {
    "submit": ["uv", "run", "aristotle", "submit"],
    "prove": ["uv", "run", "aristotle", "prove"],
    "draft": [],
    "formalize": [],
    "swarm": [],
}


@dataclass(slots=True)
class LeanSubmitResult:
    exit_code: int
    stdout: str
    stderr: str
    argv: list[str]


def _lean_section(config: dict[str, Any]) -> dict[str, Any]:
    raw = config.get("lean")
    return raw if isinstance(raw, dict) else {}


def _argv_from_key(lean: dict[str, Any], key: str, default: list[str]) -> list[str]:
    raw = lean.get(key)
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    if isinstance(raw, list) and raw:
        return [str(x) for x in raw]
    return list(default)


def resolve_lean_backend_name(
    lean: dict[str, Any], explicit: str | None
) -> tuple[str | None, str | None]:
    """Resolve ``lean.backends`` entry. Returns ``(name, None)`` or ``(None, err)``.

    When ``lean.backends`` is unset or empty, returns ``(None, None)`` (legacy top-level argv only)
    unless *explicit* is set, in which case return an error.
    """
    raw = lean.get("backends")
    if not isinstance(raw, dict) or not raw:
        if explicit:
            return None, (
                "lean.backends is not configured — add named entries under ``lean.backends`` "
                "and optional ``lean.default_backend`` (see ``io lean backends list`` and docs). "
                f"Remove --backend / @backend or set config. (got {explicit!r})"
            )
        return None, None
    backends: dict[str, Any] = {
        str(k): v for k, v in raw.items() if isinstance(v, dict) and str(k).strip()
    }
    if not backends:
        if explicit:
            return None, "lean.backends has no valid entries (each value must be a mapping)."
        return None, None
    if explicit:
        if explicit not in backends:
            return None, f"unknown lean backend {explicit!r}; configured: {sorted(backends)}"
        return explicit, None
    d = lean.get("default_backend")
    if isinstance(d, str) and d in backends:
        return d, None
    return sorted(backends.keys())[0], None


def _argv_from_backend_or_global(
    lean: dict[str, Any],
    backend_name: str | None,
    argv_key: str,
    mode_default: list[str],
) -> list[str]:
    """Use ``backends[backend_name][argv_key]`` when present; else top-level ``lean[argv_key]``."""
    if not backend_name:
        return _argv_from_key(lean, argv_key, mode_default)
    bmap = lean.get("backends")
    if not isinstance(bmap, dict):
        return _argv_from_key(lean, argv_key, mode_default)
    child = bmap.get(backend_name)
    if not isinstance(child, dict) or argv_key not in child:
        return _argv_from_key(lean, argv_key, mode_default)
    parent = _argv_from_key(lean, argv_key, mode_default)
    return _argv_from_key(child, argv_key, parent)


def submit_argv_from_config(config: dict[str, Any], backend_name: str | None = None) -> list[str]:
    """Argv prefix before the theorem statement (default: uv run aristotle submit)."""
    lean = _lean_section(config)
    return _argv_from_backend_or_global(
        lean, backend_name, "submit_argv", _GLOBAL_DEFAULT_ARGV["submit"]
    )


def prove_argv_from_config(config: dict[str, Any], backend_name: str | None = None) -> list[str]:
    """Argv prefix for ``prove`` (default: Aristotle via ``lean.prove_argv``)."""
    lean = _lean_section(config)
    return _argv_from_backend_or_global(
        lean, backend_name, "prove_argv", _GLOBAL_DEFAULT_ARGV["prove"]
    )


def draft_argv_from_config(config: dict[str, Any], backend_name: str | None = None) -> list[str]:
    """Argv for ``draft`` (``lean.draft_argv``)."""
    lean = _lean_section(config)
    return _argv_from_backend_or_global(
        lean, backend_name, "draft_argv", _GLOBAL_DEFAULT_ARGV["draft"]
    )


def formalize_argv_from_config(config: dict[str, Any], backend_name: str | None = None) -> list[str]:
    """Argv for ``formalize`` (``lean.formalize_argv``)."""
    lean = _lean_section(config)
    return _argv_from_backend_or_global(
        lean, backend_name, "formalize_argv", _GLOBAL_DEFAULT_ARGV["formalize"]
    )


def swarm_argv_from_config(config: dict[str, Any], backend_name: str | None = None) -> list[str]:
    """Argv for ``swarm`` (``lean.swarm_argv``)."""
    lean = _lean_section(config)
    return _argv_from_backend_or_global(
        lean, backend_name, "swarm_argv", _GLOBAL_DEFAULT_ARGV["swarm"]
    )


def lean_backends_report(config: dict[str, Any]) -> dict[str, Any]:
    """Structured view of ``lean.backends`` for doctor / ``io lean backends list``."""
    lean = _lean_section(config)
    raw = lean.get("backends")
    if not isinstance(raw, dict) or not raw:
        return {
            "configured": False,
            "hint": "Add lean.backends: { name: { prove_argv: [...] } } and lean.default_backend to use "
            "``--backend`` or ``/lean prove @name …``.",
        }
    names = sorted(str(k) for k, v in raw.items() if isinstance(v, dict))
    resolved, _ = resolve_lean_backend_name(lean, None)
    return {
        "configured": True,
        "names": names,
        "default_backend": lean.get("default_backend"),
        "resolved_default": resolved,
    }


def format_lean_backends_list(config: dict[str, Any]) -> str:
    return json.dumps(lean_backends_report(config), indent=2)


def default_project_dir(config: dict[str, Any], cwd: Path) -> Path:
    lean = _lean_section(config)
    rel = lean.get("default_project_dir", ".")
    p = Path(str(rel)).expanduser()
    return (cwd / p).resolve() if not p.is_absolute() else p.resolve()


def _timeout_for_mode(lean: dict[str, Any], mode: LeanMode) -> int:
    submit_t = int(lean.get("submit_timeout", 600))
    prove_t = int(lean.get("prove_timeout", submit_t))
    if mode == "submit":
        return submit_t
    if mode == "prove":
        return prove_t
    if mode == "draft":
        return int(lean.get("draft_timeout", prove_t))
    if mode == "formalize":
        return int(lean.get("formalize_timeout", prove_t))
    if mode == "swarm":
        return int(lean.get("swarm_timeout", prove_t))
    return submit_t


def _base_argv_for_mode(
    config: dict[str, Any], mode: LeanMode, backend_name: str | None
) -> tuple[list[str], str | None]:
    """Return ``(argv_prefix, error_message)`` for *mode*."""
    if mode == "submit":
        return submit_argv_from_config(config, backend_name), None
    if mode == "prove":
        base = prove_argv_from_config(config, backend_name)
        if not base:
            return [], "lean.prove_argv is empty; set lean.prove_argv in config"
        return base, None
    if mode == "draft":
        base = draft_argv_from_config(config, backend_name)
        if not base:
            return [], "lean.draft_argv is empty; set lean.draft_argv in config"
        return base, None
    if mode == "formalize":
        base = formalize_argv_from_config(config, backend_name)
        if not base:
            return [], "lean.formalize_argv is empty; set lean.formalize_argv in config"
        return base, None
    if mode == "swarm":
        base = swarm_argv_from_config(config, backend_name)
        if not base:
            return [], "lean.swarm_argv is empty; set lean.swarm_argv in config"
        return base, None
    return [], f"unknown lean mode {mode!r}"


def run_lean_cli(
    statement: str,
    *,
    mode: LeanMode,
    config: dict[str, Any],
    cwd: Path,
    home: Path,
    project_dir: Path | None = None,
    project_name: str | None = None,
    backend: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> LeanSubmitResult:
    """Run configured argv for *mode* + *statement* + ``--project-dir``."""
    statement = statement.strip()
    if not statement:
        return LeanSubmitResult(2, "", "empty statement", [])

    lean = _lean_section(config)
    if lean.get("enabled") is False:
        return LeanSubmitResult(2, "", "lean.enabled is false in config", [])

    if project_dir is not None and project_name:
        return LeanSubmitResult(
            2,
            "",
            "use either --project-dir or --project <name>, not both",
            [],
        )

    bname, berr = resolve_lean_backend_name(lean, backend)
    if berr:
        return LeanSubmitResult(2, "", berr, [])

    base, berr2 = _base_argv_for_mode(config, mode, bname)
    if berr2:
        return LeanSubmitResult(2, "", berr2, [])

    resolved, rerr = resolve_effective_project_dir(
        home=home,
        cwd=cwd,
        config=config,
        project_dir=project_dir,
        project_name=project_name,
    )
    if rerr:
        return LeanSubmitResult(2, "", rerr, [])
    proj = resolved if resolved is not None else default_project_dir(config, cwd)
    proj = resolve_lean_root_with_gauss(proj, config)
    argv = [*base, statement, "--project-dir", str(proj)]
    if extra_args:
        argv.extend(extra_args)

    env = {**os.environ}
    env.setdefault("IO_HOME", str(home))

    if dry_run:
        payload: dict[str, Any] = {"mode": mode, "argv": argv, "cwd": str(cwd)}
        if bname is not None:
            payload["backend"] = bname
        return LeanSubmitResult(
            0,
            json.dumps(payload, indent=2),
            "",
            argv,
        )

    timeout = _timeout_for_mode(lean, mode)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return LeanSubmitResult(124, "", f"lean {mode} timed out after {timeout}s", argv)
    except OSError as exc:
        logger.warning("lean %s failed to spawn: %s", mode, exc)
        return LeanSubmitResult(127, "", str(exc), argv)

    stderr_out = proc.stderr or ""
    if bname is not None:
        stderr_out = f"[io] lean {mode} backend={bname}\n" + stderr_out
    return LeanSubmitResult(proc.returncode, proc.stdout or "", stderr_out, argv)


def run_lean_submit(
    statement: str,
    *,
    config: dict[str, Any],
    cwd: Path,
    home: Path,
    project_dir: Path | None = None,
    project_name: str | None = None,
    backend: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> LeanSubmitResult:
    """Lean submit — default argv is Aristotle (``lean.submit_argv``)."""
    return run_lean_cli(
        statement,
        mode="submit",
        config=config,
        cwd=cwd,
        home=home,
        project_dir=project_dir,
        project_name=project_name,
        backend=backend,
        extra_args=extra_args,
        dry_run=dry_run,
    )


# Backward-compatible name
run_aristotle_submit = run_lean_submit


def run_lean_prove(
    statement: str,
    *,
    config: dict[str, Any],
    cwd: Path,
    home: Path,
    project_dir: Path | None = None,
    project_name: str | None = None,
    backend: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> LeanSubmitResult:
    """Lean prove — default argv is Aristotle (``lean.prove_argv``)."""
    return run_lean_cli(
        statement,
        mode="prove",
        config=config,
        cwd=cwd,
        home=home,
        project_dir=project_dir,
        project_name=project_name,
        backend=backend,
        extra_args=extra_args,
        dry_run=dry_run,
    )


def run_lean_draft(
    statement: str,
    *,
    config: dict[str, Any],
    cwd: Path,
    home: Path,
    project_dir: Path | None = None,
    project_name: str | None = None,
    backend: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> LeanSubmitResult:
    """Lean draft (``lean.draft_argv``)."""
    return run_lean_cli(
        statement,
        mode="draft",
        config=config,
        cwd=cwd,
        home=home,
        project_dir=project_dir,
        project_name=project_name,
        backend=backend,
        extra_args=extra_args,
        dry_run=dry_run,
    )


def run_lean_formalize(
    statement: str,
    *,
    config: dict[str, Any],
    cwd: Path,
    home: Path,
    project_dir: Path | None = None,
    project_name: str | None = None,
    backend: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> LeanSubmitResult:
    """Lean formalize (``lean.formalize_argv``)."""
    return run_lean_cli(
        statement,
        mode="formalize",
        config=config,
        cwd=cwd,
        home=home,
        project_dir=project_dir,
        project_name=project_name,
        backend=backend,
        extra_args=extra_args,
        dry_run=dry_run,
    )


def run_lean_swarm(
    statement: str,
    *,
    config: dict[str, Any],
    cwd: Path,
    home: Path,
    project_dir: Path | None = None,
    project_name: str | None = None,
    backend: str | None = None,
    extra_args: list[str] | None = None,
    dry_run: bool = False,
) -> LeanSubmitResult:
    """Lean swarm hook (``lean.swarm_argv``)."""
    return run_lean_cli(
        statement,
        mode="swarm",
        config=config,
        cwd=cwd,
        home=home,
        project_dir=project_dir,
        project_name=project_name,
        backend=backend,
        extra_args=extra_args,
        dry_run=dry_run,
    )


def format_submit_result(result: LeanSubmitResult) -> str:
    parts = [f"exit_code: {result.exit_code}"]
    if result.argv:
        parts.append("command: " + " ".join(shlex.quote(a) for a in result.argv))
    if result.stdout.strip():
        parts.append("--- stdout ---\n" + result.stdout.rstrip())
    if result.stderr.strip():
        parts.append("--- stderr ---\n" + result.stderr.rstrip())
    return "\n".join(parts).strip()


def _parse_backend_prefix(statement: str) -> tuple[str | None, str]:
    """If *statement* starts with ``@backend_name ``, return ``(name, rest)`` else ``(None, statement)``."""
    s = statement.strip()
    if not s.startswith("@"):
        return None, s
    m = re.match(r"^@([a-zA-Z][a-zA-Z0-9._-]*)\s+(.+)$", s, re.DOTALL)
    if not m:
        raise ValueError(
            "Usage: /lean prove @backend_name your statement (space after backend name; "
            "configure lean.backends — see io lean backends list)"
        )
    return m.group(1), m.group(2).strip()


def parse_lean_slash_arguments(arguments: str) -> tuple[str, str, list[str], str | None]:
    """Parse REPL/gateway remainder after ``/lean``.

    Returns ``(kind, payload, extra, backend)``. *backend* is set when using
    ``/lean prove @gauss …`` style (requires ``lean.backends`` in config).
    For ``project``, *payload* is the text after ``project``.
    """
    rest = arguments.strip()
    if not rest:
        raise ValueError(
            "Usage: /lean submit <theorem statement>\n"
            "       /lean prove|draft|formalize|swarm [@backend] <text>\n"
            "       /lean doctor\n"
            "       /lean project …\n"
            "Example: /lean submit Prove that there are infinitely many primes."
        )
    parts = rest.split(None, 1)
    sub = parts[0].lower()
    if sub == "doctor":
        return "doctor", "", [], None
    if sub == "project":
        if len(parts) < 2 or not parts[1].strip():
            raise ValueError(
                "Usage: /lean project list|show|use <name>|add <name> <path>|remove <name>"
            )
        return "project", parts[1].strip(), [], None
    if sub in ("submit", "prove", "draft", "formalize", "swarm"):
        if len(parts) < 2 or not parts[1].strip():
            raise ValueError(f"Usage: /lean {sub} [@backend] <text>")
        bex, stmt = _parse_backend_prefix(parts[1])
        if not stmt.strip():
            raise ValueError(f"Usage: /lean {sub} [@backend] <text>")
        return sub, stmt, [], bex
    raise ValueError(
        "Unknown /lean subcommand. Use: /lean submit|prove|draft|formalize|swarm|doctor|project …"
    )


def _probe_aristotle(uv: str, cwd: str, *extra: str) -> dict[str, Any]:
    try:
        r = subprocess.run(
            [uv, "run", "aristotle", *extra],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {"exit": r.returncode, "ok": r.returncode == 0}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}


def lean_doctor(config: dict[str, Any], *, cwd: Path, home: Path | None = None) -> dict[str, Any]:
    """Lightweight environment check (no network)."""
    lean = _lean_section(config)
    uv = shutil.which("uv")
    submit_a = submit_argv_from_config(config)
    prove_a = prove_argv_from_config(config)
    draft_a = draft_argv_from_config(config)
    formalize_a = formalize_argv_from_config(config)
    swarm_a = swarm_argv_from_config(config)
    report: dict[str, Any] = {
        "lean_config": lean,
        "lean_backends": lean_backends_report(config),
        "uv_on_path": bool(uv),
        "submit_argv": submit_a,
        "prove_argv": prove_a,
        "draft_argv": draft_a,
        "formalize_argv": formalize_a,
        "swarm_argv": swarm_a,
        "default_project_dir": str(default_project_dir(config, cwd)),
        "effective_lean_root_with_gauss": str(
            resolve_lean_root_with_gauss(default_project_dir(config, cwd), config)
        ),
    }
    if home is not None:
        report["project_registry"] = registry_summary(home, cwd=cwd)
    if uv and submit_a[:2] == ["uv", "run"] and "aristotle" in submit_a:
        report["aristotle_help"] = _probe_aristotle(uv, str(cwd), "--help")
    if uv and prove_a and prove_a[:2] == ["uv", "run"] and "aristotle" in prove_a:
        report["aristotle_prove_help"] = _probe_aristotle(uv, str(cwd), "prove", "--help")
    return report


def format_lean_doctor(config: dict[str, Any], *, cwd: Path, home: Path | None = None) -> str:
    return json.dumps(lean_doctor(config, cwd=cwd, home=home), indent=2)
