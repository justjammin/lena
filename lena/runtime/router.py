from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal

from typing_extensions import TypedDict

_log = logging.getLogger(__name__)


class RouteResult(TypedDict, total=False):
    action: str
    confidence: int
    role: str | None
    routing: Literal["direct", "orchestrate", "mcp"]
    domains: list[str]


_MCP_FALLBACK: RouteResult = {
    "action": "mcp_fallback",
    "confidence": 0,
    "role": None,
    "routing": "mcp",
    "domains": [],
}


class RouterNode:
    def __init__(self, scorer_path: Path, threshold: int = 70) -> None:
        self._scorer_path = scorer_path
        self._threshold = threshold

    def route(self, task: str) -> RouteResult:
        try:
            new_pythonpath = str(self._scorer_path.parent.parent)
            existing = os.environ.get("PYTHONPATH", "")
            pythonpath = f"{new_pythonpath}:{existing}" if existing else new_pythonpath
            env = {**os.environ, "PYTHONPATH": pythonpath}
            result = subprocess.run(
                [sys.executable, str(self._scorer_path), "--task", task, "--json"],
                capture_output=True,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                env=env,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return dict(_MCP_FALLBACK)  # type: ignore[return-value]

        if result.returncode != 0:
            _log.warning(
                "routing scorer exited %d: %s",
                result.returncode,
                result.stderr.strip(),
            )
            return dict(_MCP_FALLBACK)  # type: ignore[return-value]

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return dict(_MCP_FALLBACK)  # type: ignore[return-value]

        confidence: int = int(data.get("confidence", 0))
        action: str = data.get("action", "execute")
        role: str | None = data.get("suggested_role")
        scorer_routing: str = data.get("routing", "orchestrate")
        domains: list[str] = data.get("domains") or []

        if confidence >= self._threshold and scorer_routing == "direct":
            routing: Literal["direct", "orchestrate", "mcp"] = "direct"
        elif scorer_routing == "orchestrate":
            routing = "orchestrate"
        else:
            routing = "mcp"

        return RouteResult(
            action=action,
            confidence=confidence,
            role=role,
            routing=routing,
            domains=domains,
        )
