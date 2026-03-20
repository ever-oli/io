from __future__ import annotations

from pathlib import Path

import pytest

from io_cli.cron import CronManager
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


@pytest.mark.asyncio
async def test_run_prompt_env_overrides_reach_cronjob_origin(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    home = tmp_path / "home"

    result = await run_prompt(
        'TOOL[cronjob] {"action":"create","schedule":"manual","prompt":"say hello","name":"Origin job","deliver":"origin"}',
        cwd=cwd,
        home=home,
        model="mock/io-test",
        provider="mock",
        toolsets=["cronjob"],
        env_overrides={
            "IO_GATEWAY_SESSION": "1",
            "IO_SESSION_PLATFORM": "telegram",
            "IO_SESSION_CHAT_ID": "456",
            "IO_SESSION_CHAT_NAME": "Ops",
            "IO_SESSION_THREAD_ID": "thread-1",
        },
    )

    jobs = CronManager(home=home).list_jobs()

    assert "Origin job" in result.text
    assert len(jobs) == 1
    assert jobs[0]["origin"]["platform"] == "telegram"
    assert jobs[0]["origin"]["chat_id"] == "456"
    assert jobs[0]["origin"]["thread_id"] == "thread-1"
