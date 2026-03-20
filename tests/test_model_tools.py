from __future__ import annotations

import json

from io_cli.model_tools import get_tool_definitions, handle_function_call


def test_get_tool_definitions_for_file_toolset_includes_io_aliases() -> None:
    definitions = get_tool_definitions(enabled_toolsets=["file"])
    names = {entry["function"]["name"] for entry in definitions}
    assert {"read_file", "write_file", "patch", "search_files"} <= names


def test_get_tool_definitions_for_web_toolset_includes_web_tools() -> None:
    definitions = get_tool_definitions(enabled_toolsets=["web"])
    names = {entry["function"]["name"] for entry in definitions}
    assert {"web_search", "web_extract"} <= names


def test_handle_function_call_read_file_returns_line_numbered_json(tmp_path, monkeypatch) -> None:
    path = tmp_path / "demo.txt"
    path.write_text("alpha\nbeta\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    payload = json.loads(handle_function_call("read_file", {"path": "demo.txt", "offset": 1, "limit": 10}))

    assert payload["path"].endswith("demo.txt")
    assert "1|alpha" in payload["content"]
    assert "2|beta" in payload["content"]


def test_handle_function_call_terminal_background_and_process_wait(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    started = json.loads(
        handle_function_call(
            "terminal",
            {"command": "python3 -c 'import time; print(\"ready\"); time.sleep(0.1)'", "background": True},
            task_id="test-task",
        )
    )
    session_id = started["session_id"]

    waited = {}
    for _ in range(3):
        waited = json.loads(
            handle_function_call("process", {"action": "wait", "session_id": session_id, "timeout": 5})
        )
        if waited.get("exit_code") is not None:
            break

    assert waited["session_id"] == session_id
    assert waited["exit_code"] == 0
