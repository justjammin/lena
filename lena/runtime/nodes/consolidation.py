from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from ..state import AgentState

_log = logging.getLogger(__name__)

# Repo root derived from this file's location:
# consolidation.py → nodes/ → runtime/ → lena/ → repo root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Cache of ADR file contents: populated once then frozen.
_adr_cache: list[dict] | None = None
_adr_cache_lock = threading.Lock()


def _load_adr_items(decisions_dir: Path) -> list[dict]:
    """Scan docs/decisions/ once and return items ready for embedding."""
    global _adr_cache
    with _adr_cache_lock:
        if _adr_cache is not None:
            return _adr_cache

        items: list[dict] = []
        if decisions_dir.is_dir():
            for adr_path in sorted(decisions_dir.glob("*.md")):
                try:
                    content = adr_path.read_text(encoding="utf-8")
                    items.append(
                        {
                            "content": content,
                            "type": "adr",
                            "domain": "",
                            "metadata": {"source": str(adr_path)},
                        }
                    )
                except Exception as exc:
                    _log.warning("Failed to read ADR %s: %s", adr_path, exc)

        _adr_cache = items
        return _adr_cache


def _get_vector_adapter():
    """Return VectorMemoryAdapter singleton or None if unavailable."""
    try:
        from ..nodes.vector_recall import _get_vector_adapter as _va
        return _va()
    except Exception:
        return None


def _consolidation_worker(items: list[dict], adapter: Any) -> None:
    """Background thread: embed + upsert each item. Best-effort — never crashes session.

    Performs a cheap hash check before calling the embedder so repeat content
    does not trigger unnecessary Ollama round-trips.
    """
    for item in items:
        try:
            content = item["content"]
            content_hash = adapter._content_hash(content)
            if adapter.exists_by_hash(content_hash):
                _log.debug("consolidation_worker: skipping already-stored hash %s", content_hash)
                continue
            adapter.upsert(
                content,
                item["type"],
                item.get("domain", ""),
                item.get("metadata", {}),
            )
        except Exception as exc:
            _log.debug("consolidation_worker upsert skipped: %s", exc)


def consolidation_node(state: AgentState) -> dict:
    """Collect embeddable artefacts and spawn a daemon thread to persist them.

    Non-blocking — returns immediately so the graph can proceed to END.
    """
    adapter = _get_vector_adapter()
    if adapter is None:
        return {}

    items: list[dict] = []

    # Task resolution — only when a bd issue was registered.
    upstream = state.get("upstream_context")
    if upstream and state.get("bd_id"):
        items.append(
            {
                "content": upstream,
                "type": "task_resolution",
                "domain": state.get("hat") or "",
                "metadata": {"bd_id": state.get("bd_id")},
            }
        )

    # Routing override — persist for future routing calibration.
    routing_result = state.get("routing_result") or {}
    if routing_result.get("routing") == "mcp":
        task = state.get("task") or ""
        if task:
            items.append(
                {
                    "content": task,
                    "type": "routing_override",
                    "domain": "",
                    "metadata": {"routing": "mcp"},
                }
            )

    # ADRs — scan once and cache. Use project-root-anchored path so this works
    # regardless of the process cwd (e.g. when invoked from a hook or test runner).
    decisions_dir = _PROJECT_ROOT / "docs" / "decisions"
    adr_items = _load_adr_items(decisions_dir)
    items.extend(adr_items)

    if not items:
        return {}

    # Capture adapter reference before thread start (avoids GC race).
    captured_adapter = adapter
    t = threading.Thread(
        target=_consolidation_worker,
        args=(items, captured_adapter),
        daemon=True,
    )
    t.start()

    return {}
