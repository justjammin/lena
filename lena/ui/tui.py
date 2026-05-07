from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, ListView, ListItem, Label
from textual.containers import Horizontal, Vertical
from textual import work

from ..events import EventType, LenaEvent, bus


MEGAMAN_PALETTE = {
    "bg": "#000000",
    "blue": "#0080c8",
    "red": "#c82000",
    "yellow": "#f8b800",
    "white": "#f8f8f8",
    "cyan": "#00c8c8",
    "green": "#00a800",
    "orange": "#f87858",
}

LENA_CSS = """
Screen {
    background: #000000;
    color: #f8f8f8;
}

#title {
    text-align: center;
    color: #0080c8;
    text-style: bold;
    padding: 1;
}

#stage-select {
    border: solid #0080c8;
    padding: 1;
    margin: 1;
    height: 12;
}

#boss-health {
    color: #c82000;
}

#weapon-bar {
    color: #f8b800;
}

#life-bar {
    color: #00c8c8;
}

#etanks {
    color: #00a800;
}

#log {
    border: solid #0080c8;
    height: 10;
    overflow-y: scroll;
    padding: 1;
}

.bar-fill {
    color: #f8b800;
}

.label {
    color: #f8f8f8;
    text-style: bold;
}

#routing {
    color: #f87858;
    text-align: center;
}
"""


class HealthBar(Static):
    """Unicode block-art health/energy bar."""

    def __init__(self, label: str, max_val: int = 28, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._max = max_val
        self._val = max_val

    def set_value(self, val: int) -> None:
        self._val = max(0, min(val, self._max))
        self.refresh()

    def render(self) -> str:
        filled = int((self._val / self._max) * self._max)
        bar = "█" * filled + "░" * (self._max - filled)
        return f"{self._label:<10} [{bar}] {self._val}/{self._max}"


class LenaTUI(App):
    """LENA Mega Man Terminal UI."""

    CSS = LENA_CSS

    def __init__(self, config_path: str | None = None) -> None:
        super().__init__()
        self._config_path = config_path
        self._log_lines: list[str] = []
        self._current_agent = "— READY —"
        self._routing_info = ""
        self._retries_remaining = 3

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("★ L E N A  —  MEGA MAN MODE ★", id="title")
        with Horizontal():
            with Vertical(id="left-panel"):
                yield Static("▶ STAGE SELECT", classes="label")
                yield ListView(id="stage-select")
                yield Static("", id="routing")
            with Vertical(id="right-panel"):
                yield HealthBar("BOSS HP", id="boss-health")
                yield HealthBar("WEAPON", id="weapon-bar")
                yield HealthBar("LIFE", id="life-bar")
                yield Static(self._etank_display(), id="etanks")
                yield Static(f"AGENT: {self._current_agent}", id="current-agent")
        yield Static(id="log")
        yield Footer()

    def _etank_display(self) -> str:
        tanks = "⬛" * self._retries_remaining + "⬜" * (3 - self._retries_remaining)
        return f"E-TANKS [{tanks}]"

    def _append_log(self, msg: str) -> None:
        self._log_lines.append(msg)
        if len(self._log_lines) > 50:
            self._log_lines = self._log_lines[-50:]
        log = self.query_one("#log", Static)
        log.update("\n".join(self._log_lines[-8:]))

    async def _event_listener(self) -> None:
        """Async worker: drain event bus queue and update widgets.

        Runs inside Textual's own event loop, so the asyncio.Queue returned by
        bus.subscribe() lives in the same loop that calls emit() — no cross-loop
        race conditions.
        """
        q = await bus.subscribe()
        try:
            while True:
                event: LenaEvent = await q.get()
                self._handle_event(event)
        finally:
            await bus.unsubscribe(q)

    def _handle_event(self, event: LenaEvent) -> None:
        if event.type == EventType.NODE_ENTER:
            node = event.payload.get("node", "?")
            self._append_log(f"▶ {node}")
            self.query_one("#current-agent", Static).update(f"AGENT: {node.upper()}")
        elif event.type == EventType.NODE_EXIT:
            node = event.payload.get("node", "?")
            self._append_log(f"✓ {node}")
        elif event.type == EventType.TASK_COMPLETE:
            self._append_log("★ STAGE CLEAR! ★")
            self.query_one("#boss-health", HealthBar).set_value(0)
        elif event.type == EventType.BD_CLOSE:
            self._append_log("♪ STAGE CLEAR FANFARE ♪")
        elif event.type == EventType.TASK_ERROR:
            err = event.payload.get("error", "?")
            self._retries_remaining = max(0, self._retries_remaining - 1)
            self.query_one("#etanks", Static).update(self._etank_display())
            self._append_log(f"✗ ERROR: {err[:60]}")
        elif event.type == EventType.TOKEN_USAGE:
            used = event.payload.get("used", 0)
            total = event.payload.get("total", 128000)
            pct = int((used / total) * 28) if total > 0 else 0
            self.query_one("#life-bar", HealthBar).set_value(28 - pct)
        elif event.type == EventType.ROUTING_DECISION:
            routing = event.payload.get("routing", "?")
            role = event.payload.get("role", "?")
            conf = event.payload.get("confidence", 0)
            self.query_one("#routing", Static).update(
                f"ROUTE: {routing.upper()} → {role} ({conf}%)"
            )
        elif event.type == EventType.FEEDBACK_LOOP:
            iteration = event.payload.get("iteration", 0)
            self._append_log(f"↺ FEEDBACK LOOP ×{iteration}")

    def on_mount(self) -> None:
        self.run_worker(self._event_listener(), exclusive=True)
        self._append_log("LENA BOOT — READY PLAYER ONE")
