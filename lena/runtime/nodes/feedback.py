from __future__ import annotations

import logging

from ...adapters import get_adapter
from ..state import AgentState

_log = logging.getLogger(__name__)

_MAX_ITERATIONS = 3


def generator(state: AgentState) -> dict:
    """Generate a solution for the task."""
    model = state["model"]
    adapter = get_adapter(model)

    messages = list(state["messages"]) + [
        {
            "role": "user",
            "content": (
                "Please generate a thorough solution for the task above. "
                "Be specific and complete."
            ),
        }
    ]

    try:
        output = adapter.complete(messages, model=model)
    except Exception as exc:
        _log.error("feedback.generator failed: %s", exc)
        output = f"[generator error: {exc}]"

    return {
        "upstream_context": output,
        "messages": [{"role": "assistant", "content": output}],
        "current_node": "generator",
    }


def critic(state: AgentState) -> dict:
    """Review the generator output and return PASS or FAIL with a reason."""
    model = state["model"]
    adapter = get_adapter(model)
    output = state.get("upstream_context", "")

    messages = list(state["messages"]) + [
        {
            "role": "user",
            "content": (
                f"Review the following response for quality, correctness, and completeness. "
                f"Reply with PASS if acceptable or FAIL followed by a brief reason if not.\n\n"
                f"Response to review:\n{output}"
            ),
        }
    ]

    try:
        verdict = adapter.complete(messages, model=model)
    except Exception as exc:
        _log.error("feedback.critic failed: %s", exc)
        verdict = "PASS"  # fail open — don't loop on adapter error

    entry = {
        "iteration": state.get("iteration", 0),
        "output": output,
        "verdict": verdict,
    }

    return {
        "feedback_history": [entry],
        "messages": [{"role": "assistant", "content": verdict}],
        "current_node": "critic",
    }


def gate(state: AgentState) -> dict:
    """Decide whether to loop (FAIL) or proceed (PASS). Max 3 iterations enforced here."""
    iteration = state.get("iteration", 0)
    history = state.get("feedback_history", [])
    latest_verdict = (history[-1].get("verdict", "") if history else "").upper()

    # Hard cap — never loop beyond max regardless of verdict
    if iteration >= _MAX_ITERATIONS:
        _log.warning("gate: reached max iterations (%d), forcing PASS", _MAX_ITERATIONS)
        return {"needs_feedback": False, "current_node": "gate"}

    if latest_verdict.startswith("FAIL"):
        return {
            "needs_feedback": True,
            "iteration": iteration + 1,
            "current_node": "gate",
        }

    return {"needs_feedback": False, "current_node": "gate"}
