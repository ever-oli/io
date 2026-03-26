from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from io_cli.config import save_config
from io_cli.main import run_prompt


def _event_sink(out: list[tuple[str, dict]]) -> Callable[[str, dict], None]:
    def _cb(event_type: str, payload: dict) -> None:
        out.append((event_type, payload))

    return _cb


def test_run_prompt_emits_message_delta_when_streaming_enabled(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"display": {"streaming": True, "stream_tool_output": True}, "toolsets": ["io-cli"]}, home)
    events: list[tuple[str, dict]] = []

    result = asyncio.run(
        run_prompt(
            "hello streaming",
            cwd=cwd,
            home=home,
            model="mock/io-test",
            provider="mock",
            on_event=_event_sink(events),
        )
    )

    assert result.text
    assert any(t == "message_delta" and p.get("delta") for t, p in events)
    assert any(t == "message" for t, _ in events)


def test_run_prompt_emits_tool_output_delta_for_bash_tool(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    save_config({"display": {"streaming": True, "stream_tool_output": True}, "toolsets": ["io-cli"]}, home)
    events: list[tuple[str, dict]] = []

    _ = asyncio.run(
        run_prompt(
            'TOOL[bash] {"command": "printf hi"}',
            cwd=cwd,
            home=home,
            model="mock/io-test",
            provider="mock",
            on_event=_event_sink(events),
        )
    )

    tool_deltas = [p for t, p in events if t == "tool_output_delta"]
    assert tool_deltas
    assert any(str(p.get("delta", "")).strip() == "hi" for p in tool_deltas)

