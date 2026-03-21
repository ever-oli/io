"""Playwright-backed browser_* tools (local Chromium, CDP, Browserbase, Browser Use)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from io_agent import GLOBAL_TOOL_REGISTRY, Tool, ToolContext, ToolResult

from ..config import load_config
from ..website_policy import check_website_access

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    async_playwright = None  # type: ignore[misc, assignment]

_pw: Any = None
_pw_lock = asyncio.Lock()
_sessions: dict[str, "BrowserSession"] = {}
_locks: dict[str, asyncio.Lock] = {}


def _task_id(ctx: ToolContext) -> str:
    t = str(ctx.metadata.get("task_id") or ctx.env.get("IO_SESSION_ID") or "default").strip()
    return t or "default"


def _lock(task: str) -> asyncio.Lock:
    return _locks.setdefault(task, asyncio.Lock())


def _bcfg(home: Path) -> dict[str, Any]:
    c = load_config(home).get("browser")
    return c if isinstance(c, dict) else {}


def _json(d: dict[str, Any], *, err: bool = False) -> ToolResult:
    return ToolResult(content=json.dumps(d, ensure_ascii=False), is_error=err)


def _norm_ref(ref: str) -> str:
    t = str(ref or "").strip()
    if t.startswith("@e"):
        t = t[2:]
    elif t.startswith("@"):
        t = t[1:]
    if len(t) > 1 and t.lower().startswith("e") and t[1:].isdigit():
        t = t[1:]
    return t.strip()


async def _get_pw() -> Any:
    global _pw
    if not HAS_PLAYWRIGHT or async_playwright is None:
        raise RuntimeError("Install playwright and browsers: pip install playwright && playwright install chromium")
    async with _pw_lock:
        if _pw is None:
            _pw = await async_playwright().start()
        return _pw


@dataclass
class BrowserSession:
    browser: Any
    page: Any
    console_messages: list[dict[str, str]] = field(default_factory=list)
    browserbase_session_id: str | None = None
    browser_use_session_id: str | None = None
    browser_use_api_key: str | None = None
    browser_use_base: str = "https://api.browser-use.com/api/v2"
    last_touch: float = field(default_factory=time.monotonic)


def _touch(s: BrowserSession) -> None:
    s.last_touch = time.monotonic()


async def _close(task: str, s: BrowserSession, home: Path) -> None:
    cfg = _bcfg(home)
    if s.browser_use_session_id and s.browser_use_api_key:
        base = s.browser_use_base.rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                await client.patch(
                    f"{base}/browsers/{s.browser_use_session_id}",
                    headers={"X-Browser-Use-API-Key": s.browser_use_api_key, "Content-Type": "application/json"},
                    json={"action": "stop"},
                )
        except Exception as exc:
            logger.debug("browser_use stop: %s", exc)
    if s.browserbase_session_id:
        key = str(cfg.get("browserbase_api_key") or "").strip()
        if key:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    await client.post(
                        f"https://api.browserbase.com/v1/sessions/{s.browserbase_session_id}",
                        headers={"X-BB-API-Key": key, "Content-Type": "application/json"},
                        json={"status": "REQUEST_RELEASE"},
                    )
            except Exception as exc:
                logger.debug("browserbase release: %s", exc)
    try:
        await s.browser.close()
    except Exception:
        pass
    _sessions.pop(task, None)


async def _stale_maybe(task: str, s: BrowserSession, home: Path) -> None:
    t = int(_bcfg(home).get("inactivity_timeout", 120) or 120)
    if t > 0 and time.monotonic() - s.last_touch > t:
        await _close(task, s, home)


async def _cdp_page(pw: Any, url: str) -> tuple[Any, Any]:
    browser = await pw.chromium.connect_over_cdp(url)
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    return browser, page


async def _ensure(ctx: ToolContext) -> tuple[str, BrowserSession]:
    home = ctx.home
    task = _task_id(ctx)
    cfg = _bcfg(home)
    async with _lock(task):
        if task in _sessions:
            await _stale_maybe(task, _sessions[task], home)
        if task in _sessions:
            _touch(_sessions[task])
            return task, _sessions[task]

        backend = str(cfg.get("backend", "local_playwright") or "local_playwright").lower()
        cdp_url = str(cfg.get("cdp_url") or ctx.env.get("CHROME_CDP_URL") or "").strip()
        bb_key = str(cfg.get("browserbase_api_key") or ctx.env.get("BROWSERBASE_API_KEY") or "").strip()
        bb_proj = str(cfg.get("browserbase_project_id") or ctx.env.get("BROWSERBASE_PROJECT_ID") or "").strip()
        bu_key = str(cfg.get("browser_use_api_key") or ctx.env.get("BROWSER_USE_API_KEY") or "").strip()
        bu_base = str(cfg.get("browser_use_api_base") or "https://api.browser-use.com/api/v2").strip().rstrip("/")
        vw, vh = int(cfg.get("viewport_width", 1280) or 1280), int(cfg.get("viewport_height", 720) or 720)
        headless = bool(cfg.get("headless", True))
        pw = await _get_pw()
        bb_id = bu_id = None
        browser = page = None

        if backend == "browserbase" and bb_key:
            payload: dict[str, Any] = {"browserSettings": {"viewport": {"width": vw, "height": vh}}}
            if bb_proj:
                payload["projectId"] = bb_proj
            if cfg.get("record_sessions"):
                payload["browserSettings"]["recordSession"] = True
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    "https://api.browserbase.com/v1/sessions",
                    headers={"X-BB-API-Key": bb_key, "Content-Type": "application/json"},
                    json=payload,
                )
                r.raise_for_status()
                data = r.json()
            connect = str(data.get("connectUrl") or "")
            bb_id = str(data.get("id") or "")
            if not connect:
                raise RuntimeError("browserbase: no connectUrl")
            browser, page = await _cdp_page(pw, connect)

        elif backend == "browser_use" and bu_key:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(
                    f"{bu_base}/browsers",
                    headers={"X-Browser-Use-API-Key": bu_key, "Content-Type": "application/json"},
                    json={
                        "browserScreenWidth": vw,
                        "browserScreenHeight": vh,
                        "enableRecording": bool(cfg.get("record_sessions", False)),
                    },
                )
                r.raise_for_status()
                data = r.json()
            connect = str(data.get("cdpUrl") or data.get("cdp_url") or "")
            bu_id = str(data.get("id") or "")
            if not connect:
                raise RuntimeError("browser_use: no cdpUrl")
            browser, page = await _cdp_page(pw, connect)

        elif backend == "cdp":
            if not cdp_url:
                raise RuntimeError("browser.cdp_url or CHROME_CDP_URL required")
            browser, page = await _cdp_page(pw, cdp_url)

        else:
            browser = await pw.chromium.launch(headless=headless, args=["--disable-dev-shm-usage"])
            pctx = await browser.new_context(viewport={"width": vw, "height": vh})
            page = await pctx.new_page()

        assert browser is not None and page is not None
        sess = BrowserSession(
            browser=browser,
            page=page,
            browserbase_session_id=bb_id,
            browser_use_session_id=bu_id,
            browser_use_api_key=bu_key if bu_id else None,
            browser_use_base=bu_base,
        )

        def _on_console(msg: Any) -> None:
            try:
                sess.console_messages.append({"type": str(msg.type), "text": str(msg.text)[:4000]})
            except Exception:
                pass

        page.on("console", _on_console)
        _sessions[task] = sess
        _touch(sess)
        return task, sess


_TAG_JS = """
() => {
  const sel = 'a[href], button, input:not([type="hidden"]), textarea, select, [role="button"], [role="link"], [role="textbox"], [tabindex]:not([tabindex="-1"])';
  let i = 0;
  document.querySelectorAll(sel).forEach(el => {
    const st = window.getComputedStyle(el);
    if (st.display === 'none' || st.visibility === 'hidden') return;
    if (el.offsetParent === null && el.tagName !== 'BODY' && el.tagName !== 'HTML') return;
    i += 1;
    el.setAttribute('data-io-browser-ref', String(i));
  });
  return i;
}
"""


async def _tag(page: Any) -> int:
    return int(await page.evaluate(_TAG_JS))


async def _lines(page: Any, n: int) -> list[str]:
    out: list[str] = []
    for i in range(1, n + 1):
        info = await page.evaluate(
            f"""() => {{
            const el = document.querySelector('[data-io-browser-ref="{i}"]');
            if (!el) return null;
            return {{
              tag: el.tagName, type: el.type || '', aria: el.getAttribute('aria-label') || '',
              placeholder: el.getAttribute('placeholder') || '',
              text: (el.innerText || '').slice(0, 160).replace(/\\s+/g, ' ').trim(),
              href: el.href || ''
            }};
          }}"""
        )
        if not info:
            continue
        bits = [f"@{i}", str(info.get("tag", "")).lower()]
        for k, mx in (("type", None), ("aria", 80), ("placeholder", 60), ("text", 120)):
            v = info.get(k)
            if v:
                bits.append(f"{k}={str(v)[:mx or 999]}")
        if info.get("href"):
            bits.append(f"href={str(info['href'])[:80]}")
        out.append(" ".join(bits))
    return out


Handler = Callable[[ToolContext, dict[str, object]], Awaitable[ToolResult]]


class _BrowserTool(Tool):
    never_parallel = True

    def __init__(self, name: str, description: str, input_schema: dict[str, Any], run: Handler) -> None:
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self._run = run

    async def execute(self, context: ToolContext, arguments: dict[str, object]) -> ToolResult:
        return await self._run(context, arguments)


async def _h_navigate(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    url = str(a.get("url", "")).strip()
    if not url:
        return _json({"error": "url required"}, err=True)
    block = check_website_access(url)
    if block:
        return _json({"error": f"blocked: {block.get('reason', 'policy')}"}, err=True)
    try:
        _, s = await _ensure(ctx)
        await s.page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        _touch(s)
        return _json({"ok": True, "url": s.page.url})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_snapshot(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    try:
        _, s = await _ensure(ctx)
        n = await _tag(s.page)
        L = await _lines(s.page, n)
        snap = "\n".join(L) if L else "(no interactive elements)"
        if bool(a.get("full", False)):
            body = str(await s.page.evaluate("() => (document.body && document.body.innerText) || ''"))[:12_000]
            if body:
                snap = f"{snap}\n\n--- text ---\n{body}"
        _touch(s)
        return _json({"snapshot": snap, "interactive_count": n, "url": s.page.url})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_click(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    ref = _norm_ref(str(a.get("ref", "")))
    if not ref:
        return _json({"error": "ref required"}, err=True)
    try:
        _, s = await _ensure(ctx)
        await s.page.locator(f'[data-io-browser-ref="{ref}"]').first.click(timeout=15_000)
        _touch(s)
        return _json({"ok": True, "ref": ref})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_type(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    ref = _norm_ref(str(a.get("ref", "")))
    if not ref:
        return _json({"error": "ref required"}, err=True)
    text = str(a.get("text", ""))
    try:
        _, s = await _ensure(ctx)
        loc = s.page.locator(f'[data-io-browser-ref="{ref}"]').first
        await loc.click(timeout=10_000)
        await loc.fill("")
        await loc.fill(text)
        _touch(s)
        return _json({"ok": True, "ref": ref})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_scroll(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    direction = str(a.get("direction", "down") or "down").lower()
    amount = int(a.get("amount", 480) or 480)
    delta = -amount if direction == "up" else amount
    try:
        _, s = await _ensure(ctx)
        await s.page.evaluate(f"() => window.scrollBy(0, {delta})")
        _touch(s)
        return _json({"ok": True, "direction": direction, "amount": amount})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_back(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    try:
        _, s = await _ensure(ctx)
        await s.page.go_back()
        _touch(s)
        return _json({"ok": True, "url": s.page.url})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_press(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    key = str(a.get("key", "") or "").strip()
    if not key:
        return _json({"error": "key required"}, err=True)
    key = re.sub(r"\s+", "", key)
    if key.lower() == "return":
        key = "Enter"
    elif len(key) > 1 and key[1:].islower():
        key = key[0].upper() + key[1:]
    try:
        _, s = await _ensure(ctx)
        await s.page.keyboard.press(key)
        _touch(s)
        return _json({"ok": True, "key": key})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_close(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    task = _task_id(ctx)
    async with _lock(task):
        s = _sessions.get(task)
        if s:
            await _close(task, s, ctx.home)
    return _json({"ok": True})


async def _h_images(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    try:
        _, s = await _ensure(ctx)
        data = await s.page.evaluate(
            """() => Array.from(document.images).slice(0, 80).map(img => ({
            src: img.currentSrc || img.src || '', alt: img.alt || ''
          }))"""
        )
        _touch(s)
        return _json({"images": data})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_vision(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    try:
        _, s = await _ensure(ctx)
        out = ctx.home / "browser_screenshots"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"shot-{int(time.time() * 1000)}.png"
        await s.page.screenshot(path=str(path), full_page=False)
        _touch(s)
        return _json({"path": str(path)})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


async def _h_console(ctx: ToolContext, a: dict[str, object]) -> ToolResult:
    try:
        _, s = await _ensure(ctx)
        msgs = list(s.console_messages)
        if bool(a.get("clear", False)):
            s.console_messages.clear()
        _touch(s)
        return _json({"messages": msgs})
    except Exception as exc:
        return _json({"error": str(exc)}, err=True)


def _register() -> None:
    specs: list[tuple[str, str, dict[str, Any], Handler]] = [
        (
            "browser_navigate",
            "Open a URL in the browser (starts session if needed).",
            {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
            _h_navigate,
        ),
        (
            "browser_snapshot",
            "List interactive elements with @N refs for click/type.",
            {
                "type": "object",
                "properties": {"full": {"type": "boolean", "description": "Include page text excerpt"}},
            },
            _h_snapshot,
        ),
        (
            "browser_click",
            "Click element by ref from browser_snapshot.",
            {"type": "object", "properties": {"ref": {"type": "string"}}, "required": ["ref"]},
            _h_click,
        ),
        (
            "browser_type",
            "Fill an input/textarea by ref.",
            {"type": "object", "properties": {"ref": {"type": "string"}, "text": {"type": "string"}}, "required": ["ref", "text"]},
            _h_type,
        ),
        (
            "browser_scroll",
            "Scroll the page.",
            {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                    "amount": {"type": "integer", "default": 480},
                },
            },
            _h_scroll,
        ),
        ("browser_back", "History back.", {"type": "object", "properties": {}}, _h_back),
        (
            "browser_press",
            "Key press (Enter, Tab, ArrowDown, …).",
            {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
            _h_press,
        ),
        ("browser_close", "Close session; release cloud browser if any.", {"type": "object", "properties": {}}, _h_close),
        ("browser_get_images", "List img src/alt on the page.", {"type": "object", "properties": {}}, _h_images),
        (
            "browser_vision",
            "Screenshot to ~/.io/browser_screenshots/.",
            {"type": "object", "properties": {"annotate": {"type": "boolean"}}},
            _h_vision,
        ),
        (
            "browser_console",
            "Read console lines captured for this session.",
            {"type": "object", "properties": {"clear": {"type": "boolean"}}},
            _h_console,
        ),
    ]
    for name, desc, schema, run in specs:
        GLOBAL_TOOL_REGISTRY.register(_BrowserTool(name, desc, schema, run))


_register()
