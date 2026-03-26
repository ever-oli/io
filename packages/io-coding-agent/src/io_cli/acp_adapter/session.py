"""ACP session manager for IO."""

from __future__ import annotations

import copy
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Lock
from typing import Any

from io_agent import SessionDB

from ..config import ensure_io_home
from ..main import run_prompt
from ..session import SessionManager as JsonlSessionManager


logger = logging.getLogger(__name__)


def _entry_id() -> str:
    return uuid.uuid4().hex[:8]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ACPAgentProxy:
    home: Path
    session_id: str
    session_file: Path
    cwd: str = "."
    model: str = ""
    provider: str | None = None
    enabled_toolsets: list[str] = field(default_factory=lambda: ["io-acp"])
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False

    def interrupt(self) -> None:
        self.cancelled = True

    async def run_conversation(
        self,
        *,
        user_message: str,
        conversation_history: list[dict[str, Any]] | None = None,
        task_id: str,
    ) -> dict[str, Any]:
        del conversation_history
        result = await run_prompt(
            user_message,
            cwd=Path(self.cwd),
            home=self.home,
            model=self.model or None,
            provider=self.provider,
            session_path=self.session_file,
            toolsets=list(self.enabled_toolsets),
            load_extensions=True,
            env_overrides={
                "IO_SESSION_ID": task_id or self.session_id,
                "IO_MCP_SERVERS": json.dumps(self.mcp_servers, ensure_ascii=False),
            },
            session_source="acp",
        )
        history = JsonlSessionManager.open(self.session_file).build_session_context()
        self.model = result.model
        self.provider = result.provider
        return {
            "final_response": result.text,
            "messages": history,
            "usage": {
                "prompt_tokens": int(result.usage.input_tokens or 0),
                "completion_tokens": int(result.usage.output_tokens or 0),
                "total_tokens": int((result.usage.input_tokens or 0) + (result.usage.output_tokens or 0)),
                "reasoning_tokens": int(result.usage.reasoning_tokens or 0),
                "cached_tokens": int(result.usage.cache_read_tokens or 0),
            },
        }


@dataclass
class SessionState:
    session_id: str
    agent: Any
    session_file: Path
    cwd: str = "."
    model: str = ""
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    cancel_event: Event | None = None


