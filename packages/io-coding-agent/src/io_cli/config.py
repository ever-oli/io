"""Configuration and home-directory management."""

from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from dotenv import dotenv_values

from .default_soul import DEFAULT_SOUL_MD


DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "auto",
        # Free-tier OpenRouter default for new installs (override in ~/.io/config.yaml).
        "default": "openrouter/nvidia/nemotron-3-super-120b-a12b:free",
        "base_url": "",
        "api_mode": "",
    },
    "fallback_providers": [],
    "fallback_model": {},
    "toolsets": ["io-cli"],
    "agent": {
        "max_turns": 90,
    },
    "terminal": {
        "backend": "local",
        "cwd": ".",
        "timeout": 180,
        "persistent_shell": True,
        "docker_image": "nikolaik/python-nodejs:python3.11-nodejs20",
        "docker_mount_cwd_to_workspace": False,
        "docker_forward_env": [],
        "singularity_image": "docker://python:3.11-slim",
        "modal_image": "debian_slim",
        "daytona_image": "python:3.11",
        "container_cpu": 1,
        "container_memory": 5120,
        "container_disk": 51200,
        "container_persistent": True,
        "ssh_host": "",
        "ssh_user": "",
        "ssh_port": 22,
        "ssh_key": "",
    },
    "browser": {
        "backend": "local_playwright",  # local_playwright | cdp | browserbase | browser_use
        "headless": True,
        "cdp_url": "",
        "browserbase_api_key": "",
        "browserbase_project_id": "",
        "browser_use_api_key": "",
        "browser_use_api_base": "https://api.browser-use.com/api/v2",
        "viewport_width": 1280,
        "viewport_height": 720,
        "inactivity_timeout": 120,
        "record_sessions": False,
    },
    "web": {
        "backend": "local",
        "timeout": 20,
        "max_extract_chars": 5000,
        "user_agent": "IO Agent/0.1.2",
    },
    "checkpoints": {
        "enabled": True,
        "max_snapshots": 50,
    },
    "compression": {
        "enabled": True,
        "threshold": 0.5,
        "summary_model": "google/gemini-3-flash-preview",
        "summary_provider": "auto",
        "summary_base_url": "",
    },
    "smart_model_routing": {
        "enabled": False,
        "max_simple_chars": 160,
        "max_simple_words": 28,
        "cheap_model": {},
    },
    "semantic": {
        "enabled": False,
        "max_hits": 5,
        "repo_map": False,
        "repo_map_max_entries": 25,
    },
    "auxiliary": {
        key: {"provider": "auto", "model": "", "base_url": "", "api_key": ""}
        for key in (
            "vision",
            "web_extract",
            "compression",
            "session_search",
            "skills_hub",
            "approval",
            "mcp",
            "flush_memories",
        )
    },
    "display": {
        "compact": False,
        "personality": "operator",
        "resume_display": "full",
        "bell_on_complete": False,
        "show_reasoning": False,
        "streaming": False,
        "stream_tool_output": True,
        "tool_trace": True,
        "tool_trace_mode": "compact",
        "tool_trace_icon_preset": "emoji",
        "tool_trace_icon_overrides": {},
        "tool_trace_show_duration": True,
        "tool_trace_suppress_tools": ["echo"],
        "repl_multiline": True,
        # meta_submit = full prompt_toolkit multiline (Enter newline, Meta+Enter submit).
        # single_ctrl_j = pi-like: Enter submits, Ctrl-J inserts newline (default).
        # buffer = line-oriented paste mode until a sentinel line (see repl_buffer_sentinel).
        "repl_multiline_mode": "single_ctrl_j",
        "repl_buffer_sentinel": "END",
        "show_cost": False,
        "skin": "default",
    },
    "privacy": {
        "redact_pii": False,
    },
    "security": {
        "website_blocklist": {
            "enabled": False,
            "domains": [],
            "shared_files": [],
        },
        # OpenGauss/Hermes-style Tirith CLI (optional binary on PATH or ~/.io/bin/tirith)
        "tirith": {
            "enabled": True,
            "path": "tirith",
            "timeout": 5,
            "fail_open": True,
            # Used by ``io security tirith-install`` (``cargo install`` crate name)
            "cargo_install_package": "tirith",
        },
    },
    "gateway": {
        "enabled": False,
        "remote_approval_queue": False,
        "remote_approval_timeout_seconds": 60,
        "tool_trace": True,
        "tool_trace_mode": "compact",
        "tool_trace_icon_preset": "emoji",
        "tool_trace_icon_overrides": {},
        "tool_trace_show_duration": True,
        "tool_trace_split_messages": True,
        "tool_trace_suppress_tools": ["echo"],
    },
    "honcho": {
        "enabled": False,
        "base_url": "",
        "api_key": "",
        "timeout": 30.0,
        # v3 API (https://docs.honcho.dev/v3/). Set api_version: legacy for old GET /api/* installs.
        "api_version": "v3",
        "workspace_id": "default",
        "session_id": "",
        "default_peer_id": "user",
        "conclusion_observer_peer": "io-agent",
        "conclusion_observed_peer": "user",
    },
    # Repo-local soul.md when gateway/terminal cwd is $HOME (e.g. Telegram) — see README
    "soul": {
        "workspace_root": "",
    },
    "nuggets": {
        "auto_promote": True,
        "periodic_nudge": {
            "enabled": False,
            "interval_hours": 24,
            "prompt": (
                "Summarize recent work as 3–7 bullets suitable for ~/.io/memories/MEMORY.md; "
                "use only read-safe tools."
            ),
            "model": "mock/io-test",
            "provider": "mock",
            "timeout_sec": 300,
        },
    },
    # OpenGauss bridge — subprocess passthrough (io gauss chat, gateway run, etc.)
    "gauss": {
        "enabled": True,
        "bin": "gauss",
    },
    # Formal proofs: Aristotle (Harmonic Math) via `uv run aristotle submit …`
    "lean": {
        "enabled": True,
        "default_project_dir": ".",
        # When true, use registry ``current`` as --project-dir if neither --project-dir nor --project is set
        "prefer_registry_current": False,
        # If ``project_dir/.gauss/project.yaml`` sets a lean root, use it for --project-dir
        "respect_gauss_project_yaml": True,
        # Optional: ``backends: { aristotle: { prove_argv: [...] }, gauss: { ... } }`` plus
        # ``default_backend`` — see docs/open_gauss_hermes_port.md and ``io lean backends list``.
        "submit_argv": ["uv", "run", "aristotle", "submit"],
        "submit_timeout": 600,
        # OpenGauss-style /prove — override for lean4-skills or a different CLI
        "prove_argv": ["uv", "run", "aristotle", "prove"],
        "prove_timeout": 600,
        # Gauss-style bridges — set to your OpenGauss / wrapper CLIs when used
        "draft_argv": [],
        "draft_timeout": 600,
        "formalize_argv": [],
        "formalize_timeout": 600,
        "swarm_argv": [],
        "swarm_timeout": 900,
    },
    "skills": {
        "auto_load": True,
        "disabled": [],
        "platform_disabled": {},
    },
    "platform_toolsets": {
        "cli": ["io-cli"],
        "telegram": ["io-telegram"],
        "discord": ["io-discord"],
        "slack": ["io-slack"],
        "whatsapp": ["io-whatsapp"],
        "signal": ["io-signal"],
        "email": ["io-email"],
        "sms": ["io-sms"],
        "homeassistant": ["io-homeassistant"],
        "dingtalk": ["io-dingtalk"],
        "webhook": ["io-cli"],
    },
    "custom_providers": [],
}

