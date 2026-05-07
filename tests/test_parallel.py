"""Tests for parallel execution nodes — fan_out, branch_executor, merge_node."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> dict:
    state = {
        "task": "write a hello world script",
        "hat": "",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "write a hello world script"},
        ],
        "routing_result": {"routing": "orchestrate", "action": "execute", "confidence": 80, "role": None},
        "memory": {},
        "cache_breakpoints": [],
        "current_node": "router_node",
        "error": None,
        "iteration": 0,
        "bd_id": None,
        "needs_feedback": False,
        "feedback_history": [],
        "upstream_context": None,
        "mem0_session_id": "mem-sess-1",
        "zep_session_id": "zep-sess-1",
        "model": "claude-sonnet-4-6",
        "branch_id": None,
        "branch_results": {},
        "vector_memories": [],
        "parallel_tasks": [],
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# fan_out_node
# ---------------------------------------------------------------------------

class TestFanOutNode:
    def test_fan_out_produces_send_list_for_each_task(self):
        from langgraph.types import Send
        from lena.runtime.nodes.parallel import fan_out_node

        tasks = [
            {"task": "build API", "domain": "backend", "branch_id": "branch-1"},
            {"task": "write tests", "domain": "testing", "branch_id": "branch-2"},
            {"task": "update docs", "domain": "documentation", "branch_id": "branch-3"},
        ]
        state = _base_state(parallel_tasks=tasks)

        result = fan_out_node(state)

        assert isinstance(result, list)
        assert len(result) == 3
        for send_obj in result:
            assert isinstance(send_obj, Send)

    def test_fan_out_sets_correct_node_name(self):
        from langgraph.types import Send
        from lena.runtime.nodes.parallel import fan_out_node

        tasks = [
            {"task": "task A", "domain": "backend", "branch_id": "b-1"},
        ]
        state = _base_state(parallel_tasks=tasks)

        result = fan_out_node(state)

        assert result[0].node == "branch_executor"

    def test_fan_out_sets_task_and_branch_id_in_send_state(self):
        from lena.runtime.nodes.parallel import fan_out_node

        tasks = [
            {"task": "task A", "domain": "backend", "branch_id": "branch-A"},
            {"task": "task B", "domain": "testing", "branch_id": "branch-B"},
        ]
        state = _base_state(parallel_tasks=tasks)

        result = fan_out_node(state)

        # Each Send carries the overridden task + branch_id
        send_a = result[0]
        assert send_a.arg["task"] == "task A"
        assert send_a.arg["branch_id"] == "branch-A"

        send_b = result[1]
        assert send_b.arg["task"] == "task B"
        assert send_b.arg["branch_id"] == "branch-B"

    def test_fan_out_empty_tasks_sends_to_executor(self):
        from langgraph.types import Send
        from lena.runtime.nodes.parallel import fan_out_node

        state = _base_state(parallel_tasks=[])

        result = fan_out_node(state)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].node == "executor"

    def test_fan_out_none_tasks_sends_to_executor(self):
        from langgraph.types import Send
        from lena.runtime.nodes.parallel import fan_out_node

        state = _base_state(parallel_tasks=None)

        result = fan_out_node(state)

        assert len(result) == 1
        assert result[0].node == "executor"


# ---------------------------------------------------------------------------
# branch_executor
# ---------------------------------------------------------------------------

class TestBranchExecutor:
    def test_branch_executor_writes_to_branch_results(self):
        from lena.runtime.nodes.parallel import branch_executor

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = "branch output here"

        state = _base_state(branch_id="branch-1", task="do the backend task")

        with patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter):
            result = branch_executor(state)

        assert "branch_results" in result
        assert "branch-1" in result["branch_results"]
        assert result["branch_results"]["branch-1"]["output"] == "branch output here"

    def test_branch_executor_records_model_in_result(self):
        from lena.runtime.nodes.parallel import branch_executor

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = "output"

        state = _base_state(branch_id="branch-2", model="gpt-5.5")

        with patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter):
            result = branch_executor(state)

        assert result["branch_results"]["branch-2"]["model"] == "gpt-5.5"

    def test_branch_executor_handles_adapter_failure_gracefully(self):
        from lena.runtime.nodes.parallel import branch_executor

        mock_adapter = MagicMock()
        mock_adapter.complete.side_effect = RuntimeError("adapter down")

        state = _base_state(branch_id="branch-err")

        with patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter):
            result = branch_executor(state)

        # Should not raise — error message stored in output
        assert "branch-err" in result["branch_results"]
        assert "branch_executor error" in result["branch_results"]["branch-err"]["output"]

    def test_branch_executor_never_writes_hat_file(self, tmp_path, monkeypatch):
        """Confirm no .lena-hat file is created during branch execution."""
        import os
        from lena.runtime.nodes.parallel import branch_executor

        monkeypatch.chdir(tmp_path)

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = "output"

        state = _base_state(branch_id="branch-hat-check", hat="backend-developer")

        with patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter):
            branch_executor(state)

        hat_files = list(tmp_path.glob(".lena-hat*"))
        assert hat_files == [], f"Unexpected hat file(s) written: {hat_files}"

    def test_branch_executor_default_branch_id_when_none(self):
        from lena.runtime.nodes.parallel import branch_executor

        mock_adapter = MagicMock()
        mock_adapter.complete.return_value = "output"

        state = _base_state(branch_id=None)

        with patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter):
            result = branch_executor(state)

        assert "default" in result["branch_results"]


# ---------------------------------------------------------------------------
# merge_node
# ---------------------------------------------------------------------------

class TestMergeNode:
    def test_merge_collapses_branch_results_to_upstream_context(self):
        from lena.runtime.nodes.parallel import merge_node

        state = _base_state(
            branch_results={
                "branch-1": {"output": "backend done", "model": "gpt-5.5"},
                "branch-2": {"output": "tests written", "model": "gpt-5.5"},
            }
        )

        result = merge_node(state)

        assert "upstream_context" in result
        assert "branch-1" in result["upstream_context"]
        assert "backend done" in result["upstream_context"]
        assert "branch-2" in result["upstream_context"]
        assert "tests written" in result["upstream_context"]

    def test_merge_sets_needs_feedback_false(self):
        from lena.runtime.nodes.parallel import merge_node

        state = _base_state(
            branch_results={"b1": {"output": "x", "model": "m"}},
            needs_feedback=True,
        )

        result = merge_node(state)

        assert result["needs_feedback"] is False

    def test_merge_empty_branch_results_returns_existing_context(self):
        from lena.runtime.nodes.parallel import merge_node

        state = _base_state(
            branch_results={},
            upstream_context="existing context",
        )

        result = merge_node(state)

        assert result["upstream_context"] == "existing context"

    def test_merge_includes_branch_results_header(self):
        from lena.runtime.nodes.parallel import merge_node

        state = _base_state(
            branch_results={"b1": {"output": "result", "model": "m"}},
        )

        result = merge_node(state)

        assert "## Branch Results" in result["upstream_context"]


# ---------------------------------------------------------------------------
# End-to-end: router_node → fan_out → branch_executor → merge_node
# Verifies the full orchestrate path is reachable and branch_results populated.
# ---------------------------------------------------------------------------

class TestOrchestrateEndToEnd:
    """Integration test: routing="orchestrate" flows through fan_out to branch_executor
    and produces populated branch_results after merge_node."""

    def test_router_node_produces_parallel_tasks_for_orchestrate(self):
        """router_node emits parallel_tasks when scorer returns routing=orchestrate + domains."""
        import json
        from unittest.mock import patch, MagicMock
        from lena.runtime.nodes.router_node import router_node

        scorer_output = json.dumps({
            "routing": "orchestrate",
            "confidence": 85,
            "action": "execute",
            "suggested_role": None,
            "domains": ["backend", "testing"],
        })

        mock_run = MagicMock()
        mock_run.stdout = scorer_output
        mock_run.returncode = 0
        mock_run.stderr = ""

        from pathlib import Path

        mock_config = MagicMock()
        mock_config.routing.scorer_path = Path("/fake/routing_score.py")
        mock_config.routing.threshold = 70

        state = _base_state(task="build API with tests for user service")

        with (
            patch("subprocess.run", return_value=mock_run),
            patch("lena.runtime.nodes.router_node.load_config", return_value=mock_config),
        ):
            result = router_node(state)

        assert result["routing_result"]["routing"] == "orchestrate"
        assert len(result["parallel_tasks"]) == 2
        domains_emitted = [t["domain"] for t in result["parallel_tasks"]]
        assert "backend" in domains_emitted
        assert "testing" in domains_emitted
        for t in result["parallel_tasks"]:
            assert t["task"] == "build API with tests for user service"
            assert len(t["branch_id"]) > 0

    def test_full_orchestrate_path_populates_branch_results(self):
        """fan_out → branch_executor → merge_node produces non-empty branch_results."""
        from langgraph.types import Send
        from unittest.mock import patch, MagicMock
        from lena.runtime.nodes.parallel import fan_out_node, branch_executor, merge_node

        tasks = [
            {"task": "implement auth service", "domain": "backend", "branch_id": "backend-abc"},
            {"task": "write auth tests", "domain": "testing", "branch_id": "testing-def"},
        ]
        state = _base_state(
            task="implement auth service with tests",
            parallel_tasks=tasks,
            routing_result={"routing": "orchestrate", "action": "execute", "confidence": 85, "role": None},
        )

        # Step 1: fan_out produces Send objects for both branches
        sends = fan_out_node(state)
        assert len(sends) == 2
        assert all(isinstance(s, Send) for s in sends)
        assert all(s.node == "branch_executor" for s in sends)

        # Step 2: each branch executes and writes to branch_results
        mock_adapter = MagicMock()
        mock_adapter.complete.side_effect = ["auth service implemented", "auth tests written"]

        all_branch_results: dict = {}
        with patch("lena.runtime.nodes.parallel.get_adapter", return_value=mock_adapter):
            for send_obj in sends:
                branch_state = {**state, **send_obj.arg}
                branch_out = branch_executor(branch_state)
                all_branch_results.update(branch_out["branch_results"])

        assert "backend-abc" in all_branch_results
        assert "testing-def" in all_branch_results
        assert all_branch_results["backend-abc"]["output"] == "auth service implemented"
        assert all_branch_results["testing-def"]["output"] == "auth tests written"

        # Step 3: merge_node collapses branch_results to upstream_context
        merged_state = {**state, "branch_results": all_branch_results}
        merge_out = merge_node(merged_state)

        assert "upstream_context" in merge_out
        assert "backend-abc" in merge_out["upstream_context"]
        assert "testing-def" in merge_out["upstream_context"]
        assert "auth service implemented" in merge_out["upstream_context"]
        assert "auth tests written" in merge_out["upstream_context"]
        assert merge_out["needs_feedback"] is False

    def test_orchestrate_no_domains_produces_empty_parallel_tasks(self):
        """When scorer returns routing=orchestrate but no domains, parallel_tasks is empty."""
        import json
        from unittest.mock import patch, MagicMock
        from lena.runtime.nodes.router_node import router_node

        scorer_output = json.dumps({
            "routing": "orchestrate",
            "confidence": 60,
            "action": "clarify_or_orchestrate",
            "suggested_role": None,
            "domains": [],
        })

        mock_run = MagicMock()
        mock_run.stdout = scorer_output
        mock_run.returncode = 0
        mock_run.stderr = ""

        from pathlib import Path

        mock_config = MagicMock()
        mock_config.routing.scorer_path = Path("/fake/routing_score.py")
        mock_config.routing.threshold = 70

        state = _base_state(task="do something unclear")

        with (
            patch("subprocess.run", return_value=mock_run),
            patch("lena.runtime.nodes.router_node.load_config", return_value=mock_config),
        ):
            result = router_node(state)

        assert result["routing_result"]["routing"] == "orchestrate"
        assert result["parallel_tasks"] == []
