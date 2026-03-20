"""ACP server exposing IO through the Agent Client Protocol."""

from __future__ import annotations

import inspect
import logging
from typing import Any

import acp
from acp.schema import (
    AgentCapabilities,
    AuthenticateResponse,
    AuthMethod,
    ClientCapabilities,
    EmbeddedResourceContentBlock,
    ImageContentBlock,
    AudioContentBlock,
    Implementation,
    InitializeResponse,
    ListSessionsResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PromptResponse,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionForkCapabilities,
    SessionInfo,
    SessionListCapabilities,
    TextContentBlock,
    ResourceContentBlock,
    ForkSessionResponse,
    Usage,
)

from io_agent import ContextCompressor

from .. import __version__ as IO_VERSION
from ..toolsets import build_toolset_resolver
from ..tools.registry import get_tool_registry
from .auth import detect_provider, has_provider
from .session import SessionManager, SessionState


logger = logging.getLogger(__name__)


def _extract_text(
    prompt: list[
        TextContentBlock
        | ImageContentBlock
        | AudioContentBlock
        | ResourceContentBlock
        | EmbeddedResourceContentBlock
    ],
) -> str:
    parts: list[str] = []
    for block in prompt:
        if isinstance(block, TextContentBlock):
            parts.append(block.text)
        elif hasattr(block, "text"):
            parts.append(str(block.text))
    return "\n".join(parts)


