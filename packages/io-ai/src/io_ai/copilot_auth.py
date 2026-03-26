"""GitHub Copilot authentication (OAuth device code + token rules).

Ported from NousResearch/hermes-agent ``hermes_cli/copilot_auth.py`` (MIT): same
OAuth **client_id** as Copilot CLI / opencode, device flow endpoints, and token
prefix rules (``gho_``, fine-grained ``github_pat_``, ``ghu_``; classic ``ghp_``
is rejected for the Copilot API).

Credential order (matches Copilot CLI / Hermes):

1. ``COPILOT_GITHUB_TOKEN`` env / ``~/.io/.env``
2. ``GH_TOKEN``
3. ``GITHUB_TOKEN``
4. ``~/.io/auth.json`` → ``copilot.api_key`` (written by ``io auth copilot-login``)
5. ``gh auth token`` when GitHub CLI is logged in with a non-classic token
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .auth import AuthStore

logger = logging.getLogger(__name__)

# OAuth device code flow (same client ID as opencode / Copilot CLI — Hermes parity)
COPILOT_OAUTH_CLIENT_ID = "Ov23li8tweQw6odWQebz"

_CLASSIC_PAT_PREFIX = "ghp_"

_DEVICE_CODE_POLL_INTERVAL = 5
_DEVICE_CODE_POLL_SAFETY_MARGIN = 3


def is_classic_pat(token: str) -> bool:
    return token.strip().startswith(_CLASSIC_PAT_PREFIX)


def validate_copilot_token(token: str) -> tuple[bool, str]:
    """Return (ok, message). Classic PATs (ghp_*) are not valid for Copilot API."""
    token = token.strip()
    if not token:
        return False, "Empty token"
    if token.startswith(_CLASSIC_PAT_PREFIX):
        return (
            False,
            "Classic Personal Access Tokens (ghp_*) are not supported by the Copilot API. "
            "Use: `io auth copilot-login`, a fine-grained PAT (github_pat_* with Copilot Requests), "
            "or `gh auth login` (device flow → gho_*).",
        )
    return True, "OK"


def _gh_cli_candidates() -> list[str]:
    candidates: list[str] = []
    resolved = shutil.which("gh")
    if resolved:
        candidates.append(resolved)
    for candidate in (
        "/opt/homebrew/bin/gh",
        "/usr/local/bin/gh",
        str(Path.home() / ".local" / "bin" / "gh"),
    ):
        if candidate not in candidates and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            candidates.append(candidate)
    return candidates


def _try_gh_cli_token() -> Optional[str]:
    for gh_path in _gh_cli_candidates():
        try:
            result = subprocess.run(
                [gh_path, "auth", "token"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.debug("gh CLI token lookup failed (%s): %s", gh_path, exc)
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def resolve_copilot_api_key(store: AuthStore, *, config: dict[str, Any] | None = None) -> str | None:
    """Resolve a token for Copilot: env (.env), auth.json, then ``gh auth token``.

    Skips unsupported classic PATs (ghp_*) and continues to the next source.
    """
    _ = config
    dotenv_map = store.dotenv_values()
    provider_cfg = store.provider_config("copilot")
    for env_key in provider_cfg.env_keys:
        value = store.env.get(env_key) or dotenv_map.get(env_key)
        if not value:
            continue
        valid, msg = validate_copilot_token(value)
        if not valid:
            logger.warning("Ignoring %s: %s", env_key, msg)
            continue
        return value.strip()

    stored = store.get_stored_provider_token("copilot")
    if stored:
        valid, msg = validate_copilot_token(stored)
        if valid:
            return stored.strip()
        logger.warning("Ignoring copilot token in auth.json: %s", msg)

    gh_tok = _try_gh_cli_token()
    if gh_tok:
        valid, msg = validate_copilot_token(gh_tok)
        if not valid:
            raise ValueError(f"Token from `gh auth token` is unsupported: {msg}")
        return gh_tok.strip()

    return None


def save_copilot_token_to_auth(store: AuthStore, token: str) -> None:
    """Persist OAuth/API token under ``auth.json`` → ``copilot`` (merged)."""
    token = token.strip()
    if not token:
        raise ValueError("Empty token")
    valid, msg = validate_copilot_token(token)
    if not valid:
        raise ValueError(msg)
    payload = store.load_auth()
    copilot_entry = payload.get("copilot")
    if not isinstance(copilot_entry, dict):
        copilot_entry = {}
    copilot_entry["api_key"] = token
    payload["copilot"] = copilot_entry
    store.save_auth(payload)


def copilot_device_code_login(
    *,
    host: str = "github.com",
    timeout_seconds: float = 300,
    user_agent: str = "IOAgent/1.0",
) -> Optional[str]:
    """Run GitHub OAuth device flow; print instructions; return access token or None."""
    domain = host.rstrip("/").removeprefix("https://").removeprefix("http://")
    device_code_url = f"https://{domain}/login/device/code"
    access_token_url = f"https://{domain}/login/oauth/access_token"

    data = urllib.parse.urlencode(
        {
            "client_id": COPILOT_OAUTH_CLIENT_ID,
            "scope": "read:user",
        }
    ).encode()

    req = urllib.request.Request(
        device_code_url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": user_agent,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            device_data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.exception("Device code request failed")
        print(f"✗ Failed to start device authorization: {exc}")
        return None

    verification_uri = device_data.get("verification_uri", "https://github.com/login/device")
    user_code = device_data.get("user_code", "")
    device_code = device_data.get("device_code", "")
    interval = max(int(device_data.get("interval", _DEVICE_CODE_POLL_INTERVAL)), 1)

    if not device_code or not user_code:
        print("✗ GitHub did not return a device code.")
        return None

    print()
    print(f" Open this URL in your browser: {verification_uri}")
    print(f" Enter this code: {user_code}")
    print()
    print(" Waiting for authorization...", end="", flush=True)

    deadline = time.time() + timeout_seconds

    while time.time() < deadline:
        time.sleep(interval + _DEVICE_CODE_POLL_SAFETY_MARGIN)

        poll_data = urllib.parse.urlencode(
            {
                "client_id": COPILOT_OAUTH_CLIENT_ID,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            }
        ).encode()

        poll_req = urllib.request.Request(
            access_token_url,
            data=poll_data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": user_agent,
            },
        )

        try:
            with urllib.request.urlopen(poll_req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
        except Exception:
            print(".", end="", flush=True)
            continue

        if result.get("access_token"):
            print(" ✓")
            return str(result["access_token"])

        error = result.get("error", "")
        if error == "authorization_pending":
            print(".", end="", flush=True)
            continue
        if error == "slow_down":
            server_interval = result.get("interval")
            if isinstance(server_interval, (int, float)) and server_interval > 0:
                interval = int(server_interval)
            else:
                interval += 5
            print(".", end="", flush=True)
            continue
        if error == "expired_token":
            print()
            print("✗ Device code expired. Run again.")
            return None
        if error == "access_denied":
            print()
            print("✗ Authorization was denied.")
            return None
        if error:
            print()
            print(f"✗ Authorization failed: {error}")
            return None

    print()
    print("✗ Timed out waiting for authorization.")
    return None
