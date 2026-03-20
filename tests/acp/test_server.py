"""Tests for io_cli.acp_adapter.server."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import acp
import pytest
from acp.schema import (
    AgentCapabilities,
    AuthenticateResponse,
    Implementation,
    InitializeResponse,
    ListSessionsResponse,
    NewSessionResponse,
    PromptResponse,
    ResumeSessionResponse,
    TextContentBlock,
)

from io_cli import __version__ as IO_VERSION
from io_cli.acp_adapter.server import IOACPAgent
from io_cli.acp_adapter.session import SessionManager


@pytest.fixture()
def mock_manager():
    return SessionManager(agent_factory=lambda: MagicMock(name="MockAIAgent"))


@pytest.fixture()
def agent(mock_manager):
    return IOACPAgent(session_manager=mock_manager)


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_returns_correct_protocol_version(self, agent):
        response = await agent.initialize(protocol_version=1)
        assert isinstance(response, InitializeResponse)
        assert response.protocol_version == acp.PROTOCOL_VERSION

    @pytest.mark.asyncio
    async def test_initialize_returns_agent_info(self, agent):
        response = await agent.initialize(protocol_version=1)
        assert isinstance(response.agent_info, Implementation)
        assert response.agent_info.name == "io-agent"
        assert response.agent_info.version == IO_VERSION

    @pytest.mark.asyncio
    async def test_initialize_returns_capabilities(self, agent):
        response = await agent.initialize(protocol_version=1)
        assert isinstance(response.agent_capabilities, AgentCapabilities)
        assert response.agent_capabilities.session_capabilities is not None


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_authenticate_with_provider_configured(self, agent, monkeypatch):
        monkeypatch.setattr("io_cli.acp_adapter.server.has_provider", lambda **kwargs: True)
        response = await agent.authenticate(method_id="openrouter")
        assert isinstance(response, AuthenticateResponse)

    @pytest.mark.asyncio
    async def test_authenticate_without_provider(self, agent, monkeypatch):
        monkeypatch.setattr("io_cli.acp_adapter.server.has_provider", lambda **kwargs: False)
        response = await agent.authenticate(method_id="openrouter")
        assert response is None


class TestSessionOps:
    @pytest.mark.asyncio
    async def test_new_session_creates_session(self, agent):
        response = await agent.new_session(cwd="/home/user/project")
        assert isinstance(response, NewSessionResponse)
        state = agent.session_manager.get_session(response.session_id)
        assert state is not None
        assert state.cwd == "/home/user/project"

    @pytest.mark.asyncio
    async def test_cancel_sets_event(self, agent):
        response = await agent.new_session(cwd=".")
        state = agent.session_manager.get_session(response.session_id)
        assert not state.cancel_event.is_set()
        await agent.cancel(session_id=response.session_id)
        assert state.cancel_event.is_set()

    @pytest.mark.asyncio
    async def test_load_session_not_found_returns_none(self, agent):
        assert await agent.load_session(cwd="/tmp", session_id="bogus") is None

    @pytest.mark.asyncio
    async def test_resume_session_returns_response(self, agent):
        response = await agent.new_session(cwd="/tmp")
        resume_response = await agent.resume_session(cwd="/tmp", session_id=response.session_id)
        assert isinstance(resume_response, ResumeSessionResponse)


class TestListAndFork:
    @pytest.mark.asyncio
    async def test_list_sessions(self, agent):
        await agent.new_session(cwd="/a")
        await agent.new_session(cwd="/b")
        response = await agent.list_sessions()
        assert isinstance(response, ListSessionsResponse)
        assert len(response.sessions) == 2

    @pytest.mark.asyncio
    async def test_fork_session(self, agent):
        new_response = await agent.new_session(cwd="/original")
        fork_response = await agent.fork_session(cwd="/forked", session_id=new_response.session_id)
        assert fork_response.session_id
        assert fork_response.session_id != new_response.session_id


class TestPrompt:
    @pytest.mark.asyncio
    async def test_prompt_returns_refusal_for_unknown_session(self, agent):
        response = await agent.prompt(prompt=[TextContentBlock(type="text", text="hello")], session_id="nonexistent")
        assert isinstance(response, PromptResponse)
        assert response.stop_reason == "refusal"

    @pytest.mark.asyncio
    async def test_prompt_runs_agent(self, agent):
        new_response = await agent.new_session(cwd=".")
        state = agent.session_manager.get_session(new_response.session_id)
        state.agent.run_conversation = MagicMock(
            return_value={
                "final_response": "Hello! How can I help?",
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "Hello! How can I help?"},
                ],
            }
        )
        mock_conn = MagicMock(spec=acp.Client)
        mock_conn.session_update = AsyncMock()
        agent._conn = mock_conn
        response = await agent.prompt(prompt=[TextContentBlock(type="text", text="hello")], session_id=new_response.session_id)
        assert isinstance(response, PromptResponse)
        assert response.stop_reason == "end_turn"
        state.agent.run_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_prompt_updates_history(self, agent):
        new_response = await agent.new_session(cwd=".")
        state = agent.session_manager.get_session(new_response.session_id)
        expected_history = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hey"},
        ]
        state.agent.run_conversation = MagicMock(return_value={"final_response": "hey", "messages": expected_history})
        agent._conn = MagicMock(spec=acp.Client, session_update=AsyncMock())
        await agent.prompt(prompt=[TextContentBlock(type="text", text="hi")], session_id=new_response.session_id)
        assert state.history == expected_history

    @pytest.mark.asyncio
    async def test_prompt_sends_final_message_update(self, agent):
        new_response = await agent.new_session(cwd=".")
        state = agent.session_manager.get_session(new_response.session_id)
        state.agent.run_conversation = MagicMock(return_value={"final_response": "I can help with that!", "messages": []})
        mock_conn = MagicMock(spec=acp.Client)
        mock_conn.session_update = AsyncMock()
        agent._conn = mock_conn
        await agent.prompt(prompt=[TextContentBlock(type="text", text="help me")], session_id=new_response.session_id)
        mock_conn.session_update.assert_called()
        last_call = mock_conn.session_update.call_args_list[-1]
        update = last_call[1].get("update") or last_call[0][1]
        assert update.session_update == "agent_message_chunk"

    @pytest.mark.asyncio
    async def test_prompt_cancelled_returns_cancelled_stop_reason(self, agent):
        new_response = await agent.new_session(cwd=".")
        state = agent.session_manager.get_session(new_response.session_id)

        def mock_run(**kwargs):
            state.cancel_event.set()
            return {"final_response": "interrupted", "messages": []}

        state.agent.run_conversation = mock_run
        agent._conn = MagicMock(spec=acp.Client, session_update=AsyncMock())
        response = await agent.prompt(prompt=[TextContentBlock(type="text", text="do something")], session_id=new_response.session_id)
        assert response.stop_reason == "cancelled"


class TestOnConnect:
    def test_on_connect_stores_client(self, agent):
        mock_conn = MagicMock(spec=acp.Client)
        agent.on_connect(mock_conn)
        assert agent._conn is mock_conn


class TestSlashCommands:
    def _make_state(self, mock_manager):
        state = mock_manager.create_session(cwd="/tmp")
        state.agent.model = "test-model"
        state.agent.provider = "openrouter"
        state.model = "test-model"
        return state

    def test_help_lists_commands(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        result = agent._handle_slash_command("/help", state)
        assert "/help" in result
        assert "/model" in result
        assert "/tools" in result
        assert "/reset" in result

    def test_model_shows_current(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        result = agent._handle_slash_command("/model", state)
        assert "test-model" in result

    def test_tools_lists_available_tools(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        result = agent._handle_slash_command("/tools", state)
        assert "Available tools" in result

    def test_context_empty(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        state.history = []
        result = agent._handle_slash_command("/context", state)
        assert "empty" in result.lower()

    def test_context_with_messages(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        state.history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = agent._handle_slash_command("/context", state)
        assert "2 messages" in result
        assert "user: 1" in result

    def test_reset_clears_history(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        state.history = [{"role": "user", "content": "hello"}]
        result = agent._handle_slash_command("/reset", state)
        assert "cleared" in result.lower()
        assert len(state.history) == 0

    def test_version(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        result = agent._handle_slash_command("/version", state)
        assert IO_VERSION in result

    def test_unknown_command_returns_none(self, agent, mock_manager):
        state = self._make_state(mock_manager)
        assert agent._handle_slash_command("/nonexistent", state) is None

    @pytest.mark.asyncio
    async def test_slash_command_intercepted_in_prompt(self, agent):
        new_response = await agent.new_session(cwd="/tmp")
        mock_conn = MagicMock(spec=acp.Client)
        mock_conn.session_update = AsyncMock()
        agent._conn = mock_conn
        response = await agent.prompt(prompt=[TextContentBlock(type="text", text="/help")], session_id=new_response.session_id)
        assert response.stop_reason == "end_turn"
        mock_conn.session_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_slash_falls_through_to_agent(self, agent):
        new_response = await agent.new_session(cwd="/tmp")
        state = agent.session_manager.get_session(new_response.session_id)
        state.agent.run_conversation = MagicMock(return_value={"final_response": "I processed /foo", "messages": []})
        response = await agent.prompt(prompt=[TextContentBlock(type="text", text="/foo bar")], session_id=new_response.session_id)
        assert response.stop_reason == "end_turn"
        state.agent.run_conversation.assert_called_once()
