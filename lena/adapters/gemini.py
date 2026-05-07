from __future__ import annotations

import hashlib
import json
from typing import Any

from .base import Message

try:
    import google.genai as _genai
    from google.genai import types as _genai_types
    from google.genai import errors as _genai_errors
except ImportError as exc:  # pragma: no cover
    _genai = None  # type: ignore[assignment]
    _genai_types = None  # type: ignore[assignment]
    _genai_errors = None  # type: ignore[assignment]
    _import_error = exc
else:
    _import_error = None

# Sentinel used in except clauses so the no-deps import path still works.
_GeminiAPIError: type = _genai_errors.APIError if _genai_errors is not None else Exception  # type: ignore[union-attr]

_CACHE_TTL_SECONDS = 3600


class GeminiAdapter:
    name = "gemini"

    def __init__(self) -> None:
        if _genai is None:
            raise ImportError("google-genai package required: pip install google-genai") from _import_error
        self._client = _genai.Client()
        self._cache_registry: dict[str, str] = {}  # content_hash -> cache_name
        self.last_usage: dict[str, int] = {}
        self.last_cache_fallback: bool = False

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        **kwargs: Any,
    ) -> str:
        self.last_cache_fallback = False
        cached_content_name: str | None = None

        if cache_breakpoints:
            bp = cache_breakpoints[0]
            prefix = messages[:bp]
            content_hash = _hash_messages(prefix)

            if content_hash in self._cache_registry:
                cached_content_name = self._cache_registry[content_hash]
            else:
                try:
                    cached = self._client.caches.create(
                        model=model,
                        contents=_to_genai_contents(prefix),
                        ttl=f"{_CACHE_TTL_SECONDS}s",
                    )
                    cached_content_name = cached.name
                    self._cache_registry[content_hash] = cached_content_name
                except _GeminiAPIError:
                    self.last_cache_fallback = True

        remaining = messages[cache_breakpoints[0]:] if (cache_breakpoints and not self.last_cache_fallback) else messages

        system_msgs = [m["content"] for m in remaining if m.get("role") == "system"]
        non_system = [m for m in remaining if m.get("role") != "system"]

        generate_config: dict[str, Any] = {**kwargs}
        if cached_content_name:
            generate_config["cached_content"] = cached_content_name
        if system_msgs:
            generate_config["system_instruction"] = "\n".join(
                s if isinstance(s, str) else str(s) for s in system_msgs
            )

        config_obj = _genai_types.GenerateContentConfig(**generate_config) if generate_config else None

        response = self._client.models.generate_content(
            model=model,
            contents=_to_genai_contents(non_system),
            config=config_obj,
        )

        meta = response.usage_metadata
        self.last_usage = {
            "input_tokens": getattr(meta, "prompt_token_count", 0) or 0,
            "cache_read_tokens": getattr(meta, "cached_content_token_count", 0) or 0,
            "cache_write_tokens": 0,
            "output_tokens": getattr(meta, "candidates_token_count", 0) or 0,
        }

        return response.text or ""


def _hash_messages(messages: list[Message]) -> str:
    serialized = json.dumps(
        [dict(m) for m in messages],
        sort_keys=True,
        default=str,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def _to_genai_contents(messages: list[Message]) -> list[dict]:
    """Convert non-system Message list to google-genai Content format."""
    result = []
    for msg in messages:
        role = msg.get("role", "user")
        # Gemini uses "model" for assistant, "user" for user
        genai_role = "model" if role == "assistant" else "user"
        content = msg.get("content", "")
        if isinstance(content, str):
            parts = [{"text": content}]
        else:
            parts = [
                {"text": block.get("text", "")} if block.get("type") == "text" else block
                for block in content
            ]
        result.append({"role": genai_role, "parts": parts})
    return result
