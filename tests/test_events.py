from __future__ import annotations

import asyncio

import pytest

from lena.events import EventType, LenaEvent, LenaEventBus, bus


@pytest.fixture(autouse=True)
def _reset_bus():
    bus._subscribers.clear()
    yield
    bus._subscribers.clear()


class TestLenaEventBus:
    def test_subscribe_returns_queue(self):
        async def _run():
            q = await bus.subscribe()
            assert isinstance(q, asyncio.Queue)

        asyncio.run(_run())

    def test_emit_delivers_to_subscriber(self):
        async def _run():
            q = await bus.subscribe()
            event = LenaEvent(type=EventType.NODE_ENTER, payload={"node": "router"})
            await bus.emit(event)
            received = q.get_nowait()
            assert received.type == EventType.NODE_ENTER
            assert received.payload["node"] == "router"

        asyncio.run(_run())

    def test_multiple_subscribers_each_receive(self):
        async def _run():
            q1 = await bus.subscribe()
            q2 = await bus.subscribe()
            event = LenaEvent(type=EventType.TASK_COMPLETE)
            await bus.emit(event)
            assert q1.get_nowait().type == EventType.TASK_COMPLETE
            assert q2.get_nowait().type == EventType.TASK_COMPLETE

        asyncio.run(_run())

    def test_unsubscribe_stops_delivery(self):
        async def _run():
            q = await bus.subscribe()
            await bus.unsubscribe(q)
            await bus.emit(LenaEvent(type=EventType.NODE_EXIT))
            assert q.empty()

        asyncio.run(_run())

    def test_queue_full_drops_silently(self):
        async def _run():
            q = await bus.subscribe()
            # Fill to maxsize=256
            for _ in range(256):
                q.put_nowait(LenaEvent(type=EventType.NODE_ENTER))
            # One more via emit should silently drop, not raise
            await bus.emit(LenaEvent(type=EventType.NODE_EXIT))
            assert q.full()

        asyncio.run(_run())

    def test_emit_sync_no_loop_does_not_crash(self):
        asyncio.set_event_loop(None)
        bus.emit_sync(LenaEvent(type=EventType.NODE_ENTER))
