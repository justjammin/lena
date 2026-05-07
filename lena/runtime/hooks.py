from __future__ import annotations

from langchain_core.callbacks import BaseCallbackHandler

from ..events import EventType, LenaEvent, bus


class LenaGraphCallbacks(BaseCallbackHandler):
    """Emits LenaEvents on LangGraph node transitions."""

    def on_chain_start(self, serialized: dict, inputs: dict, **kwargs) -> None:
        node = serialized.get("id", ["", "", "unknown"])[-1]
        bus.emit_sync(LenaEvent(
            type=EventType.NODE_ENTER,
            payload={"node": node, "inputs_keys": list(inputs.keys())},
        ))

    def on_chain_end(self, outputs: dict, **kwargs) -> None:
        node = kwargs.get("name", "unknown")
        bus.emit_sync(LenaEvent(
            type=EventType.NODE_EXIT,
            payload={"node": node, "output_keys": list(outputs.keys())},
        ))

    def on_chain_error(self, error: Exception, **kwargs) -> None:
        bus.emit_sync(LenaEvent(
            type=EventType.TASK_ERROR,
            payload={"error": str(error)},
        ))
