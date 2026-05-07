"""Tests for memory adapters — mock mem0 + zep backends."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestMem0Adapter:
    def test_remember_calls_mem_add(self):
        mock_mem = MagicMock()
        with patch("lena.memory.mem0_adapter.Mem0Adapter.__init__", return_value=None):
            from lena.memory.mem0_adapter import Mem0Adapter
            adapter = Mem0Adapter.__new__(Mem0Adapter)
            adapter._mem = mock_mem

        adapter.remember("my_key", "my_value", "session-1")
        mock_mem.add.assert_called_once_with(
            "my_value",
            user_id="session-1",
            metadata={"key": "my_key"},
        )

    def test_recall_returns_first_result(self):
        mock_mem = MagicMock()
        mock_mem.search.return_value = [{"memory": "stored_value"}]

        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = mock_mem

        result = adapter.recall("my_key", "session-1")
        assert result == "stored_value"

    def test_recall_returns_none_when_no_results(self):
        mock_mem = MagicMock()
        mock_mem.search.return_value = []

        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = mock_mem

        result = adapter.recall("my_key", "session-1")
        assert result is None

    def test_search_returns_list(self):
        mock_mem = MagicMock()
        mock_mem.search.return_value = [{"memory": "fact1"}, {"memory": "fact2"}]

        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = mock_mem

        results = adapter.search("query", "session-1", k=5)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_remember_noop_when_mem_none(self):
        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = None
        # Should not raise
        adapter.remember("k", "v", "s")

    def test_recall_returns_none_when_mem_none(self):
        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = None
        assert adapter.recall("k", "s") is None

    def test_search_returns_empty_when_mem_none(self):
        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = None
        assert adapter.search("q", "s") == []

    def test_consolidate_is_noop(self):
        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = MagicMock()
        # Should not raise and should not call any mem method
        adapter.consolidate("session-1")
        adapter._mem.assert_not_called()

    def test_protocol_conformance(self):
        from lena.memory.base import MemoryBackend
        from lena.memory.mem0_adapter import Mem0Adapter
        adapter = Mem0Adapter.__new__(Mem0Adapter)
        adapter._mem = None
        assert isinstance(adapter, MemoryBackend)


class TestZepAdapter:
    def _make_adapter(self, client=None, client_type="zep_python"):
        from lena.memory.zep_adapter import ZepAdapter
        adapter = ZepAdapter.__new__(ZepAdapter)
        adapter._base_url = "http://localhost:8000"
        adapter._api_key = ""
        adapter._client = client
        adapter._client_type = client_type
        return adapter

    def test_add_message_noop_when_no_client(self):
        adapter = self._make_adapter(client=None, client_type=None)
        # Should not raise
        adapter.add_message("sess", "user", "hello")

    def test_search_facts_empty_when_no_client(self):
        adapter = self._make_adapter(client=None, client_type=None)
        result = adapter.search_facts("sess", "query")
        assert result == []

    def test_get_session_summary_none_when_no_client(self):
        adapter = self._make_adapter(client=None, client_type=None)
        result = adapter.get_session_summary("sess")
        assert result is None

    def test_search_facts_exception_returns_empty(self):
        mock_client = MagicMock()
        mock_client.memory.search.side_effect = RuntimeError("connection refused")
        adapter = self._make_adapter(client=mock_client, client_type="zep_python")
        result = adapter.search_facts("sess", "query")
        assert result == []

    def test_add_message_exception_does_not_crash(self):
        mock_client = MagicMock()
        mock_client.memory.add.side_effect = RuntimeError("network error")
        adapter = self._make_adapter(client=mock_client, client_type="zep_cloud")
        # Should not raise
        adapter.add_message("sess", "user", "hello")
