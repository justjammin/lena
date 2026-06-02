from __future__ import annotations

import operator
from typing import Annotated, Any

from typing_extensions import TypedDict

from ..adapters.base import Message
from .router import RouteResult


def _add_messages(left: list[Message], right: list[Message]) -> list[Message]:
    """Append-only reducer for messages — LangGraph merges partial state updates."""
    return left + right


def _merge_branch_results(left: dict, right: dict) -> dict:
    """Last-write-wins merge for parallel branch result dicts."""
    return {**left, **right}


class AgentState(TypedDict):
    # --- core (existing) ---
    hat: str
    messages: Annotated[list[Message], _add_messages]
    task: str
    routing_result: RouteResult | None
    memory: dict[str, Any]
    cache_breakpoints: list[int]
    current_node: str
    error: str | None
    iteration: int
    # --- phase 2 additions ---
    bd_id: str | None
    needs_feedback: bool
    feedback_history: Annotated[list[dict], operator.add]
    upstream_context: str | None
    mem0_session_id: str
    zep_session_id: str
    model: str
    # --- phase 3 prereqs ---
    branch_id: str | None
    branch_results: Annotated[dict[str, dict], _merge_branch_results]
    # --- phase 3 additions ---
    vector_memories: list[dict]
    parallel_tasks: list[dict]
    domain: str
