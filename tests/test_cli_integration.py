from __future__ import annotations

from pathlib import Path

import pytest

from io_cli.main import run_prompt


@pytest.mark.asyncio
async def test_run_prompt_uses_mock_provider_and_ls_tool(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "alpha.txt").write_text("hello", encoding="utf-8")
    result = await run_prompt(
        'TOOL[ls] {"path": "."}',
        cwd=cwd,
        home=tmp_path / "home",
        model="mock/io-test",
        provider="mock",
    )
    assert "alpha.txt" in result.text
    assert result.session_path.exists()