DEFAULT_PROFILE = "default"
PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def get_default_io_home() -> Path:
    return Path.home() / ".io"


def get_profiles_root() -> Path:
    return get_default_io_home() / "profiles"


def get_active_profile_path() -> Path:
    return get_default_io_home() / "active_profile"


def validate_profile_name(name: str) -> str:
    normalized = str(name or "").strip().lower()
    if normalized == DEFAULT_PROFILE:
        return DEFAULT_PROFILE
    if not PROFILE_NAME_RE.match(normalized):
        raise ValueError(
            f"Invalid profile name {name!r}. Expected {PROFILE_NAME_RE.pattern!r} or 'default'."
        )
    return normalized


def get_profile_home(name: str) -> Path:
    normalized = validate_profile_name(name)
    if normalized == DEFAULT_PROFILE:
        return get_default_io_home()
    return get_profiles_root() / normalized


def read_active_profile() -> str:
    path = get_active_profile_path()
    try:
        selected = path.read_text(encoding="utf-8").strip()
    except OSError:
        return DEFAULT_PROFILE
    if not selected:
        return DEFAULT_PROFILE
    try:
        return validate_profile_name(selected)
    except ValueError:
        return DEFAULT_PROFILE


def resolve_io_home(
    home: Path | None = None,
    *,
    profile: str | None = None,
    env: dict[str, str] | None = None,
) -> Path:
    runtime_env = dict(os.environ) if env is None else dict(env)
    if home is not None:
        return Path(home).expanduser().resolve()

    explicit_home = str(runtime_env.get("IO_HOME", "") or "").strip()
    if explicit_home:
        return Path(explicit_home).expanduser().resolve()

    selected_profile = profile or runtime_env.get("IO_PROFILE") or read_active_profile()
    return get_profile_home(validate_profile_name(selected_profile))


