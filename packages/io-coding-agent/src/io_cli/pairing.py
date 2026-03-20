"""CLI commands and storage for gateway DM pairing."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path

from .config import ensure_io_home


ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
CODE_TTL_SECONDS = 3600
RATE_LIMIT_SECONDS = 600
LOCKOUT_SECONDS = 3600
MAX_PENDING_PER_PLATFORM = 3
MAX_FAILED_ATTEMPTS = 5


def _secure_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


class PairingStore:
    """Manages pending pairing codes and approved gateway users."""

    def __init__(self, *, home: Path | None = None) -> None:
        self.home = ensure_io_home(home)
        self.pairing_dir = self.home / "pairing"
        self.pairing_dir.mkdir(parents=True, exist_ok=True)

    def _pending_path(self, platform: str) -> Path:
        return self.pairing_dir / f"{platform}-pending.json"

    def _approved_path(self, platform: str) -> Path:
        return self.pairing_dir / f"{platform}-approved.json"

    def _rate_limit_path(self) -> Path:
        return self.pairing_dir / "_rate_limits.json"

    def _load_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_json(self, path: Path, data: dict) -> None:
        _secure_write(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))

    def is_approved(self, platform: str, user_id: str) -> bool:
        approved = self._load_json(self._approved_path(platform))
        return user_id in approved

    def list_approved(self, platform: str | None = None) -> list[dict]:
        results: list[dict] = []
        platforms = [platform] if platform else self._all_platforms("approved")
        for current in platforms:
            approved = self._load_json(self._approved_path(current))
            for user_id, info in approved.items():
                if isinstance(info, dict):
                    results.append({"platform": current, "user_id": user_id, **info})
        return results

    def _approve_user(self, platform: str, user_id: str, user_name: str = "") -> None:
        approved = self._load_json(self._approved_path(platform))
        approved[user_id] = {"user_name": user_name, "approved_at": time.time()}
        self._save_json(self._approved_path(platform), approved)

    def revoke(self, platform: str, user_id: str) -> bool:
        approved = self._load_json(self._approved_path(platform))
        if user_id not in approved:
            return False
        del approved[user_id]
        self._save_json(self._approved_path(platform), approved)
        return True

    def generate_code(self, platform: str, user_id: str, user_name: str = "") -> str | None:
        self._cleanup_expired(platform)
        if self._is_locked_out(platform) or self._is_rate_limited(platform, user_id):
            return None
        pending = self._load_json(self._pending_path(platform))
        if len(pending) >= MAX_PENDING_PER_PLATFORM:
            return None
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
        pending[code] = {"user_id": user_id, "user_name": user_name, "created_at": time.time()}
        self._save_json(self._pending_path(platform), pending)
        self._record_rate_limit(platform, user_id)
        return code

    def approve_code(self, platform: str, code: str) -> dict | None:
        self._cleanup_expired(platform)
        pending = self._load_json(self._pending_path(platform))
        normalized = code.upper().strip()
        if normalized not in pending:
            self._record_failed_attempt(platform)
            return None
        entry = pending.pop(normalized)
        self._save_json(self._pending_path(platform), pending)
        user_id = str(entry.get("user_id", "")).strip()
        user_name = str(entry.get("user_name", "")).strip()
        if not user_id:
            return None
        self._approve_user(platform, user_id, user_name)
        return {"user_id": user_id, "user_name": user_name}

    def list_pending(self, platform: str | None = None) -> list[dict]:
        results: list[dict] = []
        platforms = [platform] if platform else self._all_platforms("pending")
        for current in platforms:
            self._cleanup_expired(current)
            pending = self._load_json(self._pending_path(current))
            for code, info in pending.items():
                if not isinstance(info, dict):
                    continue
                age_minutes = int((time.time() - float(info.get("created_at", 0))) / 60)
                results.append(
                    {
                        "platform": current,
                        "code": code,
                        "user_id": str(info.get("user_id", "")),
                        "user_name": str(info.get("user_name", "")),
                        "age_minutes": age_minutes,
                    }
                )
        return results

    def clear_pending(self, platform: str | None = None) -> int:
        count = 0
        platforms = [platform] if platform else self._all_platforms("pending")
        for current in platforms:
            pending = self._load_json(self._pending_path(current))
            count += len(pending)
            self._save_json(self._pending_path(current), {})
        return count

    def _is_rate_limited(self, platform: str, user_id: str) -> bool:
        limits = self._load_json(self._rate_limit_path())
        last_request = float(limits.get(f"{platform}:{user_id}", 0) or 0)
        return (time.time() - last_request) < RATE_LIMIT_SECONDS

    def _record_rate_limit(self, platform: str, user_id: str) -> None:
        limits = self._load_json(self._rate_limit_path())
        limits[f"{platform}:{user_id}"] = time.time()
        self._save_json(self._rate_limit_path(), limits)

    def _is_locked_out(self, platform: str) -> bool:
        limits = self._load_json(self._rate_limit_path())
        lockout_until = float(limits.get(f"_lockout:{platform}", 0) or 0)
        return time.time() < lockout_until

    def _record_failed_attempt(self, platform: str) -> None:
        limits = self._load_json(self._rate_limit_path())
        fail_key = f"_failures:{platform}"
        failures = int(limits.get(fail_key, 0) or 0) + 1
        limits[fail_key] = failures
        if failures >= MAX_FAILED_ATTEMPTS:
            limits[f"_lockout:{platform}"] = time.time() + LOCKOUT_SECONDS
            limits[fail_key] = 0
        self._save_json(self._rate_limit_path(), limits)

    def _cleanup_expired(self, platform: str) -> None:
        pending = self._load_json(self._pending_path(platform))
        now = time.time()
        expired = [
            code for code, info in pending.items()
            if isinstance(info, dict) and (now - float(info.get("created_at", 0) or 0)) > CODE_TTL_SECONDS
        ]
        if expired:
            for code in expired:
                pending.pop(code, None)
            self._save_json(self._pending_path(platform), pending)

    def _all_platforms(self, suffix: str) -> list[str]:
        platforms: list[str] = []
        for path in self.pairing_dir.glob(f"*-{suffix}.json"):
            platform = path.name[: -len(f"-{suffix}.json")]
            if platform and not platform.startswith("_"):
                platforms.append(platform)
        return sorted(platforms)


def pairing_command(args, *, home: Path | None = None) -> None:
    store = PairingStore(home=home)
    action = getattr(args, "pairing_action", None)
    if action == "list":
        _cmd_list(store)
        return
    if action == "approve":
        _cmd_approve(store, args.platform, args.code)
        return
    if action == "revoke":
        _cmd_revoke(store, args.platform, args.user_id)
        return
    if action == "clear-pending":
        _cmd_clear_pending(store)
        return
    print("Usage: io pairing {list|approve|revoke|clear-pending}")
    print("Run 'io pairing --help' for details.")


def _cmd_list(store: PairingStore) -> None:
    pending = store.list_pending()
    approved = store.list_approved()
    if not pending and not approved:
        print("No pairing data found. No one has tried to pair yet~")
        return
    if pending:
        print(f"\n  Pending Pairing Requests ({len(pending)}):")
        print(f"  {'Platform':<12} {'Code':<10} {'User ID':<20} {'Name':<20} {'Age'}")
        print(f"  {'--------':<12} {'----':<10} {'-------':<20} {'----':<20} {'---'}")
        for item in pending:
            print(
                f"  {item['platform']:<12} {item['code']:<10} {item['user_id']:<20} "
                f"{item.get('user_name', ''):<20} {item['age_minutes']}m ago"
            )
    else:
        print("\n  No pending pairing requests.")
    if approved:
        print(f"\n  Approved Users ({len(approved)}):")
        print(f"  {'Platform':<12} {'User ID':<20} {'Name':<20}")
        print(f"  {'--------':<12} {'-------':<20} {'----':<20}")
        for item in approved:
            print(f"  {item['platform']:<12} {item['user_id']:<20} {item.get('user_name', ''):<20}")
    else:
        print("\n  No approved users.")
    print()


def _cmd_approve(store: PairingStore, platform: str, code: str) -> None:
    result = store.approve_code(platform.lower().strip(), code.upper().strip())
    if result:
        user_id = result["user_id"]
        user_name = result.get("user_name", "")
        display = f"{user_name} ({user_id})" if user_name else user_id
        print(f"\n  Approved! User {display} on {platform} can now use the bot~")
        print("  They'll be recognized automatically on their next message.\n")
        return
    print(f"\n  Code '{code}' not found or expired for platform '{platform}'.")
    print("  Run 'io pairing list' to see pending codes.\n")


def _cmd_revoke(store: PairingStore, platform: str, user_id: str) -> None:
    if store.revoke(platform.lower().strip(), user_id):
        print(f"\n  Revoked access for user {user_id} on {platform}.\n")
        return
    print(f"\n  User {user_id} not found in approved list for {platform}.\n")


def _cmd_clear_pending(store: PairingStore) -> None:
    count = store.clear_pending()
    if count:
        print(f"\n  Cleared {count} pending pairing request(s).\n")
        return
    print("\n  No pending requests to clear.\n")
