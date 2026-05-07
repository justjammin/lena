from __future__ import annotations

import logging
import subprocess

from ...memory.mem0_adapter import Mem0Adapter
from ...memory.zep_adapter import ZepAdapter
from ...config import load_config
from ..state import AgentState

_log = logging.getLogger(__name__)

_mem0: Mem0Adapter | None = None
_zep: ZepAdapter | None = None


def _get_mem0() -> Mem0Adapter:
    global _mem0
    if _mem0 is None:
        _mem0 = Mem0Adapter()
    return _mem0


def _get_zep() -> ZepAdapter:
    global _zep
    if _zep is None:
        cfg = load_config()
        _zep = ZepAdapter(
            base_url=cfg.memory.zep.base_url,
            api_key=cfg.memory.zep.api_key,
        )
    return _zep


def synthesizer(state: AgentState) -> dict:
    bd_id = state.get("bd_id")
    response_summary = state.get("upstream_context") or ""
    mem0_session = state["mem0_session_id"]
    zep_session = state["zep_session_id"]

    # Close bd issue if we registered one
    if bd_id:
        reason = response_summary[:200].replace("\n", " ")
        try:
            subprocess.run(
                ["bd", "close", bd_id, "--reason", reason],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
            _log.warning("bd close failed: %s", exc)

    # Persist result to mem0
    summary = response_summary[:1000]  # keep it bounded
    _get_mem0().remember("last_task_result", summary, mem0_session)

    # Add to Zep session
    _get_zep().add_message(zep_session, "assistant", summary)

    return {"current_node": "done"}
