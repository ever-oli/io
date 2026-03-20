"""IO-compatible web tools with a local, dependency-light backend."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, urlparse
from urllib.request import Request, urlopen

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import load_config
from ..website_policy import check_website_access

logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "local"
DEFAULT_TIMEOUT = 20
DEFAULT_MAX_CONTENT_CHARS = 5000
MAX_FETCH_BYTES = 2_000_000
MAX_SEARCH_RESULTS = 10
MAX_EXTRACT_URLS = 5
DEFAULT_USER_AGENT = "IO Agent/0.1"


def _json_result(payload: dict[str, Any]) -> ToolResult:
    is_error = bool(payload.get("error")) and not bool(payload.get("success"))
    return ToolResult(content=json.dumps(payload, ensure_ascii=False), is_error=is_error)


def _compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def _normalize_newlines(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _decode_duckduckgo_href(href: str) -> str:
    if not href:
        return ""
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return href


def _get_web_config(home: Path | None) -> dict[str, Any]:
    config = load_config(home)
    payload = config.get("web", {})
    return payload if isinstance(payload, dict) else {}


def _get_timeout(home: Path | None) -> int:
    value = _get_web_config(home).get("timeout", DEFAULT_TIMEOUT)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT


def _get_max_content_chars(home: Path | None) -> int:
    value = _get_web_config(home).get("max_extract_chars", DEFAULT_MAX_CONTENT_CHARS)
    try:
        return max(1000, int(value))
    except (TypeError, ValueError):
        return DEFAULT_MAX_CONTENT_CHARS


def _get_backend(home: Path | None) -> str:
    backend = str(_get_web_config(home).get("backend", DEFAULT_BACKEND)).strip().lower()
    if backend in {"local", "duckduckgo", "auto", "parallel", "firecrawl", "tavily"}:
        return backend
    return DEFAULT_BACKEND


def _get_user_agent(home: Path | None) -> str:
    value = str(_get_web_config(home).get("user_agent", DEFAULT_USER_AGENT)).strip()
    return value or DEFAULT_USER_AGENT


@dataclass(slots=True)
class FetchedContent:
    final_url: str
    content_type: str
    charset: str | None
    data: bytes


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._capture_title = False
        self._capture_snippet = False
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        if tag == "a" and classes.intersection({"result__a", "result-link"}):
            self._flush_current()
            self._current = {
                "title": "",
                "url": _decode_duckduckgo_href(attributes.get("href", "")),
                "description": "",
                "position": len(self.results) + 1,
            }
            self._capture_title = True
            self._title_parts = []
            return
        if classes.intersection({"result__snippet", "result-snippet"}) and self._current is not None:
            self._capture_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture_title and self._current is not None:
            self._current["title"] = _compact_whitespace("".join(self._title_parts))
            self._capture_title = False
            return
        if self._capture_snippet and tag in {"a", "div", "span"} and self._current is not None:
            self._current["description"] = _compact_whitespace("".join(self._snippet_parts))
            self._capture_snippet = False

    def handle_data(self, data: str) -> None:
        if self._capture_title:
            self._title_parts.append(data)
        elif self._capture_snippet:
            self._snippet_parts.append(data)

    def close(self) -> None:
        super().close()
        self._flush_current()

    def _flush_current(self) -> None:
        if not self._current:
            return
        if self._current.get("title") and self._current.get("url"):
            self.results.append(self._current)
        self._current = None
        self._capture_title = False
        self._capture_snippet = False
        self._title_parts = []
        self._snippet_parts = []


class _ReadableHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "table",
        "tr",
    }
    IGNORE_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._parts: list[str] = []
        self._capture_title = False
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self.IGNORE_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return
        if tag == "title":
            self._capture_title = True
            return
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(tag[1])
            self._parts.append("\n" + ("#" * level) + " ")
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag in self.BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.IGNORE_TAGS and self._ignore_depth:
            self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return
        if tag == "title":
            self._capture_title = False
            return
        if tag in self.BLOCK_TAGS or tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        text = _compact_whitespace(data)
        if not text:
            return
        if self._capture_title:
            self.title = (self.title + " " + text).strip()
            return
        self._parts.append(text + " ")

    def content(self) -> str:
        return _normalize_newlines("".join(self._parts))


def _decode_text(data: bytes, charset: str | None = None) -> str:
    if charset:
        try:
            return data.decode(charset, errors="replace")
        except LookupError:
            pass
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding, errors="replace")
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def _fetch_url_content(url: str, *, timeout: int, user_agent: str) -> FetchedContent:
    request = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_FETCH_BYTES:
                    raise ValueError(f"Refusing content larger than {MAX_FETCH_BYTES} bytes")
                chunks.append(chunk)
            data = b"".join(chunks)
            return FetchedContent(
                final_url=response.geturl(),
                content_type=response.headers.get("Content-Type", ""),
                charset=response.headers.get_content_charset(),
                data=data,
            )
    except HTTPError as exc:
        raise ValueError(f"HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise ValueError(f"Failed to reach {url}: {exc.reason}") from exc


def _http_get_text(url: str, *, timeout: int, user_agent: str) -> str:
    fetched = _fetch_url_content(url, timeout=timeout, user_agent=user_agent)
    return _decode_text(fetched.data, fetched.charset)


def _parse_duckduckgo_results(html: str, limit: int) -> list[dict[str, Any]]:
    parser = _DuckDuckGoResultParser()
    parser.feed(html)
    parser.close()
    results = []
    for entry in parser.results[:limit]:
        results.append(
            {
                "title": entry.get("title", ""),
                "url": entry.get("url", ""),
                "description": entry.get("description", ""),
                "position": len(results) + 1,
            }
        )
    return results


def _search_duckduckgo(query: str, *, limit: int, timeout: int, user_agent: str) -> list[dict[str, Any]]:
    html = _http_get_text(
        f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
        timeout=timeout,
        user_agent=user_agent,
    )
    return _parse_duckduckgo_results(html, limit)


def _extract_html_document(html: str) -> tuple[str, str]:
    parser = _ReadableHTMLParser()
    parser.feed(html)
    parser.close()
    content = parser.content()
    title = parser.title or ""
    return title, content


def _extract_pdf_text(data: bytes) -> str:
    pdftotext = shutil.which("pdftotext")
    if not pdftotext:
        raise ValueError("PDF extraction requires pdftotext on PATH for the local backend")
    with tempfile.TemporaryDirectory(prefix="io-web-") as tmp_dir:
        pdf_path = Path(tmp_dir) / "document.pdf"
        txt_path = Path(tmp_dir) / "document.txt"
        pdf_path.write_bytes(data)
        try:
            subprocess.run(
                [pdftotext, str(pdf_path), str(txt_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip() if exc.stderr else str(exc)
            raise ValueError(f"pdftotext failed: {stderr}") from exc
        return txt_path.read_text(encoding="utf-8", errors="replace")


def _condense_content(content: str, *, max_chars: int) -> str:
    cleaned = _normalize_newlines(content)
    if len(cleaned) <= max_chars:
        return cleaned
    paragraphs = [paragraph.strip() for paragraph in cleaned.split("\n\n") if paragraph.strip()]
    selected: list[str] = []
    current_size = 0
    for paragraph in paragraphs:
        extra = len(paragraph) + (2 if selected else 0)
        if current_size + extra > max_chars - 40:
            break
        selected.append(paragraph)
        current_size += extra
    if not selected:
        selected = [cleaned[: max_chars - 40].rstrip()]
    return "\n\n".join(selected) + "\n\n[Content truncated]"


def _extract_document(fetched: FetchedContent, *, max_chars: int) -> tuple[str, str]:
    content_type = fetched.content_type.lower()
    if "pdf" in content_type or fetched.final_url.lower().endswith(".pdf"):
        title = Path(urlparse(fetched.final_url).path).name or fetched.final_url
        content = _extract_pdf_text(fetched.data)
        return title, _condense_content(content, max_chars=max_chars)
    text = _decode_text(fetched.data, fetched.charset)
    if "html" in content_type or "<html" in text[:500].lower():
        title, content = _extract_html_document(text)
    else:
        title = Path(urlparse(fetched.final_url).path).name or fetched.final_url
        content = text
    return title, _condense_content(content, max_chars=max_chars)


def web_search_tool(query: str, limit: int = 5, *, home: Path | None = None) -> str:
    if not query.strip():
        return json.dumps({"error": "query is required", "success": False}, ensure_ascii=False)
    timeout = _get_timeout(home)
    user_agent = _get_user_agent(home)
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))
    try:
        results = _search_duckduckgo(query, limit=limit, timeout=timeout, user_agent=user_agent)
        return json.dumps(
            {
                "success": True,
                "data": {"web": results},
                "backend": _get_backend(home),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        logger.debug("Error searching web: %s", exc)
        return json.dumps({"error": f"Error searching web: {exc}"}, ensure_ascii=False)


async def web_extract_tool(
    urls: list[str],
    format: str | None = None,
    use_llm_processing: bool = True,
    model: str | None = None,
    min_length: int = DEFAULT_MAX_CONTENT_CHARS,
    *,
    home: Path | None = None,
) -> str:
    del format, use_llm_processing, model, min_length
    timeout = _get_timeout(home)
    user_agent = _get_user_agent(home)
    max_chars = _get_max_content_chars(home)
    config_path = (home / "config.yaml") if home is not None else None
    results: list[dict[str, Any]] = []

    for raw_url in urls[:MAX_EXTRACT_URLS]:
        url = str(raw_url).strip()
        if not url:
            continue
        blocked = check_website_access(url, config_path=config_path)
        if blocked:
            results.append(
                {
                    "url": url,
                    "title": "",
                    "content": "",
                    "error": blocked["message"],
                    "blocked_by_policy": {
                        "host": blocked["host"],
                        "rule": blocked["rule"],
                        "source": blocked["source"],
                    },
                }
            )
            continue
        try:
            fetched = await asyncio.to_thread(
                _fetch_url_content,
                url,
                timeout=timeout,
                user_agent=user_agent,
            )
            final_blocked = check_website_access(fetched.final_url, config_path=config_path)
            if final_blocked:
                results.append(
                    {
                        "url": fetched.final_url,
                        "title": "",
                        "content": "",
                        "error": final_blocked["message"],
                        "blocked_by_policy": {
                            "host": final_blocked["host"],
                            "rule": final_blocked["rule"],
                            "source": final_blocked["source"],
                        },
                    }
                )
                continue
            title, content = await asyncio.to_thread(
                _extract_document,
                fetched,
                max_chars=max_chars,
            )
            results.append(
                {
                    "url": fetched.final_url,
                    "title": title,
                    "content": content,
                    "error": None,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "url": url,
                    "title": "",
                    "content": "",
                    "error": str(exc),
                }
            )

    if not results:
        return json.dumps({"error": "Content was inaccessible or not found"}, ensure_ascii=False)
    return json.dumps({"results": results}, ensure_ascii=False)


WEB_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query to look up on the web",
        }
    },
    "required": ["query"],
}


WEB_EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "urls": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of URLs to extract content from (max 5 URLs per call)",
            "maxItems": MAX_EXTRACT_URLS,
        }
    },
    "required": ["urls"],
}


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for information on any topic. Returns up to 5 relevant "
        "results with titles, URLs, and descriptions."
    )
    input_schema = WEB_SEARCH_SCHEMA

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        payload = await asyncio.to_thread(
            web_search_tool,
            str(arguments.get("query", "")),
            int(arguments.get("limit", 5) or 5),
            home=context.home,
        )
        parsed = json.loads(payload)
        return ToolResult(content=payload, is_error=bool(parsed.get("error")) and not bool(parsed.get("success")))


class WebExtractTool(Tool):
    name = "web_extract"
    description = (
        "Extract content from web page URLs. Returns page content in markdown-like text. "
        "If a URL fails, use browser tooling or another backend."
    )
    input_schema = WEB_EXTRACT_SCHEMA

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        urls = arguments.get("urls", [])
        payload = await web_extract_tool(
            urls[:MAX_EXTRACT_URLS] if isinstance(urls, list) else [],
            "markdown",
            home=context.home,
        )
        parsed = json.loads(payload)
        return ToolResult(content=payload, is_error=bool(parsed.get("error")) and "results" not in parsed)


GLOBAL_TOOL_REGISTRY.register(WebSearchTool())
GLOBAL_TOOL_REGISTRY.register(WebExtractTool())