class IOACPAgent(acp.Agent):
    """ACP Agent implementation wrapping IO."""

    _SLASH_COMMANDS = {
        "help": "Show available commands",
        "model": "Show or change current model",
        "tools": "List available tools",
        "context": "Show conversation context info",
        "reset": "Clear conversation history",
        "compact": "Compress conversation context",
        "version": "Show IO version",
    }

    def __init__(self, session_manager: SessionManager | None = None):
        super().__init__()
        self.session_manager = session_manager or SessionManager()
        self._conn: acp.Client | None = None

    def on_connect(self, conn: acp.Client) -> None:
        self._conn = conn
        logger.info("ACP client connected")

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        del client_capabilities, kwargs
        provider = detect_provider(home=self.session_manager.home)
        auth_methods = None
        if provider:
            auth_methods = [
                AuthMethod(
                    id=provider,
                    name=f"{provider} runtime credentials",
                    description=f"Authenticate IO using the currently configured {provider} runtime credentials.",
                )
            ]
        client_name = client_info.name if client_info else "unknown"
        logger.info("Initialize from %s (protocol v%s)", client_name, protocol_version)
        return InitializeResponse(
            protocol_version=acp.PROTOCOL_VERSION,
            agent_info=Implementation(name="io-agent", version=IO_VERSION),
            agent_capabilities=AgentCapabilities(
                session_capabilities=SessionCapabilities(
                    fork=SessionForkCapabilities(),
                    list=SessionListCapabilities(),
                ),
            ),
            auth_methods=auth_methods,
        )

    async def authenticate(self, method_id: str, **kwargs: Any) -> AuthenticateResponse | None:
        del method_id, kwargs
        if has_provider(home=self.session_manager.home):
            return AuthenticateResponse()
        return None

    async def new_session(self, cwd: str, mcp_servers: list | None = None, **kwargs: Any) -> NewSessionResponse:
        del mcp_servers, kwargs
        state = self.session_manager.create_session(cwd=cwd)
        return NewSessionResponse(session_id=state.session_id)

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list | None = None,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        del mcp_servers, kwargs
        state = self.session_manager.update_cwd(session_id, cwd)
        if state is None:
            return None
        return LoadSessionResponse()

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list | None = None,
        **kwargs: Any,
    ) -> ResumeSessionResponse:
        del mcp_servers, kwargs
        state = self.session_manager.update_cwd(session_id, cwd)
        if state is None:
            state = self.session_manager.create_session(cwd=cwd)
        return ResumeSessionResponse()

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        del kwargs
        state = self.session_manager.get_session(session_id)
        if state and state.cancel_event:
            state.cancel_event.set()
            if hasattr(state.agent, "interrupt"):
                state.agent.interrupt()

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list | None = None,
        **kwargs: Any,
    ) -> ForkSessionResponse:
        del mcp_servers, kwargs
        state = self.session_manager.fork_session(session_id, cwd=cwd)
        return ForkSessionResponse(session_id=state.session_id if state else "")

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ) -> ListSessionsResponse:
        del cursor, cwd, kwargs
        sessions = [
            SessionInfo(session_id=entry["session_id"], cwd=entry["cwd"])
            for entry in self.session_manager.list_sessions()
        ]
        return ListSessionsResponse(sessions=sessions)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        del kwargs
        state = self.session_manager.get_session(session_id)
        if state is None:
            logger.error("prompt: session %s not found", session_id)
            return PromptResponse(stop_reason="refusal")

        user_text = _extract_text(prompt).strip()
        if not user_text:
            return PromptResponse(stop_reason="end_turn")

        if user_text.startswith("/"):
            response_text = self._handle_slash_command(user_text, state)
            if response_text is not None:
                if self._conn is not None:
                    await self._conn.session_update(session_id, acp.update_agent_message_text(response_text))
                return PromptResponse(stop_reason="end_turn")

        try:
            result = state.agent.run_conversation(
                user_message=user_text,
                conversation_history=state.history,
                task_id=session_id,
            )
            if inspect.isawaitable(result):
                result = await result
        except Exception as exc:
            logger.exception("ACP agent failed for session %s", session_id)
            result = {"final_response": f"Error: {exc}", "messages": state.history}

        if isinstance(result, dict) and result.get("messages") is not None:
            state.history = list(result.get("messages") or [])
            state.model = str(result.get("model") or getattr(state.agent, "model", state.model) or state.model)
            self.session_manager.save_session(session_id)

        final_response = str(result.get("final_response", "") if isinstance(result, dict) else "")
        if final_response and self._conn is not None:
            await self._conn.session_update(session_id, acp.update_agent_message_text(final_response))

        stop_reason = "cancelled" if state.cancel_event and state.cancel_event.is_set() else "end_turn"
        return PromptResponse(stop_reason=stop_reason, usage=self._build_usage(result))

    def _build_usage(self, result: Any) -> Usage | None:
        if not isinstance(result, dict):
            return None
        usage = result.get("usage")
        if not usage:
            return None
        if hasattr(usage, "input_tokens"):
            return Usage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                total_tokens=int((getattr(usage, "input_tokens", 0) or 0) + (getattr(usage, "output_tokens", 0) or 0)),
                thought_tokens=int(getattr(usage, "reasoning_tokens", 0) or 0),
                cached_read_tokens=int(getattr(usage, "cache_read_tokens", 0) or 0),
            )
        if isinstance(usage, dict):
            return Usage(
                input_tokens=int(usage.get("prompt_tokens", 0) or 0),
                output_tokens=int(usage.get("completion_tokens", 0) or 0),
                total_tokens=int(usage.get("total_tokens", 0) or 0),
                thought_tokens=int(usage.get("reasoning_tokens", 0) or 0),
                cached_read_tokens=int(usage.get("cached_tokens", 0) or 0),
            )
        return None

    def _handle_slash_command(self, text: str, state: SessionState) -> str | None:
        parts = text.split(maxsplit=1)
        command = parts[0].lstrip("/").lower()
        args = parts[1].strip() if len(parts) > 1 else ""
        handler = {
            "help": self._cmd_help,
            "model": self._cmd_model,
            "tools": self._cmd_tools,
            "context": self._cmd_context,
            "reset": self._cmd_reset,
            "compact": self._cmd_compact,
            "version": self._cmd_version,
        }.get(command)
        if handler is None:
            return None
        return handler(args, state)

    def _cmd_help(self, args: str, state: SessionState) -> str:
        del args, state
        lines = ["Available commands:", ""]
        for command, description in self._SLASH_COMMANDS.items():
            lines.append(f"  /{command:10s}  {description}")
        lines.append("")
        lines.append("Unrecognized /commands are sent to the model as normal messages.")
        return "\n".join(lines)

    def _cmd_model(self, args: str, state: SessionState) -> str:
        if not args:
            provider = getattr(state.agent, "provider", None) or "auto"
            return f"Current model: {state.model or getattr(state.agent, 'model', 'unknown')}\nProvider: {provider}"
        state.model = args.strip()
        state.agent = self.session_manager._make_agent(
            session_id=state.session_id,
            cwd=state.cwd,
            model=state.model,
            session_file=state.session_file,
        )
        self.session_manager.save_session(state.session_id)
        provider = getattr(state.agent, "provider", None) or "auto"
        return f"Model switched to: {state.model}\nProvider: {provider}"

    def _cmd_tools(self, args: str, state: SessionState) -> str:
        del args
        registry = get_tool_registry()
        resolver = build_toolset_resolver()
        enabled_toolsets = getattr(state.agent, "enabled_toolsets", None) or ["io-acp"]
        selected = resolver.resolve(list(enabled_toolsets), registry=registry)
        tools = registry.schemas(selected)
        if not tools:
            return "No tools available."
        lines = [f"Available tools ({len(tools)}):"]
        for tool in tools:
            description = str(tool.get("description", ""))
            if len(description) > 80:
                description = f"{description[:77]}..."
            lines.append(f"  {tool.get('name', '?')}: {description}")
        return "\n".join(lines)

    def _cmd_context(self, args: str, state: SessionState) -> str:
        del args
        if not state.history:
            return "Conversation is empty (no messages yet)."
        counts: dict[str, int] = {}
        for message in state.history:
            role = str(message.get("role", "unknown"))
            counts[role] = counts.get(role, 0) + 1
        return "\n".join(
            [
                f"Conversation: {len(state.history)} messages",
                (
                    f"  user: {counts.get('user', 0)}, assistant: {counts.get('assistant', 0)}, "
                    f"tool: {counts.get('tool', 0)}, system: {counts.get('system', 0)}"
                ),
                f"Model: {state.model or getattr(state.agent, 'model', '')}".rstrip(),
            ]
        ).rstrip()

    def _cmd_reset(self, args: str, state: SessionState) -> str:
        del args
        state.history.clear()
        self.session_manager.save_session(state.session_id)
        return "Conversation history cleared."

    def _cmd_compact(self, args: str, state: SessionState) -> str:
        del args
        if not state.history:
            return "Nothing to compress - conversation is empty."
        compressed = ContextCompressor().compress(state.history)
        if not compressed:
            return f"Context already compact enough. Messages: {len(state.history)}"
        state.history, _summary = compressed
        self.session_manager.save_session(state.session_id)
        return f"Context compressed. Messages: {len(state.history)}"

    def _cmd_version(self, args: str, state: SessionState) -> str:
        del args, state
        return f"IO v{IO_VERSION}"

    async def set_session_model(self, model_id: str, session_id: str, **kwargs: Any):
        del kwargs
        state = self.session_manager.get_session(session_id)
        if state is not None:
            state.model = model_id
            state.agent = self.session_manager._make_agent(
                session_id=session_id,
                cwd=state.cwd,
                model=model_id,
                session_file=state.session_file,
            )
            self.session_manager.save_session(session_id)
        return None