def _atomic_write_bytes(path: Path, data: bytes, *, chmod: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if chmod is not None:
            try:
                os.chmod(tmp_path, chmod)
            except OSError:
                pass
        os.replace(tmp_path, path)
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_text(
    path: Path,
    text: str,
    *,
    encoding: str = "utf-8",
    chmod: int | None = None,
) -> None:
    _atomic_write_bytes(path, text.encode(encoding), chmod=chmod)


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int = 2,
    sort_keys: bool = True,
    ensure_ascii: bool = False,
    chmod: int | None = None,
) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii),
        chmod=chmod,
    )


def atomic_write_yaml(
    path: Path,
    payload: Any,
    *,
    sort_keys: bool = False,
    chmod: int | None = None,
) -> None:
    atomic_write_text(path, yaml.safe_dump(payload, sort_keys=sort_keys), chmod=chmod)


def get_io_home() -> Path:
    return resolve_io_home()


def get_config_path(home: Path | None = None) -> Path:
    return ensure_io_home(home) / "config.yaml"


def get_env_path(home: Path | None = None) -> Path:
    return ensure_io_home(home) / ".env"


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _secure_dir(path: Path) -> None:
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _ensure_default_soul(home: Path) -> None:
    soul_path = home / "SOUL.md"
    if soul_path.exists():
        return
    atomic_write_text(soul_path, DEFAULT_SOUL_MD, chmod=0o600)
    _secure_file(soul_path)


def ensure_io_home(home: Path | None = None) -> Path:
    home = resolve_io_home(home)
    directories = (
        home,
        home / "cron",
        home / "logs",
        home / "memories",
        home / "skills",
        home / "skins",
        home / "gateway",
        home / "pairing",
        home / "approvals",
        home / "sandboxes",
        home / "agent",
        home / "agent" / "sessions",
        home / "agent" / "extensions",
    )
    for path in directories:
        path.mkdir(parents=True, exist_ok=True)
        _secure_dir(path)

    _ensure_default_soul(home)

    config_path = home / "config.yaml"
    if not config_path.exists():
        atomic_write_yaml(config_path, DEFAULT_CONFIG, sort_keys=False, chmod=0o600)
        _secure_file(config_path)

    env_path = home / ".env"
    if not env_path.exists():
        atomic_write_text(env_path, "", chmod=0o600)
        _secure_file(env_path)

    return home


def load_config(home: Path | None = None) -> dict[str, Any]:
    home = ensure_io_home(home)
    config_path = home / "config.yaml"
    if not config_path.exists():
        return deepcopy(DEFAULT_CONFIG)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return _merge(DEFAULT_CONFIG, data)


def save_config(config: dict[str, Any], home: Path | None = None) -> Path:
    home = ensure_io_home(home)
    config_path = home / "config.yaml"
    atomic_write_yaml(config_path, config, sort_keys=False, chmod=0o600)
    _secure_file(config_path)
    return config_path


def _walk_path(config: dict[str, Any], path: str, *, create: bool = False) -> tuple[dict[str, Any], str]:
    cursor = config
    parts = [segment for segment in path.split(".") if segment]
    if not parts:
        raise ValueError("Config path cannot be empty.")
    for segment in parts[:-1]:
        value = cursor.get(segment)
        if not isinstance(value, dict):
            if not create:
                raise KeyError(path)
            value = {}
            cursor[segment] = value
        cursor = value
    return cursor, parts[-1]


