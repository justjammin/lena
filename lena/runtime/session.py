from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from ..config import load_config
from .graph import build_graph
from .state import AgentState

_log = logging.getLogger(__name__)


def run_session(
    task: str,
    config_path: Path | None = None,
    model_override: str | None = None,
) -> AgentState:
    config = load_config(str(config_path) if config_path else None)
    graph = build_graph(config)

    mem0_session_id = str(uuid4())
    zep_session_id = str(uuid4())

    initial_state: AgentState = {
        "task": task,
        "hat": "",
        "messages": [],
        "routing_result": None,
        "memory": {},
        "cache_breakpoints": [],
        "current_node": "session_init",
        "error": None,
        "iteration": 0,
        "bd_id": None,
        "needs_feedback": False,
        "feedback_history": [],
        "upstream_context": None,
        "mem0_session_id": mem0_session_id,
        "zep_session_id": zep_session_id,
        "model": model_override or config.models.get("default", "claude-sonnet-4-6"),
        # phase 3 prereq fields
        "branch_id": None,
        "branch_results": {},
        "vector_memories": [],
        "parallel_tasks": [],
    }

    thread_config = {"configurable": {"thread_id": mem0_session_id}}

    from .hooks import LenaGraphCallbacks

    try:
        result = graph.invoke(initial_state, config=thread_config, callbacks=[LenaGraphCallbacks()])
    except Exception as exc:
        _log.error("Session failed: %s", exc)
        raise

    return result
