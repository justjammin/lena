from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class EventType(str, Enum):
    NODE_ENTER = "node_enter"
    NODE_EXIT = "node_exit"
    AGENT_SPAWN = "agent_spawn"
    TASK_COMPLETE = "task_complete"
    TASK_ERROR = "task_error"
    BD_CLOSE = "bd_close"
    TOKEN_USAGE = "token_usage"
    ROUTING_DECISION = "routing_decision"
    FEEDBACK_LOOP = "feedback_loop"


@dataclass
class LenaEvent:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)


class LenaEventBus:
    """Thread-safe async pub/sub bus. Subscribers receive all events."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[LenaEvent]] = []
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[LenaEvent]:
        async with self._lock:
            q: asyncio.Queue[LenaEvent] = asyncio.Queue(maxsize=256)
            self._subscribers.append(q)
            return q

    async def unsubscribe(self, q: asyncio.Queue[LenaEvent]) -> None:
        async with self._lock:
            self._subscribers.remove(q)

    async def emit(self, event: LenaEvent) -> None:
        async with self._lock:
            for q in list(self._subscribers):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass  # drop if subscriber is slow

    def emit_sync(self, event: LenaEvent) -> None:
        """Fire-and-forget from sync context (LangGraph callback threads)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(
                    lambda: asyncio.ensure_future(self.emit(event))
                )
        except RuntimeError:
            pass  # no event loop — TUI not active, skip


# Module-level singleton
bus = LenaEventBus()