class SessionManager:
    """Thread-safe ACP session manager backed by IO SessionDB."""

    def __init__(self, home: Path | None = None, agent_factory=None, db: SessionDB | None = None):
        self.home = ensure_io_home(home)
        self.sessions_root = self.home / "acp" / "sessions"
        self.sessions_root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, SessionState] = {}
        self._lock = Lock()
        self._agent_factory = agent_factory
        self._db_instance = db or SessionDB(self.home / "state.db")

    def _session_file(self, session_id: str) -> Path:
        return self.sessions_root / f"{session_id}.jsonl"

    def create_session(self, cwd: str = ".", mcp_servers: list[dict[str, Any]] | None = None) -> SessionState:
        session_id = str(uuid.uuid4())
        session_file = self._session_file(session_id)
        JsonlSessionManager.create_at_path(Path(cwd), session_file=session_file, session_id=session_id)
        agent = self._make_agent(
            session_id=session_id,
            cwd=cwd,
            session_file=session_file,
            mcp_servers=list(mcp_servers or []),
        )
        state = SessionState(
            session_id=session_id,
            agent=agent,
            session_file=session_file,
            cwd=str(cwd),
            model=str(getattr(agent, "model", "") or ""),
            mcp_servers=list(mcp_servers or []),
            history=[],
            cancel_event=Event(),
        )
        with self._lock:
            self._sessions[session_id] = state
        self._persist(state)
        return state

    def get_session(self, session_id: str) -> SessionState | None:
        with self._lock:
            state = self._sessions.get(session_id)
        if state is not None:
            return state
        return self._restore(session_id)

    def remove_session(self, session_id: str) -> bool:
        with self._lock:
            state = self._sessions.pop(session_id, None)
        if state is not None:
            state.session_file.unlink(missing_ok=True)
        deleted = self._delete_persisted(session_id)
        return state is not None or deleted

    def fork_session(
        self,
        session_id: str,
        cwd: str = ".",
        mcp_servers: list[dict[str, Any]] | None = None,
    ) -> SessionState | None:
        original = self.get_session(session_id)
        if original is None:
            return None
        new_id = str(uuid.uuid4())
        session_file = self._session_file(new_id)
        agent = self._make_agent(
            session_id=new_id,
            cwd=cwd,
            model=original.model or None,
            session_file=session_file,
            mcp_servers=list(mcp_servers or original.mcp_servers),
        )
        state = SessionState(
            session_id=new_id,
            agent=agent,
            session_file=session_file,
            cwd=str(cwd),
            model=str(getattr(agent, "model", original.model) or original.model or ""),
            mcp_servers=list(mcp_servers or original.mcp_servers),
            history=copy.deepcopy(original.history),
            cancel_event=Event(),
        )
        with self._lock:
            self._sessions[new_id] = state
        self._persist(state)
        return state

    def list_sessions(self) -> list[dict[str, Any]]:
        with self._lock:
            seen_ids = set(self._sessions.keys())
            results = [
                {
                    "session_id": state.session_id,
                    "cwd": state.cwd,
                    "model": state.model,
                    "mcp_servers": list(state.mcp_servers),
                    "history_len": len(state.history),
                    "session_file": str(state.session_file),
                }
                for state in self._sessions.values()
            ]
        for row in self._get_db().search_sessions(source="acp", limit=1000):
            session_id = str(row["id"])
            if session_id in seen_ids:
                continue
            model_config = self._parse_model_config(row.get("model_config"))
            results.append(
                {
                    "session_id": session_id,
                    "cwd": model_config.get("cwd", row.get("cwd") or "."),
                    "model": row.get("model") or "",
                    "mcp_servers": model_config.get("mcp_servers") or [],
                    "history_len": row.get("message_count") or 0,
                    "session_file": model_config.get("session_file") or str(self._session_file(session_id)),
                }
            )
        return results

    def update_cwd(self, session_id: str, cwd: str) -> SessionState | None:
        state = self.get_session(session_id)
        if state is None:
            return None
        state.cwd = str(cwd)
        if hasattr(state.agent, "cwd"):
            state.agent.cwd = str(cwd)
        self._persist(state)
        return state

    def update_mcp_servers(self, session_id: str, mcp_servers: list[dict[str, Any]] | None) -> SessionState | None:
        state = self.get_session(session_id)
        if state is None:
            return None
        state.mcp_servers = list(mcp_servers or [])
        if hasattr(state.agent, "mcp_servers"):
            state.agent.mcp_servers = list(state.mcp_servers)
        self._persist(state)
        return state

    def cleanup(self) -> None:
        with self._lock:
            session_ids = list(self._sessions.keys())
            states = list(self._sessions.values())
            self._sessions.clear()
        for state in states:
            state.session_file.unlink(missing_ok=True)
        for session_id in session_ids:
            self._delete_persisted(session_id)
        for row in self._get_db().search_sessions(source="acp", limit=10000):
            self._delete_persisted(str(row["id"]))

    def save_session(self, session_id: str) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
        if state is not None:
            self._persist(state)

    def _get_db(self) -> SessionDB:
        return self._db_instance

    def _persist(self, state: SessionState) -> None:
        self._rewrite_session_file(state)
        model_str = str(state.model or getattr(state.agent, "model", "") or "")
        self._get_db().create_session(
            session_id=state.session_id,
            source="acp",
            model=model_str,
            cwd=state.cwd,
            model_config={
                "cwd": state.cwd,
                "session_file": str(state.session_file),
                "mcp_servers": state.mcp_servers,
            },
        )
        self._get_db().clear_messages(state.session_id)
        for message in state.history:
            self._get_db().append_message(
                state.session_id,
                role=str(message.get("role", "user")),
                content=message.get("content"),
                tool_name=message.get("tool_name") or message.get("name"),
                tool_calls=message.get("tool_calls"),
                tool_call_id=message.get("tool_call_id"),
                payload=message,
            )

    def _restore(self, session_id: str) -> SessionState | None:
        row = self._get_db().get_session(session_id)
        if row is None or row.get("source") != "acp":
            return None
        model_config = self._parse_model_config(row.get("model_config"))
        cwd = str(model_config.get("cwd", row.get("cwd") or "."))
        session_file = Path(str(model_config.get("session_file") or self._session_file(session_id)))
        history = self._load_history(session_file)
        if not history:
            history = self._get_db().get_messages_as_conversation(session_id)
        agent = self._make_agent(
            session_id=session_id,
            cwd=cwd,
            model=row.get("model") or None,
            session_file=session_file,
            mcp_servers=model_config.get("mcp_servers") if isinstance(model_config.get("mcp_servers"), list) else None,
        )
        state = SessionState(
            session_id=session_id,
            agent=agent,
            session_file=session_file,
            cwd=cwd,
            model=str(row.get("model") or getattr(agent, "model", "") or ""),
            mcp_servers=model_config.get("mcp_servers") if isinstance(model_config.get("mcp_servers"), list) else [],
            history=history,
            cancel_event=Event(),
        )
        with self._lock:
            self._sessions[session_id] = state
        return state

    def _delete_persisted(self, session_id: str) -> bool:
        row = self._get_db().get_session(session_id)
        if row is not None:
            model_config = self._parse_model_config(row.get("model_config"))
            session_file = model_config.get("session_file")
            if session_file:
                Path(str(session_file)).unlink(missing_ok=True)
        return self._get_db().delete_session(session_id)

    def _make_agent(
        self,
        *,
        session_id: str,
        cwd: str,
        model: str | None = None,
        session_file: Path | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
    ):
        if self._agent_factory is not None:
            return self._agent_factory()
        return ACPAgentProxy(
            home=self.home,
            session_id=session_id,
            session_file=session_file or self._session_file(session_id),
            cwd=str(cwd),
            model=model or "",
            mcp_servers=list(mcp_servers or []),
        )

    @staticmethod
    def _parse_model_config(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
        return {}

    @staticmethod
    def _load_history(session_file: Path) -> list[dict[str, Any]]:
        if not session_file.exists():
            return []
        try:
            return JsonlSessionManager.open(session_file).build_session_context()
        except Exception:
            logger.debug("Failed to load ACP session file %s", session_file, exc_info=True)
            return []

    def _rewrite_session_file(self, state: SessionState) -> None:
        state.session_file.parent.mkdir(parents=True, exist_ok=True)
        header = {
            "type": "session",
            "version": 3,
            "id": state.session_id,
            "timestamp": _timestamp(),
            "cwd": str(Path(state.cwd).resolve()),
        }
        parent_id: str | None = None
        lines = [json.dumps(header, sort_keys=True)]
        for message in state.history:
            entry = {
                "type": "message",
                "id": _entry_id(),
                "parentId": parent_id,
                "timestamp": _timestamp(),
                "message": message,
            }
            parent_id = entry["id"]
            lines.append(json.dumps(entry, sort_keys=True))
        state.session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
