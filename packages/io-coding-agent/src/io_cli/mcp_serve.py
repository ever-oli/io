"""Minimal MCP-compatible tool server for IO conversations and gateway state."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from io_agent import SessionDB

from . import __version__
from .approval_queue import ApprovalQueueStore
from .config import ensure_io_home
from .gateway import GatewayManager
from .gateway_control import GatewayControlService
from .pairing import PairingStore
from .skills_hub import SkillsHub, SkillsHubError

logger = logging.getLogger(__name__)

_ATTACHMENT_RE = re.compile(
    r"(MEDIA:\s*(?P<media>\S+))|(?P<url>https?://\S+\.(?:png|jpg|jpeg|gif|webp|pdf|txt|md|mp4|mp3|wav))|(?P<path>(?:~/|/)\S+\.(?:png|jpg|jpeg|gif|webp|pdf|txt|md|mp4|mp3|wav))",
    re.IGNORECASE,
)

_TOOLS = [
    {
        "name": "conversations_list",
        "description": "List indexed IO conversations from state.db and gateway sessions.",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    },
    {
        "name": "conversation_get",
        "description": "Get one conversation's metadata by session_id.",
        "inputSchema": {"type": "object", "properties": {"session_id": {"type": "string"}}, "required": ["session_id"]},
    },
    {
        "name": "messages_read",
        "description": "Read normalized messages for a conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "after_cursor": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "attachments_fetch",
        "description": "Extract attachment metadata from indexed conversation messages.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}, "message_id": {"type": "integer"}},
            "required": ["session_id"],
        },
    },
    {
        "name": "events_poll",
        "description": "Poll new message events from state.db after a cursor.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "after_cursor": {"type": "integer"},
                "session_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "name": "events_wait",
        "description": "Wait for the next message event from state.db.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "after_cursor": {"type": "integer"},
                "session_id": {"type": "string"},
                "timeout_ms": {"type": "integer"},
            },
        },
    },
    {
        "name": "skills_browse",
        "description": "Browse hub-backed skills from official, GitHub, and ClawHub sources.",
        "inputSchema": {
            "type": "object",
            "properties": {"source": {"type": "string"}},
        },
    },
    {
        "name": "skills_search",
        "description": "Search hub-backed skills.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "source": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "skills_inspect",
        "description": "Inspect one hub or local skill.",
        "inputSchema": {
            "type": "object",
            "properties": {"identifier": {"type": "string"}},
            "required": ["identifier"],
        },
    },
    {
        "name": "skills_install",
        "description": "Install a hub-backed skill into ~/.io/skills.",
        "inputSchema": {
            "type": "object",
            "properties": {"identifier": {"type": "string"}, "force": {"type": "boolean"}},
            "required": ["identifier"],
        },
    },
    {
        "name": "skills_list_installed",
        "description": "List hub-managed installed skills.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "messages_send",
        "description": "Send a gateway message through the shared adapter control path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "platform": {"type": "string"},
                "chat_id": {"type": "string"},
                "content": {"type": "string"},
                "reply_to": {"type": "string"},
                "thread_id": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "messages_edit",
        "description": "Edit a previously sent gateway message on platforms that support edits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "platform": {"type": "string"},
                "chat_id": {"type": "string"},
                "message_id": {"type": "string"},
                "content": {"type": "string"},
                "thread_id": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["message_id", "content"],
        },
    },
    {
        "name": "messages_typing",
        "description": "Send a typing indicator on platforms that support it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "platform": {"type": "string"},
                "chat_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "metadata": {"type": "object"},
            },
        },
    },
    {
        "name": "permissions_list_open",
        "description": "List pending tool or pairing approvals that can be resolved remotely.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "permissions_respond",
        "description": "Approve or deny a pending tool or pairing approval.",
        "inputSchema": {
            "type": "object",
            "properties": {"approval_id": {"type": "string"}, "decision": {"type": "string"}},
            "required": ["approval_id", "decision"],
        },
    },
    {
        "name": "channels_list",
        "description": "List configured gateway channels, runtime state, home channels, and capabilities.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "channel_set_home",
        "description": "Set the home channel for a gateway platform.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "platform": {"type": "string"},
                "chat_id": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
    {
        "name": "conversation_control",
        "description": "Run typed conversation controls such as new, retry, undo, status, and usage.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "session_id": {"type": "string"},
                "platform": {"type": "string"},
                "chat_id": {"type": "string"},
                "chat_type": {"type": "string"},
                "chat_name": {"type": "string"},
                "user_id": {"type": "string"},
                "user_name": {"type": "string"},
                "thread_id": {"type": "string"},
            },
            "required": ["action"],
        },
    },
]


def _safe_stdout_write(payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    message = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
    sys.stdout.buffer.write(message)
    sys.stdout.buffer.flush()


def _read_stdio_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            break
        if b":" in line:
            key, value = line.decode("utf-8", errors="replace").split(":", 1)
            headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0") or 0)
    if length <= 0:
        return None
    raw = sys.stdin.buffer.read(length)
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload if isinstance(payload, dict) else {"value": payload},
        "isError": is_error,
    }


class IOMCPBridge:
    def __init__(self, *, home: Path | None = None) -> None:
        self.home = ensure_io_home(home)
        self.db = SessionDB(self.home / "state.db")
        self.gateway_manager = GatewayManager(home=self.home)
        self.gateway_control = GatewayControlService(home=self.home)
        self.approval_store = ApprovalQueueStore(home=self.home)
        self.pairing_store = PairingStore(home=self.home)
        self.skills_hub = SkillsHub(home=self.home)

    def _gateway_entries(self) -> dict[str, dict[str, Any]]:
        entries: dict[str, dict[str, Any]] = {}
        for entry in self.gateway_manager.session_store().list_entries():
            payload = entry.to_dict()
            entries[str(entry.session_id)] = payload
        return entries

    @staticmethod
    def _parse_model_config(raw: Any) -> dict[str, Any]:
        if not raw:
            return {}
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            return dict(payload) if isinstance(payload, dict) else {}
        return {}

    @staticmethod
    def _metadata(raw: Any) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        return {str(key): value for key, value in raw.items()}

    def conversations_list(self, limit: int = 50) -> dict[str, Any]:
        gateway_entries = self._gateway_entries()
        rows = []
        for row in self.db.search_sessions(limit=max(1, int(limit or 50))):
            session_id = str(row.get("id") or "")
            model_config = self._parse_model_config(row.get("model_config"))
            gateway_entry = gateway_entries.get(session_id)
            rows.append(
                {
                    "session_id": session_id,
                    "source": row.get("source"),
                    "cwd": row.get("cwd"),
                    "title": row.get("title"),
                    "model": row.get("model"),
                    "message_count": row.get("message_count", 0),
                    "started_at": row.get("started_at"),
                    "route_kind": model_config.get("route_kind", "primary"),
                    "route_label": model_config.get("route_label", "primary"),
                    "platform": gateway_entry.get("platform") if isinstance(gateway_entry, dict) else None,
                    "origin": gateway_entry.get("origin") if isinstance(gateway_entry, dict) else None,
                }
            )
        return {"conversations": rows}

    def conversation_get(self, session_id: str) -> dict[str, Any]:
        row = self.db.get_session(session_id)
        if row is None:
            return {"error": f"Unknown session_id: {session_id}"}
        gateway_entry = self._gateway_entries().get(session_id)
        model_config = self._parse_model_config(row.get("model_config"))
        return {
            "session": row,
            "model_config": model_config,
            "gateway_entry": gateway_entry,
        }

    def messages_read(self, session_id: str, *, after_cursor: int = 0, limit: int = 100) -> dict[str, Any]:
        rows = []
        with self.db.connection() as connection:
            results = connection.execute(
                """
                SELECT id, role, content, tool_name, tool_call_id, payload_json, timestamp
                FROM messages
                WHERE session_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (session_id, int(after_cursor or 0), max(1, int(limit or 100))),
            ).fetchall()
        for row in results:
            payload = {}
            raw = row["payload_json"]
            if raw:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {}
            rows.append(
                {
                    "cursor": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "tool_name": row["tool_name"],
                    "tool_call_id": row["tool_call_id"],
                    "timestamp": row["timestamp"],
                    "payload": payload,
                }
            )
        return {"messages": rows, "next_cursor": rows[-1]["cursor"] if rows else int(after_cursor or 0)}

    def attachments_fetch(self, session_id: str, *, message_id: int | None = None) -> dict[str, Any]:
        payload = self.messages_read(session_id, after_cursor=max(0, (message_id or 1) - 1), limit=500)
        attachments: list[dict[str, Any]] = []
        for message in payload.get("messages", []):
            if message_id is not None and int(message.get("cursor", 0)) != int(message_id):
                continue
            text = str(message.get("content", "") or "")
            for match in _ATTACHMENT_RE.finditer(text):
                value = (
                    match.group("media")
                    or match.group("url")
                    or match.group("path")
                    or ""
                )
                if not value:
                    continue
                path = Path(value).expanduser() if value.startswith(("~/", "/")) else None
                attachments.append(
                    {
                        "message_id": message.get("cursor"),
                        "value": value,
                        "exists": path.exists() if path else None,
                        "size": path.stat().st_size if path and path.exists() else None,
                    }
                )
        return {"attachments": attachments}

    def events_poll(self, *, after_cursor: int = 0, session_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        query = """
            SELECT id, session_id, role, content, tool_name, tool_call_id, timestamp
            FROM messages
            WHERE id > ?
        """
        params: list[Any] = [int(after_cursor or 0)]
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY id ASC LIMIT ?"
        params.append(max(1, int(limit or 20)))
        with self.db.connection() as connection:
            rows = connection.execute(query, params).fetchall()
        events = [
            {
                "cursor": row["id"],
                "type": "message",
                "session_id": row["session_id"],
                "role": row["role"],
                "content": row["content"],
                "tool_name": row["tool_name"],
                "tool_call_id": row["tool_call_id"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]
        return {"events": events, "next_cursor": events[-1]["cursor"] if events else int(after_cursor or 0)}

    def events_wait(
        self,
        *,
        after_cursor: int = 0,
        session_id: str | None = None,
        timeout_ms: int = 30000,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + (max(1, int(timeout_ms or 30000)) / 1000.0)
        while time.monotonic() < deadline:
            payload = self.events_poll(after_cursor=after_cursor, session_id=session_id, limit=1)
            if payload["events"]:
                return payload
            time.sleep(0.2)
        return {"events": [], "next_cursor": int(after_cursor or 0), "timed_out": True}

    def skills_browse(self, *, source: str = "all") -> dict[str, Any]:
        try:
            return self.skills_hub.browse(source=source)
        except SkillsHubError as exc:
            return {"error": str(exc)}

    def skills_search(self, query: str, *, source: str = "all") -> dict[str, Any]:
        try:
            return self.skills_hub.search(query, source=source)
        except SkillsHubError as exc:
            return {"error": str(exc)}

    def skills_inspect(self, identifier: str) -> dict[str, Any]:
        try:
            return self.skills_hub.inspect(identifier)
        except SkillsHubError as exc:
            return {"error": str(exc)}

    def skills_install(self, identifier: str, *, force: bool = False) -> dict[str, Any]:
        try:
            return self.skills_hub.install(identifier, force=force)
        except SkillsHubError as exc:
            return {"error": str(exc)}

    def skills_list_installed(self) -> dict[str, Any]:
        return self.skills_hub.list_installed()

    def channels_list(self) -> dict[str, Any]:
        return self.gateway_control.channels_list()

    def permissions_list_open(self) -> dict[str, Any]:
        pending = []
        for item in self.approval_store.list_pending():
            pending.append({**item, "approval_id": f"approval:{item['approval_id']}"})
        for item in self.pairing_store.list_pending():
            pending.append(
                {
                    "approval_id": f"pairing:{item['platform']}:{item['code']}",
                    "kind": "pairing",
                    "platform": item["platform"],
                    "code": item["code"],
                    "user_id": item["user_id"],
                    "user_name": item.get("user_name"),
                    "age_minutes": item.get("age_minutes"),
                }
            )
        return {"permissions": pending}

    def permissions_respond(self, approval_id: str, decision: str) -> dict[str, Any]:
        if approval_id.startswith("approval:"):
            normalized_id = approval_id.split(":", 1)[1]
            responded = self.approval_store.respond(normalized_id, decision)
            if responded is None:
                return {"error": f"Approval not found: {approval_id}"}
            return {
                "approved": responded["decision"] in {"allow_once", "allow_always"},
                "approval_id": approval_id,
                "result": responded,
            }
        if not approval_id.startswith("pairing:"):
            return {"error": f"Unsupported approval_id: {approval_id}"}
        _prefix, platform, code = approval_id.split(":", 2)
        normalized = decision.strip().lower()
        if normalized in {"allow", "approve", "allow_once", "allow_always"}:
            approved = self.pairing_store.approve_code(platform, code)
            if approved is None:
                return {"error": f"Pairing code not found: {approval_id}"}
            return {"approved": True, "approval_id": approval_id, "result": approved}
        denied = self.pairing_store.deny_code(platform, code)
        if not denied:
            return {"error": f"Pairing code not found: {approval_id}"}
        return {"approved": False, "approval_id": approval_id}

    async def messages_send(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        content: str,
        reply_to: str | None = None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.gateway_control.messages_send(
                session_id=session_id,
                platform=platform,
                chat_id=chat_id,
                content=content,
                reply_to=reply_to,
                thread_id=thread_id,
                metadata=metadata,
            )
        except Exception as exc:
            return {"error": str(exc)}

    async def messages_edit(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        message_id: str,
        content: str,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.gateway_control.messages_edit(
                session_id=session_id,
                platform=platform,
                chat_id=chat_id,
                message_id=message_id,
                content=content,
                thread_id=thread_id,
                metadata=metadata,
            )
        except Exception as exc:
            return {"error": str(exc)}

    async def messages_typing(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        thread_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.gateway_control.messages_typing(
                session_id=session_id,
                platform=platform,
                chat_id=chat_id,
                thread_id=thread_id,
                metadata=metadata,
            )
        except Exception as exc:
            return {"error": str(exc)}

    def channel_set_home(
        self,
        *,
        session_id: str | None,
        platform: str | None,
        chat_id: str | None,
        name: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.gateway_control.channel_set_home(
                session_id=session_id,
                platform=platform,
                chat_id=chat_id,
                name=name,
            )
        except Exception as exc:
            return {"error": str(exc)}

    async def conversation_control(
        self,
        *,
        action: str,
        session_id: str | None = None,
        platform: str | None = None,
        chat_id: str | None = None,
        chat_type: str | None = None,
        chat_name: str | None = None,
        user_id: str | None = None,
        user_name: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return await self.gateway_control.conversation_control(
                action=action,
                session_id=session_id,
                platform=platform,
                chat_id=chat_id,
                chat_type=chat_type,
                chat_name=chat_name,
                user_id=user_id,
                user_name=user_name,
                thread_id=thread_id,
            )
        except Exception as exc:
            return {"error": str(exc)}

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, bool]:
        handlers = {
            "conversations_list": lambda: self.conversations_list(limit=arguments.get("limit", 50)),
            "conversation_get": lambda: self.conversation_get(str(arguments.get("session_id", ""))),
            "messages_read": lambda: self.messages_read(
                str(arguments.get("session_id", "")),
                after_cursor=int(arguments.get("after_cursor", 0) or 0),
                limit=int(arguments.get("limit", 100) or 100),
            ),
            "attachments_fetch": lambda: self.attachments_fetch(
                str(arguments.get("session_id", "")),
                message_id=int(arguments["message_id"]) if arguments.get("message_id") is not None else None,
            ),
            "events_poll": lambda: self.events_poll(
                after_cursor=int(arguments.get("after_cursor", 0) or 0),
                session_id=str(arguments.get("session_id", "") or "") or None,
                limit=int(arguments.get("limit", 20) or 20),
            ),
            "events_wait": lambda: self.events_wait(
                after_cursor=int(arguments.get("after_cursor", 0) or 0),
                session_id=str(arguments.get("session_id", "") or "") or None,
                timeout_ms=int(arguments.get("timeout_ms", 30000) or 30000),
            ),
            "skills_browse": lambda: self.skills_browse(
                source=str(arguments.get("source", "all") or "all"),
            ),
            "skills_search": lambda: self.skills_search(
                str(arguments.get("query", "") or ""),
                source=str(arguments.get("source", "all") or "all"),
            ),
            "skills_inspect": lambda: self.skills_inspect(str(arguments.get("identifier", "") or "")),
            "skills_install": lambda: self.skills_install(
                str(arguments.get("identifier", "") or ""),
                force=bool(arguments.get("force", False)),
            ),
            "skills_list_installed": self.skills_list_installed,
            "permissions_list_open": self.permissions_list_open,
            "permissions_respond": lambda: self.permissions_respond(
                str(arguments.get("approval_id", "")),
                str(arguments.get("decision", "")),
            ),
            "channels_list": self.channels_list,
            "channel_set_home": lambda: self.channel_set_home(
                session_id=str(arguments.get("session_id", "") or "") or None,
                platform=str(arguments.get("platform", "") or "") or None,
                chat_id=str(arguments.get("chat_id", "") or "") or None,
                name=str(arguments.get("name", "") or "") or None,
            ),
        }
        if name == "messages_send":
            payload = await self.messages_send(
                session_id=str(arguments.get("session_id", "") or "") or None,
                platform=str(arguments.get("platform", "") or "") or None,
                chat_id=str(arguments.get("chat_id", "") or "") or None,
                content=str(arguments.get("content", "") or ""),
                reply_to=str(arguments.get("reply_to", "") or "") or None,
                thread_id=str(arguments.get("thread_id", "") or "") or None,
                metadata=self._metadata(arguments.get("metadata")),
            )
            return payload, bool(payload.get("error"))
        if name == "messages_edit":
            payload = await self.messages_edit(
                session_id=str(arguments.get("session_id", "") or "") or None,
                platform=str(arguments.get("platform", "") or "") or None,
                chat_id=str(arguments.get("chat_id", "") or "") or None,
                message_id=str(arguments.get("message_id", "") or ""),
                content=str(arguments.get("content", "") or ""),
                thread_id=str(arguments.get("thread_id", "") or "") or None,
                metadata=self._metadata(arguments.get("metadata")),
            )
            return payload, bool(payload.get("error"))
        if name == "messages_typing":
            payload = await self.messages_typing(
                session_id=str(arguments.get("session_id", "") or "") or None,
                platform=str(arguments.get("platform", "") or "") or None,
                chat_id=str(arguments.get("chat_id", "") or "") or None,
                thread_id=str(arguments.get("thread_id", "") or "") or None,
                metadata=self._metadata(arguments.get("metadata")),
            )
            return payload, bool(payload.get("error"))
        if name == "conversation_control":
            payload = await self.conversation_control(
                action=str(arguments.get("action", "") or ""),
                session_id=str(arguments.get("session_id", "") or "") or None,
                platform=str(arguments.get("platform", "") or "") or None,
                chat_id=str(arguments.get("chat_id", "") or "") or None,
                chat_type=str(arguments.get("chat_type", "") or "") or None,
                chat_name=str(arguments.get("chat_name", "") or "") or None,
                user_id=str(arguments.get("user_id", "") or "") or None,
                user_name=str(arguments.get("user_name", "") or "") or None,
                thread_id=str(arguments.get("thread_id", "") or "") or None,
            )
            return payload, bool(payload.get("error"))
        handler = handlers.get(name)
        if handler is None:
            return {"error": f"Unknown tool: {name}"}, True
        try:
            payload = handler()
        except Exception as exc:
            return {"error": str(exc)}, True
        return payload, bool(isinstance(payload, dict) and payload.get("error"))


def _dispatch_request(bridge: IOMCPBridge, request: dict[str, Any]) -> dict[str, Any] | None:
    method = str(request.get("method") or "")
    request_id = request.get("id")

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2025-06-18",
                "serverInfo": {"name": "io-mcp", "version": __version__},
                "capabilities": {"tools": {"listChanged": False}},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": list(_TOOLS)}}
    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}
        payload, is_error = _run_async_tool(bridge, name, arguments)
        return {"jsonrpc": "2.0", "id": request_id, "result": _tool_result(payload, is_error=is_error)}
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def _run_async_tool(bridge: IOMCPBridge, name: str, arguments: dict[str, Any]) -> tuple[Any, bool]:
    import asyncio

    return asyncio.run(bridge.call_tool(name, arguments))


def _serve_stdio(bridge: IOMCPBridge) -> int:
    while True:
        request = _read_stdio_message()
        if request is None:
            return 0
        response = _dispatch_request(bridge, request)
        if response is not None:
            _safe_stdout_write(response)


def _serve_http(bridge: IOMCPBridge, *, host: str, port: int) -> int:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0") or 0)
            raw = self.rfile.read(length)
            request = json.loads(raw.decode("utf-8"))
            response = _dispatch_request(bridge, request)
            body = json.dumps(response or {"ok": True}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            logger.debug(format, *args)

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


def serve_mcp(
    *,
    home: Path | None = None,
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8765,
    verbose: bool = False,
) -> int:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    bridge = IOMCPBridge(home=home)
    if transport == "stdio":
        return _serve_stdio(bridge)
    return _serve_http(bridge, host=host, port=port)
