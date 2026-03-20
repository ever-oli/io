from __future__ import annotations

from pathlib import Path

import pytest

from io_cli.extensions import ExtensionRunner
from io_cli.main import run_prompt


def test_extension_runner_loads_python_extension(tmp_path: Path) -> None:
    extension_dir = tmp_path / "extensions"
    extension_dir.mkdir()
    extension_file = extension_dir / "demo.py"
    extension_file.write_text(
        """
def register(io):
    @io.on("tool_call")
    def block(event):
        if event["tool_name"] == "bash":
            return {"block": True, "reason": "blocked by extension"}
""".strip(),
        encoding="utf-8",
    )
    runner = ExtensionRunner(search_paths=[extension_dir])
    loaded = runner.load_all()
    assert loaded == ["demo"]


@pytest.mark.asyncio
async def test_extension_can_block_tool_call(tmp_path: Path) -> None:
    cwd = tmp_path / "repo"
    cwd.mkdir()
    extension_dir = cwd / ".io" / "extensions"
    extension_dir.mkdir(parents=True)
    (extension_dir / "block_bash.py").write_text(
        """
def register(io):
    @io.on("tool_call")
    def block(event):
        if event["tool_name"] == "bash":
            return {"block": True, "reason": "blocked by extension"}
""".strip(),
        encoding="utf-8",
    )
    result = await run_prompt(
        'TOOL[bash] {"command": "echo hello"}',
        cwd=cwd,
        home=tmp_path / "home",
        model="mock/io-test",
        provider="mock",
    )
    assert "blocked by extension" in result.text

