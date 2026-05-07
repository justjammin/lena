from __future__ import annotations

import logging
from uuid import uuid4

from ...config import load_config
from ..router import RouterNode
from ..state import AgentState

_log = logging.getLogger(__name__)

# Maximum parallel branches to spawn — caps cost and LangGraph fan-out width.
_MAX_PARALLEL_BRANCHES = 4


def router_node(state: AgentState) -> dict:
    config = load_config()
    scorer_path = config.routing.scorer_path
    threshold = config.routing.threshold

    node = RouterNode(scorer_path=scorer_path, threshold=threshold)
    result = node.route(state["task"])

    _log.debug("routing result: %s", result)

    needs_feedback = result.get("action") == "review"

    if result.get("routing") == "orchestrate":
        domains = result.get("domains") or []
        if domains:
            parallel_tasks = [
                {
                    "task": state["task"],
                    "domain": d,
                    "branch_id": f"{d}-{uuid4().hex[:8]}",
                }
                for d in domains[:_MAX_PARALLEL_BRANCHES]
            ]
        else:
            parallel_tasks = []
    else:
        parallel_tasks = []

    return {
        "routing_result": result,
        "hat": result.get("role") or "",
        "needs_feedback": needs_feedback,
        "parallel_tasks": parallel_tasks,
        "current_node": "router_node",
    }
