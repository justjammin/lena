from __future__ import annotations

import json
from typing import Any

from .base import Completion, Message, ToolCall

try:
    import openai as _openai_sdk
except ImportError as exc:  # pragma: no cover
    _openai_sdk = None  # type: ignore[assignment]
    _import_error = exc
else:
    _import_error = None


class OpenAIAdapter:
    name = "openai"

    def __init__(self) -> None:
        if _openai_sdk is None:
            raise ImportError("openai package required: pip install openai") from _import_error
        self._client = _openai_sdk.OpenAI()
        self.last_usage: dict[str, int] = {}

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> Completion:
        # cache_breakpoints are not applicable for the OpenAI API; ignored intentionally.
        if tools:
            kwargs["tools"] = tools
        response = self._client.chat.completions.create(
            model=model,
            messages=list(messages),  # type: ignore[arg-type]
            **kwargs,
        )

        usage = response.usage
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cache_read = getattr(details, "cached_tokens", 0) if details else 0
        self.last_usage = {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }

        msg = response.choices[0].message
        content = msg.content or ""
        tool_calls: list[ToolCall] = []
        for i, tc in enumerate(msg.tool_calls or []):
            raw_args = getattr(tc.function, "arguments", None) or "{}"
            tool_calls.append(ToolCall(
                id=tc.id or f"call_{i}",
                name=tc.function.name,
                arguments=json.loads(raw_args),
            ))
        return Completion(content=content, tool_calls=tool_calls)
