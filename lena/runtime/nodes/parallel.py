from __future__ import annotations

import logging

from langgraph.types import Send

from ...adapters import get_adapter
from ..handoff import HandoffTransformer
from ..state import AgentState

_log = logging.getLogger(__name__)

_transformer = HandoffTransformer(cap=500)


def fan_out_node(state: AgentState) -> list[Send]:
    """Fan out parallel tasks when routing is 'orchestrate' and parallel_tasks is non-empty.

    Returns a list of Send objects — LangGraph dispatches each to branch_executor
    concurrently and waits for all to complete before advancing.
    Falls back to a single Send to 'executor' when parallel_tasks is empty.
    """
    tasks: list[dict] = state.get("parallel_tasks") or []

    if not tasks:
        # Degenerate case: orchestrate with no parallel tasks → single execution.
        return [Send("executor", state)]

    sends = []
    for task_entry in tasks:
        branch_state = {
            **state,
            "task": task_entry["task"],
            "branch_id": task_entry["branch_id"],
        }
        sends.append(Send("branch_executor", branch_state))

    return sends


def branch_executor(state: AgentState) -> dict:
    """Execute a single parallel branch; write results to branch_results[branch_id].

    Never writes to the .lena-hat file — hat is tracked only in AgentState.
    """
    branch_id = state.get("branch_id") or "default"
    model = state["model"]
    adapter = get_adapter(model)

    messages = list(state["messages"])
    prior = state.get("upstream_context")

    if prior or len(messages) > 2:
        compressed = _transformer.compress(messages, prior)
        context_msg = {"role": "user", "content": compressed}
        insert_at = len(messages)
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                insert_at = i
                break
        messages = messages[:insert_at] + [context_msg] + messages[insert_at:]

    try:
        response = adapter.complete(
            messages,
            cache_breakpoints=state.get("cache_breakpoints") or None,
            model=model,
        )
    except Exception as exc:
        _log.error("branch_executor[%s] adapter.complete failed: %s", branch_id, exc)
        response = f"[branch_executor error: {exc}]"

    return {
        "branch_results": {
            branch_id: {"output": response, "model": model},
        },
    }


def merge_node(state: AgentState) -> dict:
    """Collapse branch_results into a single upstream_context summary."""
    branch_results: dict = state.get("branch_results") or {}

    if not branch_results:
        return {"upstream_context": state.get("upstream_context"), "needs_feedback": False}

    parts = ["## Branch Results"]
    for branch_id, result in branch_results.items():
        output = result.get("output", "")
        parts.append(f"\n### {branch_id}\n{output}")

    merged = "\n".join(parts)
    return {"upstream_context": merged, "needs_feedback": False}
