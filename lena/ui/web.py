from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..events import LenaEvent, bus

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(config_path: str | None = None) -> FastAPI:
    app = FastAPI(title="LENA — Mega Man UI")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        html = (_STATIC_DIR / "index.html").read_text()
        return html

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        q = await bus.subscribe()
        try:
            while True:
                try:
                    event: LenaEvent = await asyncio.wait_for(q.get(), timeout=30.0)
                    await ws.send_text(json.dumps({
                        "type": event.type.value,
                        "payload": event.payload,
                    }))
                except asyncio.TimeoutError:
                    # keepalive ping
                    await ws.send_text(json.dumps({"type": "ping"}))
        except WebSocketDisconnect:
            pass
        finally:
            await bus.unsubscribe(q)

    return app
