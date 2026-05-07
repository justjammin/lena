from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from lena.events import bus
from lena.ui import web as wmod
from lena.ui.web import create_app


@pytest.fixture(autouse=True)
def _reset_bus():
    bus._subscribers.clear()
    yield
    bus._subscribers.clear()


@pytest.fixture()
def app():
    return create_app()


class TestWebApp:
    def test_index_returns_html(self, app):
        with TestClient(app) as client:
            response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.skip(reason="cross-loop event delivery unreliable with TestClient thread isolation")
    def test_websocket_receives_event(self, app):
        from lena.events import EventType, LenaEvent

        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                asyncio.run(bus.emit(LenaEvent(type=EventType.NODE_ENTER, payload={"node": "test"})))
                msg = ws.receive_json()
                assert msg["type"] == EventType.NODE_ENTER.value

    def test_websocket_ping_on_timeout(self, monkeypatch):
        async def _immediate_timeout(coro, timeout):
            coro.close()
            raise asyncio.TimeoutError

        monkeypatch.setattr(wmod.asyncio, "wait_for", _immediate_timeout)
        app = wmod.create_app()
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "ping"
