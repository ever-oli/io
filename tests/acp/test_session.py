"""Tests for io_cli.acp_adapter.session."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from io_cli.acp_adapter.session import SessionManager, SessionState


def _mock_agent():
    return MagicMock(name="MockAIAgent")


@pytest.fixture()
def manager():
    return SessionManager(agent_factory=_mock_agent)


class TestCreateSession:
    def test_create_session_returns_state(self, manager):
        state = manager.create_session(cwd="/tmp/work")
        assert isinstance(state, SessionState)
        assert state.cwd == "/tmp/work"
        assert state.session_id
        assert state.history == []
        assert state.agent is not None
        assert state.session_file.exists()

    def test_session_ids_are_unique(self, manager):
        s1 = manager.create_session()
        s2 = manager.create_session()
        assert s1.session_id != s2.session_id

    def test_get_nonexistent_session_returns_none(self, manager):
        assert manager.get_session("does-not-exist") is None


class TestForkSession:
    def test_fork_session_deep_copies_history(self, manager):
        original = manager.create_session()
        original.history.extend(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ]
        )
        manager.save_session(original.session_id)
        forked = manager.fork_session(original.session_id, cwd="/new")
        assert forked is not None
        assert len(forked.history) == 2
        forked.history.append({"role": "user", "content": "extra"})
        assert len(original.history) == 2
        assert len(forked.history) == 3

    def test_fork_nonexistent_returns_none(self, manager):
        assert manager.fork_session("bogus-id") is None


class TestListAndCleanup:
    def test_list_sessions_empty(self, manager):
        assert manager.list_sessions() == []

    def test_remove_session(self, manager):
        state = manager.create_session()
        assert manager.remove_session(state.session_id) is True
        assert manager.get_session(state.session_id) is None
        assert manager.remove_session(state.session_id) is False


class TestPersistence:
    def test_create_session_writes_to_db(self, manager):
        state = manager.create_session(cwd="/project")
        row = manager._get_db().get_session(state.session_id)
        assert row is not None
        assert row["source"] == "acp"
        assert json.loads(row["model_config"])["cwd"] == "/project"

    def test_get_session_restores_from_db(self, manager):
        state = manager.create_session(cwd="/work")
        state.history.extend(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ]
        )
        manager.save_session(state.session_id)
        session_id = state.session_id
        with manager._lock:
            del manager._sessions[session_id]
        restored = manager.get_session(session_id)
        assert restored is not None
        assert restored.session_id == session_id
        assert restored.cwd == "/work"
        assert len(restored.history) == 2
        assert restored.history[0]["content"] == "hello"
        assert restored.history[1]["content"] == "hi there"

    def test_save_session_updates_db(self, manager):
        state = manager.create_session()
        state.history.append({"role": "user", "content": "test"})
        manager.save_session(state.session_id)
        messages = manager._get_db().get_messages_as_conversation(state.session_id)
        assert len(messages) == 1
        assert messages[0]["content"] == "test"

    def test_remove_session_deletes_from_db(self, manager):
        state = manager.create_session()
        db = manager._get_db()
        assert db.get_session(state.session_id) is not None
        manager.remove_session(state.session_id)
        assert db.get_session(state.session_id) is None

    def test_list_sessions_includes_db_only(self, manager):
        state = manager.create_session(cwd="/db-only")
        session_id = state.session_id
        with manager._lock:
            del manager._sessions[session_id]
        ids = {entry["session_id"] for entry in manager.list_sessions()}
        assert session_id in ids

    def test_only_restores_acp_sessions(self, manager):
        db = manager._get_db()
        db.create_session(session_id="cli-session-123", source="cli", model="test")
        assert manager.get_session("cli-session-123") is None

    def test_sessions_searchable_via_fts(self, manager):
        state = manager.create_session()
        state.history.extend(
            [
                {"role": "user", "content": "how do I configure nginx"},
                {"role": "assistant", "content": "Here is the nginx config..."},
            ]
        )
        manager.save_session(state.session_id)
        results = manager._get_db().search_messages("nginx")
        assert results
        assert state.session_id in {item["session_id"] for item in results}

    def test_tool_calls_persisted(self, manager):
        state = manager.create_session()
        state.history.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "tc_1", "type": "function", "function": {"name": "terminal", "arguments": "{}"}}],
            }
        )
        state.history.append(
            {
                "role": "tool",
                "content": "output here",
                "tool_call_id": "tc_1",
                "name": "terminal",
            }
        )
        manager.save_session(state.session_id)
        with manager._lock:
            del manager._sessions[state.session_id]
        restored = manager.get_session(state.session_id)
        assert restored is not None
        assert restored.history[0].get("tool_calls") is not None
        assert restored.history[1].get("tool_call_id") == "tc_1"
