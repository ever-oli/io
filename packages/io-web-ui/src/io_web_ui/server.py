"""FastAPI demo bridge for IO."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse


HTML = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>IO Web UI</title>
  </head>
  <body>
    <h1>IO Web UI</h1>
    <p>Browser chat scaffolding is available. Connect via WebSocket at <code>/ws</code>.</p>
  </body>
</html>
"""


def create_app() -> FastAPI:
    app = FastAPI(title="IO Web UI")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def index() -> HTMLResponse:
        return HTMLResponse(HTML)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_json({"status": "connected", "message": "IO Web UI demo bridge"})
        await websocket.close()

    return app

