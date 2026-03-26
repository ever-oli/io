from __future__ import annotations

import asyncio
from pathlib import Path

from io_cli.config import save_config
from io_cli.hermes_contracts import repo_map_contract, semantic_search_contract
from io_cli.main import run_prompt


def test_semantic_contract_and_repo_map(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def hello_world():\n    return 'ok'\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("semantic context docs", encoding="utf-8")
    hits = semantic_search_contract(query="hello_world function", cwd=tmp_path, max_hits=3)
    assert hits
    assert any(item["path"].endswith("a.py") for item in hits)
    repo_map = repo_map_contract(cwd=tmp_path, max_entries=10)
    assert any(item == "a.py" for item in repo_map)


def test_run_prompt_appends_semantic_blocks_when_enabled(tmp_path: Path) -> None:
    home = tmp_path / "home"
    cwd = tmp_path / "repo"
    cwd.mkdir()
    (cwd / "alpha.py").write_text("def alpha_tool():\n    return 1\n", encoding="utf-8")
    save_config(
        {
            "semantic": {"enabled": True, "max_hits": 3, "repo_map": True, "repo_map_max_entries": 10},
            "toolsets": ["io-cli"],
            "display": {"streaming": False, "stream_tool_output": True},
        },
        home,
    )
    events: list[tuple[str, dict]] = []

    def _sink(event_type: str, payload: dict) -> None:
        events.append((event_type, payload))

    _ = asyncio.run(
        run_prompt(
            "find alpha function",
            cwd=cwd,
            home=home,
            model="mock/io-test",
            provider="mock",
            on_event=_sink,
        )
    )
    assert any(t == "message" for t, _ in events)

