from __future__ import annotations

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from ..config import Config
from .nodes.bd_register import bd_register
from .nodes.consolidation import consolidation_node
from .nodes.executor import executor
from .nodes.feedback import critic, gate, generator
from .nodes.parallel import branch_executor, fan_out_node, merge_node
from .nodes.router_node import router_node
from .nodes.session_init import session_init
from .nodes.synthesizer import synthesizer
from .nodes.vector_recall import vector_recall_node
from .state import AgentState

_log = logging.getLogger(__name__)


def _routing_decision(state: AgentState):
    """Map routing_result to next node or Send list for parallel fan-out.

    Three paths:
    - orchestrate + parallel_tasks non-empty → list[Send] via fan_out_node (parallel fan-out)
    - orchestrate + no parallel_tasks       → "bd_register"
    - direct / mcp                          → "executor"

    Returning list[Send] from a conditional edge function is the correct LangGraph 0.2
    mechanism for fan-out — Send objects are only interpreted when returned from here,
    not from a regular add_node-registered node.
    """
    result = state.get("routing_result")
    if result is None:
        return "executor"
    routing = result.get("routing", "mcp")
    if routing == "orchestrate":
        tasks = state.get("parallel_tasks") or []
        if tasks:
            return fan_out_node(state)
        return "bd_register"
    # "direct" and "mcp" both go straight to executor
    return "executor"


def _executor_decision(state: AgentState) -> str:
    """After executor: go to generator/critic loop when the router requested a review
    (action == "review") or when router_node pre-set needs_feedback=True.
    Default: executor output goes straight to synthesizer (no wasted LLM calls).
    """
    routing_result = state.get("routing_result") or {}
    if routing_result.get("action") == "review" or state.get("needs_feedback", False):
        return "generator"
    return "synthesizer"


def _gate_decision(state: AgentState) -> str:
    """Edge function: after gate, decide loop or proceed."""
    if state.get("needs_feedback", False):
        return "generator"
    return "synthesizer"


def build_graph(config: Config):  # -> CompiledGraph
    graph = StateGraph(AgentState)

    # --- Register nodes ---
    graph.add_node("session_init", session_init)
    graph.add_node("vector_recall", vector_recall_node)
    graph.add_node("router_node", router_node)
    graph.add_node("bd_register", bd_register)
    graph.add_node("executor", executor)
    graph.add_node("generator", generator)
    graph.add_node("critic", critic)
    graph.add_node("gate", gate)
    graph.add_node("synthesizer", synthesizer)
    graph.add_node("consolidation_node", consolidation_node)
    # Parallel nodes — fan_out_node is NOT registered here; it runs as a conditional edge
    # function so its list[Send] return is interpreted as fan-out by LangGraph.
    graph.add_node("branch_executor", branch_executor)
    graph.add_node("merge_node", merge_node)

    # --- Entry point ---
    graph.set_entry_point("session_init")

    # session_init → vector_recall → router_node
    graph.add_edge("session_init", "vector_recall")
    graph.add_edge("vector_recall", "router_node")

    # router_node → branch_executor (orchestrate+parallel, via Send) OR bd_register OR executor
    # When _routing_decision returns list[Send], LangGraph dispatches each Send to branch_executor.
    graph.add_conditional_edges(
        "router_node",
        _routing_decision,
        {
            "branch_executor": "branch_executor",
            "bd_register": "bd_register",
            "executor": "executor",
        },
    )

    # bd_register → executor
    graph.add_edge("bd_register", "executor")

    # Parallel path: fan_out_node sends to branch_executor (N copies); all converge → merge_node
    # fan_out_node returns list[Send] — LangGraph handles fan-out; merge_node is the join point.
    graph.add_edge("branch_executor", "merge_node")

    # merge_node output feeds into synthesizer
    graph.add_edge("merge_node", "synthesizer")

    # executor: default path → synthesizer; feedback path → generator → critic → gate
    graph.add_conditional_edges(
        "executor",
        _executor_decision,
        {
            "synthesizer": "synthesizer",
            "generator": "generator",
        },
    )

    # generator → critic
    graph.add_edge("generator", "critic")

    # critic → gate
    graph.add_edge("critic", "gate")

    # gate: PASS → synthesizer; FAIL → generator (loop, max 3 enforced in gate node)
    graph.add_conditional_edges(
        "gate",
        _gate_decision,
        {
            "generator": "generator",
            "synthesizer": "synthesizer",
        },
    )

    # synthesizer → consolidation_node → END
    graph.add_edge("synthesizer", "consolidation_node")
    graph.add_edge("consolidation_node", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