def get_config_value(config: dict[str, Any], path: str) -> Any:
    cursor: Any = config
    for segment in [segment for segment in path.split(".") if segment]:
        if not isinstance(cursor, dict) or segment not in cursor:
            raise KeyError(path)
        cursor = cursor[segment]
    return cursor


def set_config_value(config: dict[str, Any], path: str, value: Any) -> dict[str, Any]:
    parent, leaf = _walk_path(config, path, create=True)
    parent[leaf] = value
    return config


def load_env(home: Path | None = None) -> dict[str, str]:
    home = ensure_io_home(home)
    env_path = home / ".env"
    return {key: value for key, value in dotenv_values(env_path).items() if value is not None}


def _find_workspace_soul(start: Path) -> Path | None:
    """First ``soul.md`` or ``SOUL.md`` walking up from *start* (repo-local persona)."""
    cur = start.resolve()
    for _ in range(24):
        for name in ("soul.md", "SOUL.md"):
            candidate = cur / name
            if candidate.is_file():
                return candidate
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def _soul_file_in_dir(directory: Path) -> Path | None:
    """Return ``soul.md`` or ``SOUL.md`` directly under *directory* if present."""
    d = directory.resolve()
    for name in ("soul.md", "SOUL.md"):
        candidate = d / name
        if candidate.is_file():
            return candidate
    return None


def resolve_soul_path(
    home: Path | None = None,
    *,
    cwd: Path | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    """Return ``(path, source)`` — *source* is ``workspace``, ``workspace_root``, or ``io_home``."""
    home = ensure_io_home(home)
    cfg = config if config is not None else load_config(home)
    soul_cfg = cfg.get("soul") if isinstance(cfg.get("soul"), dict) else {}
    root_raw = str(soul_cfg.get("workspace_root", "") or "").strip()

    if cwd is not None:
        ws = _find_workspace_soul(cwd)
        if ws is not None:
            return ws, "workspace"
    if root_raw:
        root = Path(root_raw).expanduser()
        if not root.is_absolute():
            root = (Path.home() / root).resolve()
        else:
            root = root.resolve()
        fixed = _soul_file_in_dir(root)
        if fixed is not None:
            return fixed, "workspace_root"
    return home / "SOUL.md", "io_home"


def load_soul(
    home: Path | None = None,
    *,
    cwd: Path | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Load system persona: cwd walk, then ``soul.workspace_root``, else ``~/.io/SOUL.md``."""
    path, _src = resolve_soul_path(home, cwd=cwd, config=config)
    return path.read_text(encoding="utf-8")


def soul_status_payload(
    home: Path | None = None,
    *,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Diagnostics: which soul file prompts use, plus a short preview (``io soul status``)."""
    home = ensure_io_home(home)
    cwd = (cwd or Path.cwd()).resolve()
    cfg = load_config(home)
    path, source = resolve_soul_path(home, cwd=cwd, config=cfg)
    exists = path.is_file()
    text = path.read_text(encoding="utf-8") if exists else ""
    lines = text.splitlines()
    preview_lines = lines[:8]
    preview = "\n".join(preview_lines)
    if len(lines) > 8 or len(text) > 600:
        preview = preview[:600] + "…"
    return {
        "soul_path": str(path),
        "soul_source": source,
        "exists": exists,
        "char_count": len(text),
        "line_count": len(lines),
        "preview": preview if preview else "(empty file)",
        "hint": (
            "Telegram/gateway often uses cwd=$HOME — set soul.workspace_root in ~/.io/config.yaml "
            "if soul_source is io_home but your persona lives in a repo."
            if source == "io_home"
            else "This file is prepended as the system prompt for IO (plus memories suffix)."
        ),
    }


def memory_snapshot(home: Path | None = None) -> str:
    home = ensure_io_home(home)
    memories = []
    for name in ("MEMORY.md", "USER.md"):
        path = home / "memories" / name
        if path.exists():
            contents = path.read_text(encoding="utf-8").strip()
            if contents:
                memories.append(f"# {name}\n{contents}")
    return "\n\n".join(memories).strip()
