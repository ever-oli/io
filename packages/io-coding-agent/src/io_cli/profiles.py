"""Named IO profile management."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_PROFILE,
    atomic_write_text,
    ensure_io_home,
    get_active_profile_path,
    get_profile_home,
    get_profiles_root,
    load_config,
    read_active_profile,
    validate_profile_name,
)
from .gateway_runtime import gateway_runtime_snapshot

_CONFIG_CLONE_FILES = (
    "config.yaml",
    ".env",
    "SOUL.md",
    "auth.json",
    "mcp_auth.json",
)

_RUNTIME_STRIP_PATHS = (
    ".update_check",
    "gateway.pid",
    "gateway_state.json",
    "state.db",
    "acp/sessions",
    "agent/sessions",
    "audio_cache",
    "document_cache",
    "gateway/agent_sessions",
    "gateway/sessions",
    "image_cache",
    "logs",
)

_PROFILE_META_SKIP_NAMES = {
    "active_profile",
    "profiles",
}


@dataclass(slots=True)
class ProfileSummary:
    name: str
    path: Path
    active: bool
    exists: bool
    model: str = ""
    provider: str = ""
    gateway_running: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": str(self.path),
            "active": self.active,
            "exists": self.exists,
            "model": self.model,
            "provider": self.provider,
            "gateway_running": self.gateway_running,
        }


def _profile_names() -> list[str]:
    names = [DEFAULT_PROFILE]
    root = get_profiles_root()
    if root.exists():
        for item in sorted(root.iterdir()):
            if item.is_dir():
                try:
                    names.append(validate_profile_name(item.name))
                except ValueError:
                    continue
    return names


def _strip_runtime_artifacts(home: Path) -> None:
    for relative in _RUNTIME_STRIP_PATHS:
        target = home / relative
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)


def _copy_tree_contents(source: Path, target: Path, *, ignore_names: set[str] | None = None) -> None:
    ignored = ignore_names or set()
    for item in source.iterdir():
        if item.name in ignored:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)


def profile_status(name: str | None = None) -> dict[str, Any]:
    active_name = read_active_profile()
    selected = validate_profile_name(name or active_name)
    home = get_profile_home(selected)
    exists = home.exists()
    model = ""
    provider = ""
    if exists:
        cfg = load_config(home)
        model_cfg = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
        model = str(model_cfg.get("default", "") or "")
        provider = str(model_cfg.get("provider", "") or "")
    return ProfileSummary(
        name=selected,
        path=home,
        active=selected == active_name,
        exists=exists,
        model=model,
        provider=provider,
        gateway_running=bool(gateway_runtime_snapshot(home).get("running")) if exists else False,
    ).to_dict()


def list_profiles() -> list[dict[str, Any]]:
    active_name = read_active_profile()
    rows: list[dict[str, Any]] = []
    for name in _profile_names():
        summary = profile_status(name)
        summary["active"] = name == active_name
        rows.append(summary)
    return rows


def set_active_profile(name: str) -> dict[str, Any]:
    selected = validate_profile_name(name)
    home = get_profile_home(selected)
    if selected != DEFAULT_PROFILE and not home.is_dir():
        raise FileNotFoundError(f"Profile does not exist: {selected}")
    marker = get_active_profile_path()
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, selected + "\n", chmod=0o600)
    return profile_status(selected)


def create_profile(
    name: str,
    *,
    source_profile: str | None = None,
    clone_config: bool = False,
    clone_all: bool = False,
) -> dict[str, Any]:
    target_name = validate_profile_name(name)
    if target_name == DEFAULT_PROFILE:
        raise ValueError("Use the default profile directly instead of creating it.")
    target = get_profile_home(target_name)
    if target.exists():
        raise FileExistsError(f"Profile already exists: {target_name}")
    source_name = validate_profile_name(source_profile or read_active_profile())
    source = get_profile_home(source_name)

    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_io_home(target)
    if clone_all:
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        _copy_tree_contents(source, target, ignore_names=_PROFILE_META_SKIP_NAMES)
        _strip_runtime_artifacts(target)
        ensure_io_home(target)
    elif clone_config:
        ensure_io_home(target)
        for relative in _CONFIG_CLONE_FILES:
            src = source / relative
            dst = target / relative
            if not src.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        ensure_io_home(target)
    else:
        ensure_io_home(target)
    return {
        **profile_status(target_name),
        "source_profile": source_name,
        "clone_config": clone_config,
        "clone_all": clone_all,
    }


def delete_profile(name: str) -> dict[str, Any]:
    selected = validate_profile_name(name)
    if selected == DEFAULT_PROFILE:
        raise ValueError("Refusing to delete the default profile.")
    path = get_profile_home(selected)
    if not path.exists():
        raise FileNotFoundError(f"Profile does not exist: {selected}")
    shutil.rmtree(path)
    if read_active_profile() == selected:
        set_active_profile(DEFAULT_PROFILE)
    return {"deleted": True, "name": selected, "path": str(path)}


def rename_profile(old_name: str, new_name: str) -> dict[str, Any]:
    source_name = validate_profile_name(old_name)
    target_name = validate_profile_name(new_name)
    if source_name == DEFAULT_PROFILE or target_name == DEFAULT_PROFILE:
        raise ValueError("Renaming the default profile is not supported.")
    source = get_profile_home(source_name)
    target = get_profile_home(target_name)
    if not source.exists():
        raise FileNotFoundError(f"Profile does not exist: {source_name}")
    if target.exists():
        raise FileExistsError(f"Profile already exists: {target_name}")
    source.rename(target)
    if read_active_profile() == source_name:
        set_active_profile(target_name)
    return {"renamed": True, "from": source_name, "to": target_name, "path": str(target)}


def export_profile(name: str, output_path: Path) -> dict[str, Any]:
    selected = validate_profile_name(name)
    source = get_profile_home(selected)
    if not source.exists():
        raise FileNotFoundError(f"Profile does not exist: {selected}")
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="io-profile-export-") as tmp_root:
        staged = Path(tmp_root) / selected
        staged.mkdir(parents=True, exist_ok=True)
        _copy_tree_contents(source, staged, ignore_names=_PROFILE_META_SKIP_NAMES)
        _strip_runtime_artifacts(staged)
        with tarfile.open(output_path, "w:gz") as archive:
            archive.add(staged, arcname=selected)
    return {"exported": True, "name": selected, "path": str(output_path)}


def import_profile(name: str, archive_path: Path) -> dict[str, Any]:
    target_name = validate_profile_name(name)
    if target_name == DEFAULT_PROFILE:
        raise ValueError("Import into a named profile instead of the default profile.")
    target = get_profile_home(target_name)
    if target.exists():
        raise FileExistsError(f"Profile already exists: {target_name}")
    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.exists():
        raise FileNotFoundError(f"Archive does not exist: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="io-profile-import-") as tmp_root:
        tmp_dir = Path(tmp_root)
        with tarfile.open(archive_path, "r:*") as archive:
            for member in archive.getmembers():
                member_path = (tmp_dir / member.name).resolve()
                if not str(member_path).startswith(str(tmp_dir.resolve())):
                    raise ValueError(f"Unsafe archive entry: {member.name}")
            try:
                archive.extractall(tmp_dir, filter="data")
            except TypeError:
                archive.extractall(tmp_dir)
        roots = [item for item in tmp_dir.iterdir() if item.is_dir()]
        source_root = roots[0] if len(roots) == 1 else tmp_dir
        shutil.copytree(source_root, target)
        _strip_runtime_artifacts(target)
        ensure_io_home(target)
    return {"imported": True, "archive": str(archive_path), **profile_status(target_name)}
