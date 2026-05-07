from __future__ import annotations

import atexit
import logging

from ...config import load_config
from ...embeddings import EmbeddingError, OllamaEmbedder
from ...memory.vector_adapter import VectorMemoryAdapter
from ..state import AgentState

_log = logging.getLogger(__name__)

# Module-level singleton — lazy init on first node invocation.
_vector_adapter: VectorMemoryAdapter | None = None


def _get_vector_adapter() -> VectorMemoryAdapter | None:
    """Lazy-init the VectorMemoryAdapter singleton.

    Returns None if team_moat is disabled or if Ollama/DB is unreachable.
    """
    global _vector_adapter
    if _vector_adapter is not None:
        return _vector_adapter

    try:
        from psycopg_pool import ConnectionPool

        from ...db.connection import get_pool

        config = load_config()
        if not config.team_moat.enabled:
            return None

        embedder = OllamaEmbedder(
            base_url=config.embeddings.base_url,
            model=config.embeddings.model,
        )
        pool: ConnectionPool = get_pool(min_size=1, max_size=5)
        pool.open()
        atexit.register(pool.close)
        _vector_adapter = VectorMemoryAdapter(
            embedder=embedder,
            pool=pool,
            team_id=config.team_moat.team_id,
        )
    except Exception as exc:
        _log.warning("VectorMemoryAdapter init failed (%s) — vector recall disabled", exc)
        return None

    return _vector_adapter


def vector_recall_node(state: AgentState) -> dict:
    """Recall team-moat memories relevant to the current task."""
    config = load_config()
    top_k = config.team_moat.top_k

    adapter = _get_vector_adapter()
    if adapter is None:
        return {"vector_memories": []}

    try:
        results = adapter.recall(state["task"], top_k=top_k)
    except (EmbeddingError, Exception) as exc:
        _log.warning("vector_recall_node failed (%s) — returning empty", exc)
        results = []

    return {"vector_memories": results}
