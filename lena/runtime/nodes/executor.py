from __future__ import annotations

import logging

from ...adapters import get_adapter
from ..handoff import HandoffTransformer
from ..state import AgentState

_log = logging.getLogger(__name__)

_transformer = HandoffTransformer(cap=500)


def executor(state: AgentState) -> dict:
    model = state["model"]
    adapter = get_adapter(model)

    messages = list(state["messages"])
    prior = state.get("upstream_context")

    # Inject compressed context from upstream steps if we have prior output
    if prior or len(messages) > 2:
        compressed = _transformer.compress(messages, prior)
        # Insert as a user message right before the last user message so
        # the model sees it as task context rather than overwriting system
        context_msg = {"role": "user", "content": compressed}
        # Find insertion point: after system, before last user
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
        _log.error("executor adapter.complete failed: %s", exc)
        response = f"[executor error: {exc}]"

    assistant_msg = {"role": "assistant", "content": response}

    return {
        "messages": [assistant_msg],
        "upstream_context": response,
        "current_node": "executor",
    }
