"""Tests for VectorMemoryAdapter — mocked psycopg pool + OllamaEmbedder."""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_embedder(vector: list[float] | None = None) -> MagicMock:
    embedder = MagicMock()
    embedder.embed.return_value = vector or [0.1] * 768
    return embedder


def _make_pool(cursor_rows: list | None = None, existing_row=None) -> MagicMock:
    """Build a mock psycopg ConnectionPool with context manager support."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = cursor_rows or []
    mock_cursor.fetchone.return_value = existing_row

    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    mock_pool = MagicMock()
    mock_pool.connection.return_value.__enter__ = lambda s: mock_conn
    mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)

    return mock_pool, mock_cursor, mock_conn


def _make_adapter(embedder=None, pool=None, team_id: str = "test-team"):
    from lena.memory.vector_adapter import VectorMemoryAdapter

    if embedder is None:
        embedder = _make_embedder()
    if pool is None:
        pool, _, _ = _make_pool()
    return VectorMemoryAdapter(embedder=embedder, pool=pool, team_id=team_id)


# ---------------------------------------------------------------------------
# OllamaEmbedder tests
# ---------------------------------------------------------------------------

class TestOllamaEmbedder:
    def test_embed_returns_vector_from_response(self):
        from lena.embeddings import OllamaEmbedder

        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
        mock_response.raise_for_status = MagicMock()

        with patch("lena.embeddings.requests.post", return_value=mock_response) as mock_post:
            embedder = OllamaEmbedder(base_url="http://localhost:11434", model="nomic-embed-text")
            result = embedder.embed("hello world")

        assert result == [0.1, 0.2, 0.3]
        mock_post.assert_called_once_with(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": "hello world"},
            timeout=30,
        )

    def test_embed_raises_embedding_error_on_request_failure(self):
        import requests as req_lib
        from lena.embeddings import OllamaEmbedder, EmbeddingError

        with patch("lena.embeddings.requests.post", side_effect=req_lib.ConnectionError("refused")):
            embedder = OllamaEmbedder()
            with pytest.raises(EmbeddingError, match="refused"):
                embedder.embed("hello")

    def test_embed_raises_embedding_error_on_bad_response_shape(self):
        from lena.embeddings import OllamaEmbedder, EmbeddingError

        mock_response = MagicMock()
        mock_response.json.return_value = {"error": "model not found"}
        mock_response.raise_for_status = MagicMock()

        with patch("lena.embeddings.requests.post", return_value=mock_response):
            embedder = OllamaEmbedder()
            with pytest.raises(EmbeddingError):
                embedder.embed("hello")

    def test_embed_batch_calls_embed_sequentially(self):
        from lena.embeddings import OllamaEmbedder

        embedder = OllamaEmbedder()
        embedder.embed = MagicMock(return_value=[0.5] * 768)

        results = embedder.embed_batch(["text1", "text2", "text3"])

        assert len(results) == 3
        assert embedder.embed.call_count == 3
        embedder.embed.assert_any_call("text1")
        embedder.embed.assert_any_call("text2")
        embedder.embed.assert_any_call("text3")

    def test_embed_strips_trailing_slash_from_base_url(self):
        from lena.embeddings import OllamaEmbedder

        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1]}
        mock_response.raise_for_status = MagicMock()

        with patch("lena.embeddings.requests.post", return_value=mock_response) as mock_post:
            embedder = OllamaEmbedder(base_url="http://localhost:11434/")
            embedder.embed("test")

        url_used = mock_post.call_args[0][0]
        assert "//" not in url_used.replace("http://", "")


# ---------------------------------------------------------------------------
# VectorMemoryAdapter — recall
# ---------------------------------------------------------------------------

class TestVectorMemoryAdapterRecall:
    def test_recall_returns_list_of_dicts(self):
        import uuid
        fake_id = str(uuid.uuid4())
        rows = [(fake_id, "some content", "task_resolution", "backend", {"hash": "abc"}, 0.92)]

        pool, cursor, _ = _make_pool(cursor_rows=rows)
        adapter = _make_adapter(pool=pool)

        results = adapter.recall("find relevant task")

        assert len(results) == 1
        assert results[0]["content"] == "some content"
        assert results[0]["type"] == "task_resolution"
        assert results[0]["domain"] == "backend"
        assert results[0]["similarity"] == pytest.approx(0.92)

    def test_recall_with_type_filter_passes_type_to_query(self):
        pool, cursor, _ = _make_pool(cursor_rows=[])
        adapter = _make_adapter(pool=pool)

        adapter.recall("query", type_filter="adr")

        executed_sql = cursor.execute.call_args[0][0]
        # type filter branch uses 5 params; check AND type = is in SQL
        assert "AND type" in executed_sql

    def test_recall_without_type_filter_omits_type_clause(self):
        pool, cursor, _ = _make_pool(cursor_rows=[])
        adapter = _make_adapter(pool=pool)

        adapter.recall("query")

        executed_sql = cursor.execute.call_args[0][0]
        assert "AND type" not in executed_sql

    def test_recall_empty_result_returns_empty_list(self):
        pool, _, _ = _make_pool(cursor_rows=[])
        adapter = _make_adapter(pool=pool)

        results = adapter.recall("nothing here")
        assert results == []

    def test_recall_embeds_query_before_sql(self):
        embedder = _make_embedder([0.1] * 768)
        pool, _, _ = _make_pool(cursor_rows=[])
        adapter = _make_adapter(embedder=embedder, pool=pool)

        adapter.recall("test query")

        embedder.embed.assert_called_once_with("test query")


# ---------------------------------------------------------------------------
# VectorMemoryAdapter — upsert + dedup
# ---------------------------------------------------------------------------

class TestVectorMemoryAdapterUpsert:
    def test_upsert_inserts_new_content(self):
        """Single INSERT with ON CONFLICT DO NOTHING — one execute call, returns id."""
        inserted_id = "abc-123"

        pool, cursor, conn = _make_pool()
        cursor.fetchone.return_value = (inserted_id,)

        adapter = _make_adapter(pool=pool)
        result = adapter.upsert("new content", "task_resolution", "backend")

        assert result == inserted_id
        # One execute call: INSERT ... ON CONFLICT DO NOTHING RETURNING id
        assert cursor.execute.call_count == 1
        insert_sql = cursor.execute.call_args[0][0]
        assert "INSERT INTO lena_team_memory" in insert_sql
        assert "ON CONFLICT" in insert_sql

    def test_upsert_returns_empty_string_on_conflict(self):
        """When ON CONFLICT fires, RETURNING returns no rows — upsert returns ''."""
        pool, cursor, conn = _make_pool()
        cursor.fetchone.return_value = None  # ON CONFLICT DO NOTHING → no RETURNING row

        adapter = _make_adapter(pool=pool)
        result = adapter.upsert("duplicate content", "task_resolution")

        assert result == ""
        # Still only one execute: INSERT (constraint handles dedup)
        assert cursor.execute.call_count == 1

    def test_upsert_embeds_content_before_insert(self):
        embedder = _make_embedder([0.5] * 768)
        pool, cursor, conn = _make_pool()
        cursor.fetchone.return_value = ("new-id",)

        adapter = _make_adapter(embedder=embedder, pool=pool)
        adapter.upsert("my content", "adr")

        embedder.embed.assert_called_once_with("my content")

    def test_exists_by_hash_returns_true_when_row_found(self):
        """exists_by_hash returns True when SELECT finds a matching row."""
        pool, cursor, conn = _make_pool()
        cursor.fetchone.return_value = ("some-id",)

        adapter = _make_adapter(pool=pool)
        assert adapter.exists_by_hash("abc123") is True

    def test_exists_by_hash_returns_false_when_no_row(self):
        """exists_by_hash returns False when SELECT finds nothing."""
        pool, cursor, conn = _make_pool()
        cursor.fetchone.return_value = None

        adapter = _make_adapter(pool=pool)
        assert adapter.exists_by_hash("abc123") is False

    def test_content_hash_is_16_chars(self):
        from lena.memory.vector_adapter import VectorMemoryAdapter
        adapter = VectorMemoryAdapter.__new__(VectorMemoryAdapter)

        h = adapter._content_hash("hello world")
        assert len(h) == 16
        assert h.isalnum()  # hex chars

    def test_content_hash_is_deterministic(self):
        from lena.memory.vector_adapter import VectorMemoryAdapter
        adapter = VectorMemoryAdapter.__new__(VectorMemoryAdapter)

        h1 = adapter._content_hash("same text")
        h2 = adapter._content_hash("same text")
        assert h1 == h2

    def test_content_hash_differs_for_different_content(self):
        from lena.memory.vector_adapter import VectorMemoryAdapter
        adapter = VectorMemoryAdapter.__new__(VectorMemoryAdapter)

        h1 = adapter._content_hash("text A")
        h2 = adapter._content_hash("text B")
        assert h1 != h2


# ---------------------------------------------------------------------------
# VectorMemoryAdapter — graceful Ollama failure
# ---------------------------------------------------------------------------

class TestVectorMemoryAdapterGracefulFailure:
    def test_recall_propagates_embedding_error(self):
        """EmbeddingError from Ollama bubbles up through recall (caller handles gracefully)."""
        from lena.embeddings import EmbeddingError

        embedder = _make_embedder()
        embedder.embed.side_effect = EmbeddingError("Ollama unreachable")

        pool, _, _ = _make_pool()
        adapter = _make_adapter(embedder=embedder, pool=pool)

        with pytest.raises(EmbeddingError):
            adapter.recall("query")

    def test_vector_recall_node_returns_empty_on_embedding_error(self):
        """vector_recall_node catches EmbeddingError and returns empty list."""
        from lena.embeddings import EmbeddingError
        from lena.runtime.nodes.vector_recall import vector_recall_node

        mock_adapter = MagicMock()
        mock_adapter.recall.side_effect = EmbeddingError("Ollama unreachable")

        mock_cfg = MagicMock()
        mock_cfg.team_moat.top_k = 5

        state = {
            "task": "test task",
            "vector_memories": [],
        }

        with (
            patch("lena.runtime.nodes.vector_recall._get_vector_adapter", return_value=mock_adapter),
            patch("lena.runtime.nodes.vector_recall.load_config", return_value=mock_cfg),
        ):
            result = vector_recall_node(state)

        assert result == {"vector_memories": []}

    def test_vector_recall_node_returns_empty_when_adapter_is_none(self):
        """When _get_vector_adapter returns None (team_moat disabled), return empty list."""
        from lena.runtime.nodes.vector_recall import vector_recall_node

        mock_cfg = MagicMock()
        mock_cfg.team_moat.top_k = 5

        state = {"task": "test task", "vector_memories": []}

        with (
            patch("lena.runtime.nodes.vector_recall._get_vector_adapter", return_value=None),
            patch("lena.runtime.nodes.vector_recall.load_config", return_value=mock_cfg),
        ):
            result = vector_recall_node(state)

        assert result == {"vector_memories": []}
