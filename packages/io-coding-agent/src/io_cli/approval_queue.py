"""File-backed remote approval queue for dangerous tool executions."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from .config import atomic_write_json, ensure_io_home

_DECISION_ALLOW = {"allow", "approve", "allow_once", "allow_always"}


class ApprovalQueueStore:
    def __init__(self, *, home: Path | None = None) -> None:
        self.home = ensure_io_home(home)
        self.approvals_dir = self.home / "approvals"
        self.approvals_dir.mkdir(parents=True, exist_ok=True)

    @property
    def pending_path(self) -> Path:
        return self.approvals_dir / "pending.json"

    @property
    def policies_path(self) -> Path:
        return self.approvals_dir / "policies.json"

    def _load_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_json(self, path: Path, payload: dict[str, Any]) -> None:
        atomic_write_json(path, payload, indent=2, sort_keys=True, chmod=0o600)

    @staticmethod
    def _policy_key(tool_name: str, arguments: dict[str, Any]) -> str:
        canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(f"{tool_name}:{canonical}".encode("utf-8")).hexdigest()
        return digest

    def policy_decision(self, tool_name: str, arguments: dict[str, Any]) -> str | None:
        policies = self._load_json(self.policies_path)
        entry = policies.get(self._policy_key(tool_name, arguments))
        if isinstance(entry, dict):
            decision = str(entry.get("decision", "") or "").strip().lower()
            if decision:
                return decision
        return None

    def list_pending(self) -> list[dict[str, Any]]:
        payload = self._load_json(self.pending_path)
        rows: list[dict[str, Any]] = []
        now = time.time()
        for approval_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            decision = str(item.get("decision", "") or "").strip().lower()
            if decision:
                continue
            created_at = float(item.get("created_at", 0) or 0)
            rows.append(
                {
                    "approval_id": approval_id,
                    "kind": "tool",
                    "session_id": item.get("session_id"),
                    "tool_name": item.get("tool_name"),
                    "arguments": item.get("arguments", {}),
                    "reason": item.get("reason"),
                    "age_seconds": max(0, int(now - created_at)),
                    "created_at": created_at,
                }
            )
        rows.sort(key=lambda item: float(item.get("created_at", 0) or 0))
        return rows

    def request_approval(
        self,
        *,
        session_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        reason: str,
        timeout_seconds: float = 60.0,
        poll_interval: float = 0.25,
    ) -> str:
        policy = self.policy_decision(tool_name, arguments)
        if policy in {"allow_always", "deny_always"}:
            return policy

        approval_id = uuid.uuid4().hex[:16]
        pending = self._load_json(self.pending_path)
        pending[approval_id] = {
            "session_id": session_id,
            "tool_name": tool_name,
            "arguments": arguments,
            "reason": reason,
            "policy_key": self._policy_key(tool_name, arguments),
            "created_at": time.time(),
        }
        self._save_json(self.pending_path, pending)

        deadline = time.time() + max(0.1, float(timeout_seconds))
        while time.time() < deadline:
            current = self._load_json(self.pending_path)
            item = current.get(approval_id)
            if not isinstance(item, dict):
                return "deny"
            decision = str(item.get("decision", "") or "").strip().lower()
            if not decision:
                time.sleep(max(0.05, float(poll_interval)))
                continue
            if decision == "allow_always":
                policies = self._load_json(self.policies_path)
                policies[str(item.get("policy_key") or "")] = {
                    "decision": "allow_always",
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "updated_at": time.time(),
                }
                self._save_json(self.policies_path, policies)
            current.pop(approval_id, None)
            self._save_json(self.pending_path, current)
            return decision

        current = self._load_json(self.pending_path)
        if approval_id in current:
            current.pop(approval_id, None)
            self._save_json(self.pending_path, current)
        return "deny"

    def respond(self, approval_id: str, decision: str) -> dict[str, Any] | None:
        payload = self._load_json(self.pending_path)
        item = payload.get(approval_id)
        if not isinstance(item, dict):
            return None
        normalized = str(decision or "").strip().lower()
        if normalized in _DECISION_ALLOW:
            normalized = "allow_always" if normalized == "allow_always" else "allow_once"
        else:
            normalized = "deny"
        item["decision"] = normalized
        item["resolved_at"] = time.time()
        payload[approval_id] = item
        self._save_json(self.pending_path, payload)
        return {
            "approval_id": approval_id,
            "decision": normalized,
            "session_id": item.get("session_id"),
            "tool_name": item.get("tool_name"),
            "arguments": item.get("arguments", {}),
        }
