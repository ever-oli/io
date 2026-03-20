"""FastAPI web runtime for IO."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from io_cli.main import format_prompt_result, run_prompt
from io_cli.session import SessionManager


HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>IO Web UI</title>
    <style>
      body { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 2rem; background: #111016; color: #f4efe7; }
      h1 { margin-bottom: 0.5rem; }
      form, pre { max-width: 960px; }
      textarea, input { width: 100%; box-sizing: border-box; margin: 0.5rem 0 1rem; background: #1a1822; color: #f4efe7; border: 1px solid #3f3a4d; padding: 0.75rem; }
      button { background: #d88f2d; color: #111016; border: 0; padding: 0.75rem 1rem; font-weight: 700; cursor: pointer; }
      pre { white-space: pre-wrap; background: #1a1822; padding: 1rem; border: 1px solid #3f3a4d; }
    </style>
  </head>
  <body>
    <h1>IO Web UI</h1>
    <p>Browser chat surface for the IO runtime.</p>
    <form id="chat-form">
      <label>Prompt</label>
      <textarea id="prompt" rows="10">hello from io-web-ui</textarea>
      <button type="submit">Run</button>
    </form>
    <pre id="output">Waiting for input.</pre>
    <script>
      const form = document.getElementById("chat-form");
      const promptEl = document.getElementById("prompt");
      const outputEl = document.getElementById("output");
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        outputEl.textContent = "Running...";
        try {
          const response = await fetch("/api/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({prompt: promptEl.value})
          });
          const bodyText = await response.text();
          const payload = JSON.parse(bodyText);
          outputEl.textContent = JSON.stringify(payload, null, 2);
        } catch (error) {
          outputEl.textContent = `Request failed: ${String(error)}`;
        }
      });
    </script>
  </body>
</html>
"""


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1)
    cwd: str | None = None
    home: str | None = None
    model: str | None = None
    provider: str | None = None
    base_url: str | None = None
    toolsets: list[str] | None = None
    session_path: str | None = None
    system_prompt_suffix: str | None = None
    env_overrides: dict[str, str] | None = None
    load_extensions: bool = True


def _serialize_prompt_result(result) -> dict[str, Any]:
    return {
        "text": result.text,
        "model": result.model,
        "provider": result.provider,
        "session_path": str(result.session_path),
        "messages": result.messages,
        "loaded_extensions": result.loaded_extensions,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cache_read_tokens": result.usage.cache_read_tokens,
            "cache_write_tokens": result.usage.cache_write_tokens,
            "reasoning_tokens": result.usage.reasoning_tokens,
            "cost_usd": result.usage.cost_usd,
        },
    }


def create_app() -> FastAPI:
    app = FastAPI(title="IO Web UI")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse(HTML)

    @app.get("/api/sessions")
    async def list_sessions(cwd: str = Query(default_factory=lambda: str(Path.cwd()))) -> dict[str, Any]:
        session_paths = SessionManager.list_for_cwd(Path(cwd))
        return {
            "cwd": str(Path(cwd).resolve()),
            "sessions": [str(path) for path in session_paths],
        }

    @app.post("/api/chat")
    async def chat(request: ChatRequest) -> dict[str, Any]:
        try:
            result = await run_prompt(
                request.prompt,
                cwd=Path(request.cwd).resolve() if request.cwd else None,
                home=Path(request.home).expanduser().resolve() if request.home else None,
                model=request.model,
                provider=request.provider,
                base_url=request.base_url,
                toolsets=request.toolsets,
                session_path=Path(request.session_path).expanduser().resolve() if request.session_path else None,
                load_extensions=request.load_extensions,
                system_prompt_suffix=request.system_prompt_suffix,
                env_overrides=request.env_overrides,
                session_source="web",
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _serialize_prompt_result(result)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"status": "connected", "message": "IO Web UI runtime ready"})
        try:
            while True:
                payload = await websocket.receive_json()
                request = ChatRequest.model_validate(payload)
                result = await run_prompt(
                    request.prompt,
                    cwd=Path(request.cwd).resolve() if request.cwd else None,
                    home=Path(request.home).expanduser().resolve() if request.home else None,
                    model=request.model,
                    provider=request.provider,
                    base_url=request.base_url,
                    toolsets=request.toolsets,
                    session_path=Path(request.session_path).expanduser().resolve() if request.session_path else None,
                    load_extensions=request.load_extensions,
                    system_prompt_suffix=request.system_prompt_suffix,
                    env_overrides=request.env_overrides,
                    session_source="websocket",
                )
                await websocket.send_json(
                    {
                        "status": "ok",
                        "result": _serialize_prompt_result(result),
                        "display": format_prompt_result(result),
                    }
                )
        except WebSocketDisconnect:
            return
        except Exception as exc:
            await websocket.send_text(json.dumps({"status": "error", "error": str(exc)}))
            await websocket.close(code=1011)

    return app
