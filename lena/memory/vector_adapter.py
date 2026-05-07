from __future__ import annotations

import hashlib
import logging
from typing import Any

from psycopg_pool import ConnectionPool

from ..embeddings import OllamaEmbedder

_log = logging.getLogger(__name__)


class VectorMemoryAdapter:
    """Team-moat memory backend: pgvector + Ollama embeddings."""

    def __init__(
        self,
        embedder: OllamaEmbedder,
        pool: ConnectionPool,
        team_id: str,
    ) -> None:
        self._embedder = embedder
        self._pool = pool
        self._team_id = team_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        top_k: int = 5,
        type_filter: str | None = None,
    ) -> list[dict]:
        """Return top_k most similar memories to *query* for this team."""
        vector = self._embedder.embed(query)
        vector_str = self._vector_to_pg(vector)

        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                if type_filter is not None:
                    cur.execute(
                        """
                        SELECT id, content, type, domain, metadata,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM lena_team_memory
                        WHERE team_id = %s AND type = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (vector_str, self._team_id, type_filter, vector_str, top_k),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, content, type, domain, metadata,
                               1 - (embedding <=> %s::vector) AS similarity
                        FROM lena_team_memory
                        WHERE team_id = %s
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                        """,
                        (vector_str, self._team_id, vector_str, top_k),
                    )
                rows = cur.fetchall()

        results = []
        for row in rows:
            results.append(
                {
                    "id": str(row[0]),
                    "content": row[1],
                    "type": row[2],
                    "domain": row[3] or "",
                    "metadata": row[4] or {},
                    "similarity": float(row[5]),
                }
            )
        return results

    def exists_by_hash(self, content_hash: str) -> bool:
        """Return True if a row with this hash already exists for the team."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM lena_team_memory
                    WHERE team_id = %s AND metadata->>'hash' = %s
                    LIMIT 1
                    """,
                    (self._team_id, content_hash),
                )
                return cur.fetchone() is not None

    def upsert(
        self,
        content: str,
        type: str,
        domain: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Embed *content* and insert into lena_team_memory.

        Uses ON CONFLICT on the unique index (team_id, metadata->>'hash') so concurrent
        calls are safe — the constraint handles dedup atomically without a prior SELECT.
        Returns the id of the inserted (or silently skipped) row.
        """
        import json

        content_hash = self._content_hash(content)
        meta: dict[str, Any] = dict(metadata or {})
        meta["hash"] = content_hash

        vector = self._embedder.embed(content)
        vector_str = self._vector_to_pg(vector)

        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO lena_team_memory
                        (team_id, content, type, domain, embedding, metadata)
                    VALUES (%s, %s, %s, %s, %s::vector, %s)
                    ON CONFLICT (team_id, (metadata->>'hash')) DO NOTHING
                    RETURNING id
                    """,
                    (
                        self._team_id,
                        content,
                        type,
                        domain,
                        vector_str,
                        json.dumps(meta),
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                # ON CONFLICT DO NOTHING → RETURNING returns no rows when skipped.
                # Return empty string to signal "already existed" to callers that care.
                return str(row[0]) if row else ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @staticmethod
    def _vector_to_pg(vector: list[float]) -> str:
        """Format a float list as PostgreSQL vector literal string."""
        return "[" + ",".join(str(v) for v in vector) + "]"
