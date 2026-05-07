from __future__ import annotations

import json
import logging

_log = logging.getLogger(__name__)


class ZepAdapter:
    """Thin wrapper around zep-python SDK for session memory + fact search.

    Falls back gracefully if Zep is unreachable or the package is missing.
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._client = None
        self._client_type: str | None = None
        self._init_client()

    def _init_client(self) -> None:
        # Try zep_python (self-hosted) first — matches our config (localhost:8000)
        try:
            from zep_python import ZepClient  # type: ignore[import-untyped]
            self._client = ZepClient(base_url=self._base_url, api_key=self._api_key or None)
            self._client_type = "zep_python"
            return
        except ImportError:
            pass
        except Exception as exc:
            _log.warning("zep_python init failed: %s", exc)
            return

        # Fallback: zep_cloud SDK
        try:
            from zep_cloud.client import Zep  # type: ignore[import-untyped]
            self._client = Zep(api_key=self._api_key)
            self._client_type = "zep_cloud"
        except ImportError:
            _log.warning("Neither zep_python nor zep_cloud found — Zep disabled")
        except Exception as exc:
            _log.warning("zep_cloud init failed: %s", exc)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def add_message(self, session_id: str, role: str, content: str) -> None:
        if self._client is None:
            return
        try:
            if self._client_type == "zep_python":
                from zep_python.memory import Message as ZepMessage  # type: ignore[import-untyped]
                from zep_python.memory import Memory as ZepMemory  # type: ignore[import-untyped]
                msg = ZepMessage(role=role, content=content, role_type=role)
                mem = ZepMemory(messages=[msg])
                self._client.memory.add(session_id, mem)
            elif self._client_type == "zep_cloud":
                self._client.memory.add(
                    session_id,
                    messages=[{"role": role, "content": content}],
                )
        except Exception as exc:
            _log.warning("Zep.add_message failed (session=%s): %s", session_id, exc)

    def search_facts(self, session_id: str, query: str, k: int = 5) -> list[str]:
        if self._client is None:
            return []
        try:
            if self._client_type == "zep_python":
                results = self._client.memory.search(
                    session_id, query=query, limit=k, search_type="summary"
                )
                return [r.summary.content for r in results if r.summary and r.summary.content]
            elif self._client_type == "zep_cloud":
                results = self._client.memory.search(
                    session_id, text=query, limit=k
                )
                return [r.fact for r in results if hasattr(r, "fact") and r.fact]
        except Exception as exc:
            _log.warning("Zep.search_facts failed (session=%s): %s", session_id, exc)
        return []

    def get_session_summary(self, session_id: str) -> str | None:
        if self._client is None:
            return None
        try:
            if self._client_type == "zep_python":
                mem = self._client.memory.get(session_id)
                if mem and mem.summary and mem.summary.content:
                    return mem.summary.content
            elif self._client_type == "zep_cloud":
                mem = self._client.memory.get(session_id)
                if mem and hasattr(mem, "summary") and mem.summary:
                    return mem.summary
        except Exception as exc:
            _log.warning("Zep.get_session_summary failed (session=%s): %s", session_id, exc)
        return None
