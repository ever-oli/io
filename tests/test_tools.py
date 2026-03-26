from __future__ import annotations

from pathlib import Path

import pytest

from io_agent import ToolContext, execute_tool_batch
from io_cli.tools.registry import get_tool_registry


@pytest.mark.asyncio
async def test_dangerous_bash_requires_approval(tmp_path: Path) -> None:
    registry = get_tool_registry()
    tool = registry.get("bash")
    context = ToolContext(
        cwd=tmp_path,
        home=tmp_path / "home",
        approval_callback=lambda _name, _arguments, _reason: False,
    )
    results = await execute_tool_batch([(tool, {"command": "rm -rf /tmp/demo"}, "call-1")], context=context)
    assert results[0][1].is_error is True
    assert "requires approval" in results[0][1].content


@pytest.mark.asyncio
async def test_bash_strips_ansi_from_output_and_stream(tmp_path: Path) -> None:
    registry = get_tool_registry()
    tool = registry.get("bash")
    seen: list[str] = []
    context = ToolContext(
        cwd=tmp_path,
        home=tmp_path / "home",
        tool_output_callback=lambda _name, _stream, chunk: seen.append(chunk),
    )
    results = await execute_tool_batch(
        [(tool, {"command": "printf '\\033[31mred\\033[0m\\n'"}, "call-1")],
        context=context,
    )
    out = results[0][1]
    assert out.is_error is False
    assert out.content.strip() == "red"
    assert seen
    assert "".join(seen).strip() == "red"

