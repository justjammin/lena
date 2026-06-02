"""Tests for LangGraph runtime — routing paths + feedback loop termination."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lena.adapters.base import Completion as _Completion


def _c(text: str) -> _Completion:
    """Shorthand: text-only Completion."""
    return _Completion(content=text, tool_calls=[])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(routing: str = "direct", iteration: int = 0) -> dict:
    return {
        "task": "write a hello world script",
        "hat": "",
        "messages": [],
        "routing_result": {"routing": routing, "action": "execute", "confidence": 80, "role": None},
        "memory": {},
        "cache_breakpoints": [],
        "current_node": "session_init",
        "error": None,
        "iteration": iteration,
        "bd_id": None,
        "needs_feedback": False,
        "feedback_history": [],
        "upstream_context": None,
        "mem0_session_id": "mem-sess-1",
        "zep_session_id": "zep-sess-1",
        "model": "claude-sonnet-4-6",
        # phase 3 prereq fields
        "branch_id": None,
        "branch_results": {},
        # phase 3 additions
        "vector_memories": [],
        "parallel_tasks": [],
    }


# ---------------------------------------------------------------------------
# Routing decision tests (unit — no full graph needed)
# ---------------------------------------------------------------------------

class TestRoutingDecision:
    def test_direct_routes_to_executor(self):
        from lena.runtime.graph import _routing_decision
        state = _base_state(routing="direct")
        assert _routing_decision(state) == "executor"

    def test_orchestrate_routes_to_bd_register(self):
        from lena.runtime.graph import _routing_decision
        state = _base_state(routing="orchestrate")
        assert _routing_decision(state) == "bd_register"

    def test_mcp_routes_to_executor(self):
        from lena.runtime.graph import _routing_decision
        state = _base_state(routing="mcp")
        assert _routing_decision(state) == "executor"

    def test_none_routing_result_defaults_to_executor(self):
        from lena.runtime.graph import _routing_decision
        state = _base_state()
        state["routing_result"] = None
        assert _routing_decision(state) == "executor"

    def test_orchestrate_with_parallel_tasks_returns_send_list(self):
        """orchestrate + non-empty parallel_tasks → list[Send] for fan-out."""
        from langgraph.types import Send
        from lena.runtime.graph import _routing_decision

        state = _base_state(routing="orchestrate")
        state["parallel_tasks"] = [
            {"task": "build API", "domain": "backend", "branch_id": "b-1"},
            {"task": "write tests", "domain": "testing", "branch_id": "b-2"},
        ]

        result = _routing_decision(state)

        assert isinstance(result, list)
        assert len(result) == 2
        for send_obj in result:
            assert isinstance(send_obj, Send)
            assert send_obj.node == "branch_executor"


# ---------------------------------------------------------------------------
# Gate decision tests
# ---------------------------------------------------------------------------

class TestGateDecision:
    def test_pass_verdict_goes_to_synthesizer(self):
        from lena.runtime.graph import _gate_decision
        state = _base_state()
        state["needs_feedback"] = False
        assert _gate_decision(state) == "synthesizer"

    def test_fail_verdict_goes_to_generator(self):
        from lena.runtime.graph import _gate_decision
        state = _base_state()
        state["needs_feedback"] = True
        assert _gate_decision(state) == "generator"


# ---------------------------------------------------------------------------
# Feedback gate node — max iteration enforcement
# ---------------------------------------------------------------------------

class TestGateNode:
    def test_gate_forces_pass_at_max_iterations(self):
        from lena.runtime.nodes.feedback import gate
        state = _base_state(iteration=3)
        state["feedback_history"] = [{"iteration": 2, "output": "x", "verdict": "FAIL bad"}]
        result = gate(state)
        assert result["needs_feedback"] is False

    def test_gate_loops_on_fail_below_max(self):
        from lena.runtime.nodes.feedback import gate
        state = _base_state(iteration=1)
        state["feedback_history"] = [{"iteration": 1, "output": "x", "verdict": "FAIL needs work"}]
        result = gate(state)
        assert result["needs_feedback"] is True
        assert result["iteration"] == 2

    def test_gate_passes_on_pass_verdict(self):
        from lena.runtime.nodes.feedback import gate
        state = _base_state(iteration=1)
        state["feedback_history"] = [{"iteration": 1, "output": "x", "verdict": "PASS"}]
        result = gate(state)
        assert result["needs_feedback"] is False


# ---------------------------------------------------------------------------
# Node unit tests with mocked adapters
# ---------------------------------------------------------------------------

class TestSessionInitNode:
    def _cfg_mock(self):
        cfg = MagicMock()
        cfg.skills_dir = Path("/nonexistent")
        cfg.models = {"default": "claude-sonnet-4-6"}
        cfg.memory.zep.base_url = "http://localhost:8000"
        cfg.memory.zep.api_key = ""
        return cfg

    def test_returns_messages_and_sets_default_model_when_unset(self):
        from lena.runtime.nodes.session_init import session_init
        state = _base_state()
        state["model"] = ""  # no model override — session_init must inject default

        with (
            patch("lena.runtime.nodes.session_init._get_mem0") as mock_mem0_fn,
            patch("lena.runtime.nodes.session_init._get_zep") as mock_zep_fn,
            patch("lena.runtime.nodes.session_init.load_config") as mock_cfg,
        ):
            mock_mem0 = MagicMock()
            mock_mem0.recall.return_value = None
            mock_mem0_fn.return_value = mock_mem0
            mock_zep = MagicMock()
            mock_zep.search_facts.return_value = []
            mock_zep_fn.return_value = mock_zep
            mock_cfg.return_value = self._cfg_mock()

            result = session_init(state)

        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) >= 1
        assert result["model"] == "claude-sonnet-4-6"

    def test_preserves_cli_model_override(self):
        from lena.runtime.nodes.session_init import session_init
        state = _base_state()
        state["model"] = "ollama/llama3"  # CLI --model override

        with (
            patch("lena.runtime.nodes.session_init._get_mem0") as mock_mem0_fn,
            patch("lena.runtime.nodes.session_init._get_zep") as mock_zep_fn,
            patch("lena.runtime.nodes.session_init.load_config") as mock_cfg,
        ):
            mock_mem0 = MagicMock()
            mock_mem0.recall.return_value = None
            mock_mem0_fn.return_value = mock_mem0
            mock_zep = MagicMock()
            mock_zep.search_facts.return_value = []
            mock_zep_fn.return_value = mock_zep
            mock_cfg.return_value = self._cfg_mock()

            result = session_init(state)

        # session_init must NOT override the CLI-supplied model
        assert "model" not in result


class TestExecutorNode:
    def test_executor_calls_adapter_and_returns_upstream_context(self):
        from lena.runtime.nodes.executor import executor

        state = _base_state()
        state["messages"] = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Write hello world"},
        ]

        from lena.adapters.base import Completion

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = Completion(content="print('hello world')", tool_calls=[])

        with patch("lena.runtime.nodes.executor.get_adapter", return_value=mock_adapter):
            with patch("lena.runtime.nodes.executor._get_registry", return_value=None):
                result = executor(state)

        assert result["upstream_context"] == "print('hello world')"
        # executor no longer sets needs_feedback — routing decision belongs to graph edges
        assert "needs_feedback" not in result
        assert any(
            m.get("content") == "print('hello world')"
            for m in result["messages"]
        )


class TestSynthesizerNode:
    def test_synthesizer_remembers_and_returns_done(self):
        from lena.runtime.nodes.synthesizer import synthesizer

        state = _base_state()
        state["upstream_context"] = "the final answer"
        state["bd_id"] = None

        with (
            patch("lena.runtime.nodes.synthesizer._get_mem0") as mock_mem0_fn,
            patch("lena.runtime.nodes.synthesizer._get_zep") as mock_zep_fn,
        ):
            mock_mem0 = MagicMock()
            mock_mem0_fn.return_value = mock_mem0
            mock_zep = MagicMock()
            mock_zep_fn.return_value = mock_zep

            result = synthesizer(state)

        assert result["current_node"] == "done"
        mock_mem0.remember.assert_called_once()
        mock_zep.add_message.assert_called_once()


class TestBdRegisterNode:
    def test_bd_unavailable_returns_none_id(self):
        from lena.runtime.nodes.bd_register import bd_register
        state = _base_state()

        with patch("lena.runtime.nodes.bd_register.subprocess.run", side_effect=FileNotFoundError):
            result = bd_register(state)

        assert result["bd_id"] is None

    def test_bd_available_parses_id(self):
        import json
        from lena.runtime.nodes.bd_register import bd_register
        state = _base_state()

        mock_run = MagicMock()
        mock_run.returncode = 0
        mock_run.stdout = json.dumps({"id": "bd-abc123"})

        with patch("lena.runtime.nodes.bd_register.subprocess.run", return_value=mock_run):
            result = bd_register(state)

        assert result["bd_id"] == "bd-abc123"


# ---------------------------------------------------------------------------
# Full graph integration — direct path
# ---------------------------------------------------------------------------

class TestGraphDirectPath:
    def _build_graph_with_mocks(self, adapter_response: str = "done"):
        """Build the graph with all external calls mocked out."""
        from lena.config import Config, AdapterPattern, RoutingConfig, MemoryConfig, ObservabilityConfig, Mem0Config, ZepConfig
        from pathlib import Path

        cfg = Config(
            models={"default": "claude-sonnet-4-6"},
            adapters=[AdapterPattern(pattern="claude-*", adapter="anthropic")],
            routing=RoutingConfig(scorer_path=Path("/nonexistent"), threshold=70),
            memory=MemoryConfig(
                backend="mem0",
                mem0=Mem0Config(vector_store={}, embedder={}),
                zep=ZepConfig(base_url="http://localhost:8000", api_key=""),
            ),
            observability=ObservabilityConfig(langfuse={}, otel_endpoint=""),
            skills_dir=Path("/nonexistent"),
        )
        from lena.runtime.graph import build_graph
        return build_graph(cfg), cfg

    def test_direct_path_completes(self):
        graph, _ = self._build_graph_with_mocks()

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = _c("PASS — looks good")

        state = _base_state(routing="direct")

        with (
            patch("lena.runtime.nodes.session_init._get_mem0") as m_mem0,
            patch("lena.runtime.nodes.session_init._get_zep") as m_zep,
            patch("lena.runtime.nodes.session_init.load_config") as m_cfg,
            patch("lena.runtime.nodes.router_node.RouterNode") as m_router_cls,
            patch("lena.runtime.nodes.executor.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.executor._get_registry", return_value=None),
            patch("lena.runtime.nodes.feedback.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.synthesizer._get_mem0") as s_mem0,
            patch("lena.runtime.nodes.synthesizer._get_zep") as s_zep,
            patch("lena.runtime.nodes.vector_recall._get_vector_adapter", return_value=None),
            patch("lena.runtime.nodes.vector_recall.load_config") as m_vr_cfg,
            patch("lena.runtime.nodes.consolidation._get_vector_adapter", return_value=None),
        ):
            # session_init mocks
            mm = MagicMock(); mm.recall.return_value = None; m_mem0.return_value = mm
            mz = MagicMock(); mz.search_facts.return_value = []; m_zep.return_value = mz
            cfg_mock = MagicMock()
            cfg_mock.skills_dir = Path("/nonexistent")
            cfg_mock.models = {"default": "claude-sonnet-4-6"}
            cfg_mock.memory.zep.base_url = "http://localhost:8000"
            cfg_mock.memory.zep.api_key = ""
            cfg_mock.team_moat.top_k = 5
            m_cfg.return_value = cfg_mock
            m_vr_cfg.return_value = cfg_mock

            # router mock — direct routing
            router_inst = MagicMock()
            router_inst.route.return_value = {
                "routing": "direct", "action": "execute",
                "confidence": 80, "role": None,
            }
            m_router_cls.return_value = router_inst

            # synthesizer mocks
            sm = MagicMock(); s_mem0.return_value = sm
            sz = MagicMock(); s_zep.return_value = sz

            result = graph.invoke(
                state,
                config={"configurable": {"thread_id": "test-thread-1"}},
            )

        assert result.get("current_node") == "done"
        # Direct path: executor runs once, no generator invoked (needs_feedback=False)
        # Adapter called for executor only
        assert mock_adapter.complete.call_count == 1

    def test_orchestrate_path_hits_bd_register(self):
        graph, _ = self._build_graph_with_mocks()

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = _c("PASS — looks good")

        state = _base_state(routing="orchestrate")
        state["routing_result"] = {
            "routing": "orchestrate", "action": "execute",
            "confidence": 80, "role": None,
        }

        with (
            patch("lena.runtime.nodes.session_init._get_mem0") as m_mem0,
            patch("lena.runtime.nodes.session_init._get_zep") as m_zep,
            patch("lena.runtime.nodes.session_init.load_config") as m_cfg,
            patch("lena.runtime.nodes.router_node.RouterNode") as m_router_cls,
            patch("lena.runtime.nodes.executor.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.executor._get_registry", return_value=None),
            patch("lena.runtime.nodes.feedback.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.synthesizer._get_mem0") as s_mem0,
            patch("lena.runtime.nodes.synthesizer._get_zep") as s_zep,
            patch("lena.runtime.nodes.bd_register.subprocess.run") as mock_bd,
            patch("lena.runtime.nodes.vector_recall._get_vector_adapter", return_value=None),
            patch("lena.runtime.nodes.vector_recall.load_config") as m_vr_cfg,
            patch("lena.runtime.nodes.consolidation._get_vector_adapter", return_value=None),
        ):
            import json
            mm = MagicMock(); mm.recall.return_value = None; m_mem0.return_value = mm
            mz = MagicMock(); mz.search_facts.return_value = []; m_zep.return_value = mz
            cfg_mock = MagicMock()
            cfg_mock.skills_dir = Path("/nonexistent")
            cfg_mock.models = {"default": "claude-sonnet-4-6"}
            cfg_mock.memory.zep.base_url = "http://localhost:8000"
            cfg_mock.memory.zep.api_key = ""
            cfg_mock.team_moat.top_k = 5
            m_cfg.return_value = cfg_mock
            m_vr_cfg.return_value = cfg_mock

            # router returns orchestrate
            router_inst = MagicMock()
            router_inst.route.return_value = {
                "routing": "orchestrate", "action": "execute",
                "confidence": 60, "role": None,
            }
            m_router_cls.return_value = router_inst

            mock_bd_result = MagicMock()
            mock_bd_result.returncode = 0
            mock_bd_result.stdout = json.dumps({"id": "bd-test-99"})
            mock_bd.return_value = mock_bd_result

            sm = MagicMock(); s_mem0.return_value = sm
            sz = MagicMock(); s_zep.return_value = sz

            result = graph.invoke(
                state,
                config={"configurable": {"thread_id": "test-thread-2"}},
            )

        assert result.get("current_node") == "done"

    def test_orchestrate_parallel_path_completes(self):
        """orchestrate + parallel_tasks → branch_executor runs per task → merge → synthesizer → done."""
        graph, _ = self._build_graph_with_mocks()

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = _c("branch output")

        state = _base_state(routing="orchestrate")
        state["parallel_tasks"] = [
            {"task": "build API", "domain": "backend", "branch_id": "b-1"},
            {"task": "write tests", "domain": "testing", "branch_id": "b-2"},
        ]

        with (
            patch("lena.runtime.nodes.session_init._get_mem0") as m_mem0,
            patch("lena.runtime.nodes.session_init._get_zep") as m_zep,
            patch("lena.runtime.nodes.session_init.load_config") as m_cfg,
            patch("lena.runtime.nodes.router_node.RouterNode") as m_router_cls,
            patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.executor._get_registry", return_value=None),
            patch("lena.runtime.nodes.synthesizer._get_mem0") as s_mem0,
            patch("lena.runtime.nodes.synthesizer._get_zep") as s_zep,
            patch("lena.runtime.nodes.vector_recall._get_vector_adapter", return_value=None),
            patch("lena.runtime.nodes.vector_recall.load_config") as m_vr_cfg,
            patch("lena.runtime.nodes.consolidation._get_vector_adapter", return_value=None),
        ):
            from pathlib import Path

            mm = MagicMock(); mm.recall.return_value = None; m_mem0.return_value = mm
            mz = MagicMock(); mz.search_facts.return_value = []; m_zep.return_value = mz
            cfg_mock = MagicMock()
            cfg_mock.skills_dir = Path("/nonexistent")
            cfg_mock.models = {"default": "claude-sonnet-4-6"}
            cfg_mock.memory.zep.base_url = "http://localhost:8000"
            cfg_mock.memory.zep.api_key = ""
            cfg_mock.team_moat.top_k = 5
            m_cfg.return_value = cfg_mock
            m_vr_cfg.return_value = cfg_mock

            router_inst = MagicMock()
            router_inst.route.return_value = {
                "routing": "orchestrate", "action": "execute",
                "confidence": 75, "role": None,
                "domains": ["backend", "testing"],
            }
            m_router_cls.return_value = router_inst

            sm = MagicMock(); s_mem0.return_value = sm
            sz = MagicMock(); s_zep.return_value = sz

            result = graph.invoke(
                state,
                config={"configurable": {"thread_id": "test-thread-parallel"}},
            )

        assert result.get("current_node") == "done"
        # branch_executor called once per task (one per domain from router)
        assert mock_adapter.complete.call_count == 2
        # branch_results must contain both branches (branch_ids are domain-prefixed)
        branch_results = result.get("branch_results", {})
        assert len(branch_results) == 2
        branch_domains = [bid.split("-")[0] for bid in branch_results]
        assert "backend" in branch_domains
        assert "testing" in branch_domains

    def test_feedback_loop_terminates_after_max_iterations(self):
        """Critic always returns FAIL — loop must enter, iterate, then terminate at max."""
        graph, _ = self._build_graph_with_mocks()

        mock_adapter = MagicMock()
        # Every adapter call returns FAIL so the loop exercises all iterations.
        mock_adapter.complete.return_value = _c("FAIL — needs improvement")

        state = _base_state(routing="direct")
        # Force the feedback path: action="review" causes router_node to set
        # needs_feedback=True and _executor_decision to route to generator.
        state["routing_result"]["action"] = "review"

        with (
            patch("lena.runtime.nodes.session_init._get_mem0") as m_mem0,
            patch("lena.runtime.nodes.session_init._get_zep") as m_zep,
            patch("lena.runtime.nodes.session_init.load_config") as m_cfg,
            patch("lena.runtime.nodes.router_node.RouterNode") as m_router_cls,
            patch("lena.runtime.nodes.executor.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.executor._get_registry", return_value=None),
            patch("lena.runtime.nodes.feedback.get_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.synthesizer._get_mem0") as s_mem0,
            patch("lena.runtime.nodes.synthesizer._get_zep") as s_zep,
            patch("lena.runtime.nodes.vector_recall._get_vector_adapter", return_value=None),
            patch("lena.runtime.nodes.vector_recall.load_config") as m_vr_cfg,
            patch("lena.runtime.nodes.consolidation._get_vector_adapter", return_value=None),
        ):
            mm = MagicMock(); mm.recall.return_value = None; m_mem0.return_value = mm
            mz = MagicMock(); mz.search_facts.return_value = []; m_zep.return_value = mz
            cfg_mock = MagicMock()
            cfg_mock.skills_dir = Path("/nonexistent")
            cfg_mock.models = {"default": "claude-sonnet-4-6"}
            cfg_mock.memory.zep.base_url = "http://localhost:8000"
            cfg_mock.memory.zep.api_key = ""
            cfg_mock.team_moat.top_k = 5
            m_cfg.return_value = cfg_mock
            m_vr_cfg.return_value = cfg_mock

            # Router returns action="review" so router_node sets needs_feedback=True.
            router_inst = MagicMock()
            router_inst.route.return_value = {
                "routing": "direct", "action": "review",
                "confidence": 80, "role": None,
            }
            m_router_cls.return_value = router_inst

            sm = MagicMock(); s_mem0.return_value = sm
            sz = MagicMock(); s_zep.return_value = sz

            result = graph.invoke(
                state,
                config={"configurable": {"thread_id": "test-thread-3"}},
            )

        # Loop must terminate — gate forces synthesizer after max iterations.
        assert result.get("current_node") == "done"
        assert result.get("iteration", 0) <= 3

        # Adapter must have been called at minimum: executor + generator + critic
        # (3 calls for iteration 1 alone). With 3 FAIL cycles: executor + 3*(gen+critic) = 7.
        assert mock_adapter.complete.call_count >= 3, (
            f"Expected >= 3 adapter calls (executor+generator+critic), "
            f"got {mock_adapter.complete.call_count}"
        )

        # feedback_history must have entries — loop actually ran.
        feedback_history = result.get("feedback_history", [])
        assert len(feedback_history) >= 1, (
            f"Expected feedback_history to have entries after feedback loop, "
            f"got {feedback_history}"
        )
