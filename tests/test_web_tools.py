from __future__ import annotations

import asyncio
import json
from pathlib import Path

from io_agent import ToolContext
from io_cli.config import load_config, save_config
from io_cli.tools import web as web_tools
from io_cli.tools.registry import get_tool_registry


def _run_tool(tmp_path: Path, tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    context = ToolContext(cwd=tmp_path, home=tmp_path / "home", env={})
    result = asyncio.run(get_tool_registry().get(tool_name).execute(context, arguments))
    return json.loads(result.content)


def test_web_search_tool_parses_duckduckgo_html(tmp_path: Path, monkeypatch) -> None:
    sample_html = """
    <html><body>
      <a class="result__a" href="https://example.com/alpha">Alpha Result</a>
      <div class="result__snippet">Alpha description</div>
      <a class="result__a" href="https://example.com/bravo">Bravo Result</a>
      <div class="result__snippet">Bravo description</div>
    </body></html>
    """

    monkeypatch.setattr(web_tools, "_http_get_text", lambda url, *, timeout, user_agent: sample_html)

    payload = _run_tool(tmp_path, "web_search", {"query": "alpha bravo"})

    assert payload["success"] is True
    assert payload["data"]["web"][0]["title"] == "Alpha Result"
    assert payload["data"]["web"][0]["url"] == "https://example.com/alpha"
    assert payload["data"]["web"][1]["description"] == "Bravo description"


def test_web_extract_tool_reads_html_content(tmp_path: Path, monkeypatch) -> None:
    fetched = web_tools.FetchedContent(
        final_url="https://example.com/page",
        content_type="text/html; charset=utf-8",
        charset="utf-8",
        data=(
            "<html><head><title>Example Page</title></head>"
            "<body><h1>Heading</h1><p>Hello world.</p><ul><li>One</li><li>Two</li></ul></body></html>"
        ).encode("utf-8"),
    )

    monkeypatch.setattr(
        web_tools,
        "_fetch_url_content",
        lambda url, *, timeout, user_agent: fetched,
    )

    payload = _run_tool(tmp_path, "web_extract", {"urls": ["https://example.com/page"]})

    assert payload["results"][0]["title"] == "Example Page"
    assert "Heading" in payload["results"][0]["content"]
    assert "Hello world." in payload["results"][0]["content"]


def test_web_extract_tool_respects_blocklist(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    config = load_config(home)
    config["security"]["website_blocklist"] = {
        "enabled": True,
        "domains": ["blocked.example"],
        "shared_files": [],
    }
    save_config(config, home)

    def _unexpected_fetch(url: str, *, timeout: int, user_agent: str) -> web_tools.FetchedContent:
        raise AssertionError(f"fetch should not run for blocked URL {url}")

    monkeypatch.setattr(web_tools, "_fetch_url_content", _unexpected_fetch)

    payload = _run_tool(tmp_path, "web_extract", {"urls": ["https://blocked.example/article"]})

    result = payload["results"][0]
    assert "blocked by website policy" in result["error"].lower()
    assert result["blocked_by_policy"]["host"] == "blocked.example"
