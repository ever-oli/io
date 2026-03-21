from __future__ import annotations

from pathlib import Path

import pytest

from io_agent import GLOBAL_TOOL_REGISTRY, ToolContext


@pytest.mark.asyncio
async def test_delegate_task_mock(tmp_path: Path) -> None:
    tool = GLOBAL_TOOL_REGISTRY.get("delegate_task")
    ctx = ToolContext(
        cwd=tmp_path,
        home=tmp_path,
        env={},
        metadata={
            "runtime_model": "mock/io-test",
            "runtime_provider": "mock",
            "runtime_base_url": None,
        },
    )
    result = await tool.execute(ctx, {"task": "just reply briefly", "max_turns": 2, "toolsets": ["safe"]})
    assert "summary" in result.content.lower() or "mock" in result.content.lower()


@pytest.mark.asyncio
async def test_execute_code_call_tool(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("abc", encoding="utf-8")
    tool = GLOBAL_TOOL_REGISTRY.get("execute_code")
    ctx = ToolContext(cwd=tmp_path, home=tmp_path, env={})
    body = "c = await call_tool('read', {'path': 'x.txt'})\nassert 'abc' in c"
    result = await tool.execute(ctx, {"code": body, "allowed_tools": ["read"]})
    assert not result.is_error


def test_honcho_tools_registered() -> None:
    for name in ("honcho_context", "honcho_profile", "honcho_search", "honcho_conclude"):
        assert name in GLOBAL_TOOL_REGISTRY.tools
