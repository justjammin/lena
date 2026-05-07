from __future__ import annotations

import json
import logging
import subprocess
import sys

from ..state import AgentState

_log = logging.getLogger(__name__)


def bd_register(state: AgentState) -> dict:
    """Create a Beads issue for orchestrated tasks. Safe to skip if bd unavailable."""
    task = state["task"]
    title = task[:60]

    try:
        result = subprocess.run(
            [
                "bd", "create",
                f"--title={title}",
                f"--description={task}",
                "--type=task",
                "--priority=2",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            bd_id: str | None = str(data.get("id") or data.get("bd_id") or "")
            if not bd_id:
                bd_id = None
            _log.debug("bd_register: created issue %s", bd_id)
        else:
            _log.warning("bd create failed (rc=%d): %s", result.returncode, result.stderr.strip())
            bd_id = None
    except (FileNotFoundError, OSError):
        _log.warning("bd CLI not found — skipping issue registration")
        bd_id = None
    except subprocess.TimeoutExpired:
        _log.warning("bd create timed out")
        bd_id = None
    except json.JSONDecodeError as exc:
        _log.warning("bd create output not JSON: %s", exc)
        bd_id = None

    return {"bd_id": bd_id, "current_node": "bd_register"}
