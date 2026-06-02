from __future__ import annotations

"""Tests for the executor act/observe loop (lena-9ho).

These tests verify:
- The bounded tool loop runs and dispatches real tool calls.
- The loop stops at MAX_TOOL_ITERS on infinite-tool-call adapters.
- Text-only (no tool_calls) paths produce a single adapter call.
- AgentRegistry wiring injects persona text and passes tools= to the adapter.
- Unknown hat falls back to old behavior (tools=None, no persona).
- branch_executor loop produces correct branch_results.
"""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import lena.runtime.tools as _tools_mod
from lena.adapters.base import Completion, ToolCall
from lena.runtime.nodes.executor import MAX_TOOL_ITERS, executor
from lena.runtime.nodes.parallel import branch_executor


# ---------------------------------------------------------------------------
# Autouse fixture: pin WORKSPACE_ROOT to tmp_path so file-IO tests that write
# to pytest's temp directory are inside the jail.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_tools_mod, "WORKSPACE_ROOT", tmp_path.resolve())


# ---------------------------------------------------------------------------
# FakeAdapter helper
# ---------------------------------------------------------------------------


class FakeAdapter:
    """Script-driven adapter that returns pre-configured Completions."""

    def __init__(self, completions: list[Completion]) -> None:
        self._completions = list(completions)
        self._calls: list[dict[str, Any]] = []
        self.name = "fake"
        self.last_usage: dict[str, int] = {}

    def complete(
        self,
        messages: list[dict],
        cache_breakpoints=None,
        model: str = "",
        tools=None,
        **kwargs,
    ) -> Completion:
        self._calls.append({"messages": list(messages), "tools": tools})
        if self._completions:
            return self._completions.pop(0)
        return Completion(content="[fake exhausted]", tool_calls=[])

    @property
    def call_count(self) -> int:
        return len(self._calls)


def _base_state(messages=None, hat="", model="claude-sonnet-4-6") -> dict:
    return {
        "hat": hat,
        "messages": messages or [{"role": "user", "content": "do the task"}],
        "task": "test task",
        "routing_result": None,
        "memory": {},
        "cache_breakpoints": [],
        "current_node": "",
        "error": None,
        "iteration": 0,
        "bd_id": None,
        "needs_feedback": False,
        "feedback_history": [],
        "upstream_context": None,
        "mem0_session_id": "",
        "zep_session_id": "",
        "model": model,
        "branch_id": None,
        "branch_results": {},
        "vector_memories": [],
        "parallel_tasks": [],
    }


# ---------------------------------------------------------------------------
# Text-only (no tool calls) — single adapter call
# ---------------------------------------------------------------------------


