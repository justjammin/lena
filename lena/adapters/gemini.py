from __future__ import annotations

import hashlib
import json
from typing import Any

from .base import Completion, Message, ToolCall

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
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> Completion:
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
        if tools:
            # Translate OpenAI-style tool schema to Gemini FunctionDeclaration list.
            function_declarations = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "parameters": t["function"].get("parameters", {}),
                }
                for t in tools
                if t.get("type") == "function"
            ]
            if function_declarations:
                generate_config["tools"] = [
                    _genai_types.Tool(function_declarations=function_declarations)
                ]

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

        try:
            content_text = response.text or ""
        except Exception:
            content_text = ""

        # Extract function calls from response parts.
        tool_calls: list[ToolCall] = []
        try:
            parts = response.candidates[0].content.parts
            for i, part in enumerate(parts):
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    tool_calls.append(ToolCall(
                        id=f"call_{i}",
                        name=fc.name,
                        arguments=dict(fc.args),
                    ))
        except Exception:
            pass

        return Completion(content=content_text, tool_calls=tool_calls)


def _hash_messages(messages: list[Message]) -> str:
    serialized = json.dumps(
        [dict(m) for m in messages],
        sort_keys=True,
        default=str,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def _to_genai_contents(messages: list[Message]) -> list[dict]:
    """Convert non-system Message list to google-genai Content format.

    Handles OpenAI-wire tool messages for multi-turn tool loops:
    - assistant messages with tool_calls → model turn with function_call parts
    - {role:"tool"} messages → user turn with function_response parts
    """
    result = []
    # Track call id → function name for function_response (Gemini needs the name, not the id).
    id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg.get("role", "user")

        if role == "assistant" and msg.get("tool_calls"):
            # Build model turn with function_call parts.
            parts: list[dict] = []
            if msg.get("content"):
                parts.append({"text": msg["content"]})
            for tc in msg["tool_calls"]:
                # tc is OpenAI wire: {"id","type":"function","function":{"name","arguments"}}
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}")
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                id_to_name[tc["id"]] = fn_name
                parts.append({"function_call": {"name": fn_name, "args": parsed_args}})
            result.append({"role": "model", "parts": parts})

        elif role == "tool":
            # Tool result: becomes a user turn with function_response part.
            call_id = msg.get("tool_call_id", "")
            fn_name = id_to_name.get(call_id, call_id)  # fall back to id if name unknown
            result.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": fn_name,
                        "response": {"result": msg.get("content", "")},
                    }
                }],
            })

        else:
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
