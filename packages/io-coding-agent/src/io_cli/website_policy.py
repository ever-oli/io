"""Website access policy helpers for URL-capable tools."""

from __future__ import annotations

import fnmatch
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_WEBSITE_BLOCKLIST = {
    "enabled": False,
    "domains": [],
    "shared_files": [],
}

_CACHE_TTL_SECONDS = 30.0
_cache_lock = threading.Lock()
_cached_policy: dict[str, Any] | None = None
_cached_policy_path: str | None = None
_cached_policy_time: float = 0.0


def _get_io_home() -> Path:
    return Path(os.getenv("IO_HOME", Path.home() / ".io"))


def _get_default_config_path() -> Path:
    return _get_io_home() / "config.yaml"


class WebsitePolicyError(Exception):
    """Raised when a website policy file is malformed."""


def _normalize_host(host: str) -> str:
    return (host or "").strip().lower().rstrip(".")


def _normalize_rule(rule: Any) -> str | None:
    if not isinstance(rule, str):
        return None
    value = rule.strip().lower()
    if not value or value.startswith("#"):
        return None
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    value = value.split("/", 1)[0].strip().rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    return value or None


def _iter_blocklist_file_rules(path: Path) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Shared blocklist file not found (skipping): %s", path)
        return []
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Failed to read shared blocklist file %s (skipping): %s", path, exc)
        return []

    rules: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        normalized = _normalize_rule(stripped)
        if normalized:
            rules.append(normalized)
    return rules


def _load_policy_config(config_path: Path | None = None) -> dict[str, Any]:
    config_path = config_path or _get_default_config_path()
    if not config_path.exists():
        return dict(_DEFAULT_WEBSITE_BLOCKLIST)

    try:
        with open(config_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        raise WebsitePolicyError(f"Invalid config YAML at {config_path}: {exc}") from exc
    except OSError as exc:
        raise WebsitePolicyError(f"Failed to read config file {config_path}: {exc}") from exc
    if not isinstance(config, dict):
        raise WebsitePolicyError("config root must be a mapping")

    security = config.get("security", {})
    if security is None:
        security = {}
    if not isinstance(security, dict):
        raise WebsitePolicyError("security must be a mapping")

    website_blocklist = security.get("website_blocklist", {})
    if website_blocklist is None:
        website_blocklist = {}
    if not isinstance(website_blocklist, dict):
        raise WebsitePolicyError("security.website_blocklist must be a mapping")

    policy = dict(_DEFAULT_WEBSITE_BLOCKLIST)
    policy.update(website_blocklist)
    return policy


def load_website_blocklist(config_path: Path | None = None) -> dict[str, Any]:
    global _cached_policy, _cached_policy_path, _cached_policy_time

    resolved_path = str(config_path) if config_path else "__default__"
    now = time.monotonic()

    if config_path is None:
        with _cache_lock:
            if (
                _cached_policy is not None
                and _cached_policy_path == resolved_path
                and (now - _cached_policy_time) < _CACHE_TTL_SECONDS
            ):
                return _cached_policy

    config_path = config_path or _get_default_config_path()
    policy = _load_policy_config(config_path)

    raw_domains = policy.get("domains", []) or []
    if not isinstance(raw_domains, list):
        raise WebsitePolicyError("security.website_blocklist.domains must be a list")

    raw_shared_files = policy.get("shared_files", []) or []
    if not isinstance(raw_shared_files, list):
        raise WebsitePolicyError("security.website_blocklist.shared_files must be a list")

    enabled = policy.get("enabled", True)
    if not isinstance(enabled, bool):
        raise WebsitePolicyError("security.website_blocklist.enabled must be a boolean")

    rules: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for raw_rule in raw_domains:
        normalized = _normalize_rule(raw_rule)
        if normalized and ("config", normalized) not in seen:
            rules.append({"pattern": normalized, "source": "config"})
            seen.add(("config", normalized))

    for shared_file in raw_shared_files:
        if not isinstance(shared_file, str) or not shared_file.strip():
            continue
        path = Path(shared_file).expanduser()
        if not path.is_absolute():
            path = (_get_io_home() / path).resolve()
        for normalized in _iter_blocklist_file_rules(path):
            key = (str(path), normalized)
            if key in seen:
                continue
            rules.append({"pattern": normalized, "source": str(path)})
            seen.add(key)

    result = {"enabled": enabled, "rules": rules}
    if config_path == _get_default_config_path():
        with _cache_lock:
            _cached_policy = result
            _cached_policy_path = "__default__"
            _cached_policy_time = now
    return result


def invalidate_cache() -> None:
    global _cached_policy
    with _cache_lock:
        _cached_policy = None


def _match_host_against_rule(host: str, pattern: str) -> bool:
    if not host or not pattern:
        return False
    if pattern.startswith("*."):
        return fnmatch.fnmatch(host, pattern)
    return host == pattern or host.endswith(f".{pattern}")


def _extract_host_from_urlish(url: str) -> str:
    parsed = urlparse(url)
    host = _normalize_host(parsed.hostname or parsed.netloc)
    if host:
        return host
    if "://" not in url:
        schemeless = urlparse(f"//{url}")
        host = _normalize_host(schemeless.hostname or schemeless.netloc)
        if host:
            return host
    return ""


def check_website_access(url: str, config_path: Path | None = None) -> dict[str, str] | None:
    policy = load_website_blocklist(config_path)
    if not policy.get("enabled", False):
        return None

    host = _extract_host_from_urlish(url)
    if not host:
        return None

    normalized = host[4:] if host.startswith("www.") else host
    for entry in policy.get("rules", []):
        pattern = entry.get("pattern", "")
        if _match_host_against_rule(normalized, pattern):
            return {
                "host": normalized,
                "rule": pattern,
                "source": entry.get("source", "config"),
                "message": f"Access to {normalized} is blocked by website policy rule '{pattern}'.",
            }
    return None
