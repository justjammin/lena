from __future__ import annotations

import logging
from typing import Any

from ..config import load_config

_log = logging.getLogger(__name__)


class Mem0Adapter:
    """MemoryBackend implementation backed by mem0 + pgvector."""

    def __init__(self) -> None:
        config = load_config()
        mem0_cfg = config.memory.mem0
        # Build config dict — include embedder only when explicitly configured so
        # mem0 doesn't fall back to its own default (OpenAI 1536-dim).
        full_cfg: dict[str, Any] = {"vector_store": mem0_cfg.vector_store}
        if mem0_cfg.embedder:
            full_cfg["embedder"] = mem0_cfg.embedder
        try:
            from mem0 import Memory  # type: ignore[import-untyped]
            self._mem = Memory.from_config(full_cfg)
        except Exception as exc:
            _log.warning("mem0 init failed (%s) — using no-op backend", exc)
            self._mem = None

    # ------------------------------------------------------------------
    # MemoryBackend protocol
    # ------------------------------------------------------------------

    def remember(self, key: str, value: Any, session_id: str) -> None:
        if self._mem is None:
            return
        try:
            self._mem.add(
                str(value),
                user_id=session_id,
                metadata={"key": key},
            )
        except Exception as exc:
            _log.warning("mem0.remember failed: %s", exc)

    def recall(self, key: str, session_id: str) -> Any | None:
        if self._mem is None:
            return None
        try:
            results = self._mem.search(key, user_id=session_id, limit=1)
            if results:
                # mem0 returns list of dicts with "memory" key
                first = results[0]
                return first.get("memory") if isinstance(first, dict) else first
        except Exception as exc:
            _log.warning("mem0.recall failed: %s", exc)
        return None

    def search(self, query: str, session_id: str, k: int = 5) -> list[dict]:
        if self._mem is None:
            return []
        try:
            results = self._mem.search(query, user_id=session_id, limit=k)
            return results if isinstance(results, list) else []
        except Exception as exc:
            _log.warning("mem0.search failed: %s", exc)
            return []

    def consolidate(self, session_id: str) -> None:
        # mem0 auto-consolidates; nothing to do here
        pass
