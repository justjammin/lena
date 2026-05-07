from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lena.runtime.router import RouteResult, RouterNode


SCORER_PATH = Path("/fake/routing_score.py")


def _make_router(threshold: int = 70) -> RouterNode:
    return RouterNode(scorer_path=SCORER_PATH, threshold=threshold)


def _mock_run(stdout: str, returncode: int = 0):
    mock = MagicMock()
    mock.stdout = stdout
    mock.returncode = returncode
    mock.stderr = ""
    return mock


# ---------------------------------------------------------------------------
# routing="direct" when confidence >= threshold and scorer says direct
# ---------------------------------------------------------------------------

class TestRouterDirectPath:
    def test_high_confidence_direct_routing(self):
        payload = json.dumps({
            "routing": "direct",
            "confidence": 85,
            "action": "execute",
            "suggested_role": "backend-developer",
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router().route("fix the login bug in auth.py")

        assert result["routing"] == "direct"
        assert result["confidence"] == 85
        assert result["role"] == "backend-developer"
        assert result["action"] == "execute"

    def test_confidence_exactly_at_threshold_is_direct(self):
        payload = json.dumps({
            "routing": "direct",
            "confidence": 70,
            "action": "execute",
            "suggested_role": "debugger",
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router(threshold=70).route("fix bug")

        assert result["routing"] == "direct"

    def test_scorer_orchestrate_routing_becomes_orchestrate(self):
        """When scorer returns orchestrate, router emits orchestrate (not mcp)."""
        payload = json.dumps({
            "routing": "orchestrate",
            "confidence": 90,
            "action": "execute",
            "suggested_role": None,
            "domains": ["backend", "frontend"],
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router().route("build and deploy the entire platform")

        assert result["routing"] == "orchestrate"
        assert result["domains"] == ["backend", "frontend"]

    def test_low_confidence_orchestrate_still_becomes_orchestrate(self):
        """Orchestrate routing is not gated by confidence — the scorer decided."""
        payload = json.dumps({
            "routing": "orchestrate",
            "confidence": 40,
            "action": "clarify_or_orchestrate",
            "suggested_role": None,
            "domains": [],
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router().route("do many things")

        assert result["routing"] == "orchestrate"

    def test_domains_surfaced_in_route_result(self):
        """domains field from scorer is passed through to RouteResult."""
        payload = json.dumps({
            "routing": "direct",
            "confidence": 80,
            "action": "execute",
            "suggested_role": "backend-developer",
            "domains": ["backend"],
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router().route("fix auth bug in api.py")

        assert result["domains"] == ["backend"]


# ---------------------------------------------------------------------------
# routing="mcp" for low confidence
# ---------------------------------------------------------------------------

class TestRouterMcpFallback:
    def test_low_confidence_becomes_mcp(self):
        payload = json.dumps({
            "routing": "direct",
            "confidence": 40,
            "action": "clarify_or_orchestrate",
            "suggested_role": None,
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router().route("do something vague")

        assert result["routing"] == "mcp"
        assert result["confidence"] == 40

    def test_confidence_just_below_threshold_is_mcp(self):
        payload = json.dumps({
            "routing": "direct",
            "confidence": 69,
            "action": "execute_log",
            "suggested_role": "backend-developer",
        })
        with patch("subprocess.run", return_value=_mock_run(payload)):
            result = _make_router(threshold=70).route("some task")

        assert result["routing"] == "mcp"


# ---------------------------------------------------------------------------
# routing="mcp" on subprocess timeout
# ---------------------------------------------------------------------------

class TestRouterTimeoutFallback:
    def test_subprocess_timeout_returns_mcp(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="py", timeout=5)):
            result = _make_router().route("anything")

        assert result["routing"] == "mcp"
        assert result["confidence"] == 0

    def test_json_parse_failure_returns_mcp(self):
        with patch("subprocess.run", return_value=_mock_run("not valid json")):
            result = _make_router().route("anything")

        assert result["routing"] == "mcp"
        assert result["confidence"] == 0

    def test_file_not_found_returns_mcp(self):
        with patch("subprocess.run", side_effect=FileNotFoundError("python not found")):
            result = _make_router().route("anything")

        assert result["routing"] == "mcp"
