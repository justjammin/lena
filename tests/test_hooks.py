from __future__ import annotations

import pytest

from lena.events import EventType, LenaEvent, bus
from lena.runtime.hooks import LenaGraphCallbacks


@pytest.fixture(autouse=True)
def _reset_bus():
    bus._subscribers.clear()
    yield
    bus._subscribers.clear()


@pytest.fixture()
def captured_events(monkeypatch):
    events: list[LenaEvent] = []
    monkeypatch.setattr(bus, "emit_sync", lambda e: events.append(e))
    return events


class TestLenaGraphCallbacks:
    def test_on_chain_start_emits_node_enter(self, captured_events):
        cb = LenaGraphCallbacks()
        cb.on_chain_start(
            serialized={"id": ["", "", "router"]},
            inputs={"task": "x"},
        )
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.type == EventType.NODE_ENTER
        assert event.payload["node"] == "router"

    def test_on_chain_end_emits_node_exit(self, captured_events):
        cb = LenaGraphCallbacks()
        cb.on_chain_end(outputs={"result": "y"}, name="executor")
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.type == EventType.NODE_EXIT
        assert event.payload["node"] == "executor"

    def test_on_chain_error_emits_task_error(self, captured_events):
        cb = LenaGraphCallbacks()
        cb.on_chain_error(RuntimeError("boom"))
        assert len(captured_events) == 1
        event = captured_events[0]
        assert event.type == EventType.TASK_ERROR
        assert event.payload["error"] == "boom"