class TestExecutorTextOnly:
    def test_single_call_no_tools(self, monkeypatch):
        fake = FakeAdapter([Completion(content="final answer", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        state = _base_state()
        result = executor(state)

        assert result["upstream_context"] == "final answer"
        assert fake.call_count == 1
        assert result["messages"][0]["role"] == "assistant"
        assert result["messages"][0]["content"] == "final answer"
        assert result["current_node"] == "executor"

    def test_returns_delta_only(self, monkeypatch):
        """messages returned should be only the delta, not the full history."""
        fake = FakeAdapter([Completion(content="hello", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        state = _base_state(messages=[
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hi"},
        ])
        result = executor(state)
        # Delta = only the assistant turn produced this node.
        roles = [m["role"] for m in result["messages"]]
        assert roles == ["assistant"]


# ---------------------------------------------------------------------------
# Tool loop — Read round-trip
# ---------------------------------------------------------------------------


class TestExecutorToolLoop:
    def test_read_tool_loop(self, monkeypatch, tmp_path):
        """First call returns a Read tool call; second call returns final text."""
        target_file = tmp_path / "greeting.txt"
        target_file.write_text("hello from file")

        fake = FakeAdapter([
            Completion(
                content="",
                tool_calls=[ToolCall(id="call_0", name="Read", arguments={"path": str(target_file)})],
            ),
            Completion(content="I read: hello from file", tool_calls=[]),
        ])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        state = _base_state()
        result = executor(state)

        assert result["upstream_context"] == "I read: hello from file"
        assert fake.call_count == 2

        # Delta must include: assistant(tool_calls), tool(result), assistant(final)
        delta = result["messages"]
        assert len(delta) == 3
        assert delta[0]["role"] == "assistant"
        assert "tool_calls" in delta[0]
        assert delta[1]["role"] == "tool"
        assert delta[1]["tool_call_id"] == "call_0"
        assert "hello from file" in delta[1]["content"]
        assert delta[2]["role"] == "assistant"
        assert delta[2]["content"] == "I read: hello from file"

    def test_tool_result_in_second_call_messages(self, monkeypatch, tmp_path):
        """The second adapter call must receive the tool result in messages."""
        target_file = tmp_path / "data.txt"
        target_file.write_text("some data")

        captured_calls: list[list[dict]] = []

        class CapturingAdapter(FakeAdapter):
            def complete(self, messages, **kwargs):
                captured_calls.append(list(messages))
                return super().complete(messages, **kwargs)

        fake = CapturingAdapter([
            Completion(
                content="",
                tool_calls=[ToolCall(id="c1", name="Read", arguments={"path": str(target_file)})],
            ),
            Completion(content="done", tool_calls=[]),
        ])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        executor(_base_state())

        # Second call messages must contain the tool result message.
        second_call_messages = captured_calls[1]
        tool_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_msgs) == 1
        assert "some data" in tool_msgs[0]["content"]


# ---------------------------------------------------------------------------
# Bounded loop — stops at MAX_TOOL_ITERS
# ---------------------------------------------------------------------------


class TestExecutorBoundedLoop:
    def test_stops_at_max_iterations(self, monkeypatch, tmp_path):
        """Adapter that always returns a tool call must stop after MAX_TOOL_ITERS."""
        f = tmp_path / "x.txt"
        f.write_text("x")

        # Create enough completions to exceed MAX_TOOL_ITERS if uncapped.
        completions = [
            Completion(
                content="",
                tool_calls=[ToolCall(id=f"c{i}", name="Read", arguments={"path": str(f)})],
            )
            for i in range(MAX_TOOL_ITERS + 5)
        ]
        fake = FakeAdapter(completions)
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        executor(_base_state())

        assert fake.call_count == MAX_TOOL_ITERS


# ---------------------------------------------------------------------------
# Registry wiring — persona + tools injected
# ---------------------------------------------------------------------------


def _write_manifest(tmp_path: Path) -> tuple[Path, Path]:
    """Write a minimal manifest and a persona .md file; return (manifest_path, persona_path)."""
    persona_dir = tmp_path / ".claude" / "agents"
    persona_dir.mkdir(parents=True)
    persona_file = persona_dir / "test-agent.md"
    persona_file.write_text("You are a test agent persona.")

    manifest = tmp_path / "agents.manifest.yaml"
    manifest.write_text(
        "version: 1\n"
        "agents:\n"
        "  backend:\n"
        "    - name: test-agent\n"
        "      path: .claude/agents/test-agent.md\n"
        "      tools: [Read, Bash]\n"
        "      model: gpt-4o\n"
    )
    return manifest, persona_file


class TestExecutorRegistryWiring:
    def _make_registry(self, manifest_path: Path):
        from lena.registry import AgentRegistry
        reg = AgentRegistry(manifest_path=manifest_path)
        reg.load()
        return reg

    def test_persona_injected_into_system_message(self, monkeypatch, tmp_path):
        manifest_path, _ = _write_manifest(tmp_path)
        registry = self._make_registry(manifest_path)

        fake = FakeAdapter([Completion(content="ok", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: registry)

        # Patch load_config so _inject_persona resolves persona relative to tmp_path.
        mock_config = MagicMock()
        mock_config.registry.manifest_path = manifest_path
        monkeypatch.setattr("lena.runtime.nodes.executor.load_config", lambda: mock_config)

        state = _base_state(hat="test-agent")
        executor(state)

        # System message must contain persona text.
        messages_sent = fake._calls[0]["messages"]
        system_msgs = [m for m in messages_sent if m.get("role") == "system"]
        assert system_msgs, "Expected a system message to be injected"
        system_content = system_msgs[0]["content"]
        assert "test-agent" in system_content
        assert "You are a test agent persona." in system_content

    def test_tools_schema_passed_to_adapter(self, monkeypatch, tmp_path):
        manifest_path, _ = _write_manifest(tmp_path)
        registry = self._make_registry(manifest_path)

        fake = FakeAdapter([Completion(content="ok", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: registry)

        mock_config = MagicMock()
        mock_config.registry.manifest_path = manifest_path
        monkeypatch.setattr("lena.runtime.nodes.executor.load_config", lambda: mock_config)

        state = _base_state(hat="test-agent")
        executor(state)

        tools_passed = fake._calls[0]["tools"]
        assert tools_passed is not None
        assert len(tools_passed) == 2  # Read + Bash
        tool_names = {t["function"]["name"] for t in tools_passed}
        assert tool_names == {"Read", "Bash"}

    def test_unknown_hat_falls_back_to_no_tools(self, monkeypatch, tmp_path):
        manifest_path, _ = _write_manifest(tmp_path)
        registry = self._make_registry(manifest_path)

        fake = FakeAdapter([Completion(content="ok", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: registry)

        state = _base_state(hat="nonexistent-agent")
        executor(state)

        # tools= should be None (no schema) for unknown hat.
        assert fake._calls[0]["tools"] is None

    def test_empty_hat_falls_back_to_no_tools(self, monkeypatch):
        fake = FakeAdapter([Completion(content="ok", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        state = _base_state(hat="")
        executor(state)

        assert fake._calls[0]["tools"] is None


# ---------------------------------------------------------------------------
# branch_executor loop
# ---------------------------------------------------------------------------


class TestBranchExecutorLoop:
    def test_text_only_branch(self, monkeypatch):
        fake = FakeAdapter([Completion(content="branch result", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.parallel.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        state = {**_base_state(), "branch_id": "test-branch", "domain": ""}
        result = branch_executor(state)

        assert result["branch_results"]["test-branch"]["output"] == "branch result"
        assert result["branch_results"]["test-branch"]["model"] == "claude-sonnet-4-6"

    def test_tool_loop_in_branch(self, monkeypatch, tmp_path):
        f = tmp_path / "branch_data.txt"
        f.write_text("branch content")

        fake = FakeAdapter([
            Completion(
                content="",
                tool_calls=[ToolCall(id="bc0", name="Read", arguments={"path": str(f)})],
            ),
            Completion(content="branch done", tool_calls=[]),
        ])
        monkeypatch.setattr("lena.runtime.nodes.parallel.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        state = {**_base_state(), "branch_id": "b1", "domain": ""}
        result = branch_executor(state)

        assert result["branch_results"]["b1"]["output"] == "branch done"
        assert fake.call_count == 2

    def test_branch_domain_wiring_injects_tools_and_persona(self, monkeypatch, tmp_path):
        """branch_executor receives domain from fan_out → registry lookup fires → tools injected."""
        manifest_path, _ = _write_manifest(tmp_path)

        from lena.registry import AgentRegistry
        registry = AgentRegistry(manifest_path=manifest_path)
        registry.load()

        fake = FakeAdapter([Completion(content="branch ok", tool_calls=[])])
        monkeypatch.setattr("lena.runtime.nodes.parallel.get_adapter", lambda model: fake)
        # parallel.py imports _get_registry directly, so patch at the parallel module namespace.
        monkeypatch.setattr("lena.runtime.nodes.parallel._get_registry", lambda: registry)

        mock_config = MagicMock()
        mock_config.registry.manifest_path = manifest_path
        monkeypatch.setattr("lena.runtime.nodes.executor.load_config", lambda: mock_config)
        monkeypatch.setattr("lena.runtime.nodes.parallel.load_config", lambda: mock_config, raising=False)

        # fan_out_node sets domain="backend"; manifest has test-agent in backend domain.
        state = {**_base_state(), "branch_id": "b-backend", "domain": "backend"}
        result = branch_executor(state)

        assert result["branch_results"]["b-backend"]["output"] == "branch ok"

        # tools= must be non-None and contain the schema from test-agent (Read, Bash per test manifest).
        tools_passed = fake._calls[0]["tools"]
        assert tools_passed is not None, "Expected tools= to be passed to branch adapter"
        tool_names = {t["function"]["name"] for t in tools_passed}
        assert tool_names == {"Read", "Bash"}

        # System message must contain persona text.
        messages_sent = fake._calls[0]["messages"]
        system_msgs = [m for m in messages_sent if m.get("role") == "system"]
        assert system_msgs, "Expected persona system message"
        assert "You are a test agent persona." in system_msgs[0]["content"]

    def test_branch_no_persona_mutation_between_parallel_branches(self, monkeypatch, tmp_path):
        """Two branches with different domains must not share/contaminate system message content."""
        manifest_path, _ = _write_manifest(tmp_path)

        from lena.registry import AgentRegistry
        registry = AgentRegistry(manifest_path=manifest_path)
        registry.load()

        # Track system messages seen by each branch.
        seen: dict[str, str] = {}

        class TrackingAdapter(FakeAdapter):
            def complete(self, messages, **kwargs):
                for m in messages:
                    if m.get("role") == "system":
                        # Store by branch (we'll key by call index since branch_id not in kwargs).
                        seen[str(len(seen))] = m.get("content", "")
                return super().complete(messages, **kwargs)

        fake1 = TrackingAdapter([Completion(content="b1 done", tool_calls=[])])
        fake2 = TrackingAdapter([Completion(content="b2 done", tool_calls=[])])

        mock_config = MagicMock()
        mock_config.registry.manifest_path = manifest_path
        monkeypatch.setattr("lena.runtime.nodes.executor.load_config", lambda: mock_config)
        # patch _get_registry at parallel's imported namespace.
        monkeypatch.setattr("lena.runtime.nodes.parallel._get_registry", lambda: registry)

        base = _base_state(messages=[
            {"role": "system", "content": "base system"},
            {"role": "user", "content": "task"},
        ])

        state1 = {**base, "branch_id": "b1", "domain": "backend"}
        state2 = {**base, "branch_id": "b2", "domain": "backend"}

        monkeypatch.setattr("lena.runtime.nodes.parallel.get_adapter", lambda model: fake1)
        branch_executor(state1)

        monkeypatch.setattr("lena.runtime.nodes.parallel.get_adapter", lambda model: fake2)
        branch_executor(state2)

        # Each branch saw its own system message — neither should have the persona injected twice.
        for key, content in seen.items():
            persona_count = content.count("## Persona:")
            assert persona_count == 1, f"Branch {key} saw persona {persona_count} times: {content!r}"


# ---------------------------------------------------------------------------
# Wire shape round-trip — iteration 2 messages have correct shape
# ---------------------------------------------------------------------------


class TestWireShapeRoundTrip:
    def test_assistant_tool_calls_stored_as_wire_shape(self, monkeypatch, tmp_path):
        """The assistant message stored in delta must use OpenAI wire shape (arguments as JSON string)."""
        f = tmp_path / "w.txt"
        f.write_text("wire test")

        fake = FakeAdapter([
            Completion(
                content="",
                tool_calls=[ToolCall(id="wc0", name="Read", arguments={"path": str(f)})],
            ),
            Completion(content="done", tool_calls=[]),
        ])
        monkeypatch.setattr("lena.runtime.nodes.executor.get_adapter", lambda model: fake)
        monkeypatch.setattr("lena.runtime.nodes.executor._get_registry", lambda: None)

        result = executor(_base_state())
        delta = result["messages"]

        # First delta message is assistant with tool_calls in wire format.
        assistant_msg = delta[0]
        assert "tool_calls" in assistant_msg
        tc = assistant_msg["tool_calls"][0]
        assert tc["type"] == "function"
        assert tc["id"] == "wc0"
        assert isinstance(tc["function"]["arguments"], str)  # must be JSON string
        parsed = json.loads(tc["function"]["arguments"])
        assert parsed["path"] == str(f)
