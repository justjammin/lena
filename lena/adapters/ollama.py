from __future__ import annotations

from typing import Any

from .base import Completion, Message, ToolCall

try:
    import ollama as _ollama_sdk
except ImportError as exc:  # pragma: no cover
    _ollama_sdk = None  # type: ignore[assignment]
    _import_error = exc
else:
    _import_error = None


class OllamaAdapter:
    name = "ollama"

    def __init__(self) -> None:
        if _ollama_sdk is None:
            raise ImportError("ollama package required: pip install ollama") from _import_error
        self.last_usage: dict[str, int] = {}

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        tools: list[dict] | None = None,
        **kwargs: Any,
    ) -> Completion:
        # cache_breakpoints are not applicable for Ollama; ignored intentionally.
        model_name = model.removeprefix("ollama/") if model.startswith("ollama/") else model

        chat_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": list(messages),  # type: ignore[arg-type]
        }
        if tools:
            chat_kwargs["tools"] = tools  # Ollama accepts OpenAI-style tool schema natively.
        # Forward any remaining kwargs (e.g. options, keep_alive) directly.
        chat_kwargs.update(kwargs)

        response = _ollama_sdk.chat(**chat_kwargs)

        # Ollama returns token counts in the response dict under prompt_eval_count / eval_count.
        self.last_usage = {
            "input_tokens": response.get("prompt_eval_count", 0) if isinstance(response, dict) else getattr(response, "prompt_eval_count", 0) or 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": response.get("eval_count", 0) if isinstance(response, dict) else getattr(response, "eval_count", 0) or 0,
        }

        if isinstance(response, dict):
            message = response.get("message", {})
            content = message.get("content", "")
            raw_tool_calls = message.get("tool_calls") or []
        else:
            content = response.message.content or ""
            raw_tool_calls = getattr(response.message, "tool_calls", None) or []

        tool_calls: list[ToolCall] = []
        for i, tc in enumerate(raw_tool_calls):
            if isinstance(tc, dict):
                fn = tc.get("function", {})
                name = fn.get("name", "")
                arguments = fn.get("arguments", {})
                tc_id = tc.get("id") or f"call_{i}"
            else:
                fn = getattr(tc, "function", None) or {}
                name = getattr(fn, "name", "") if not isinstance(fn, dict) else fn.get("name", "")
                arguments = getattr(fn, "arguments", {}) if not isinstance(fn, dict) else fn.get("arguments", {})
                tc_id = getattr(tc, "id", None) or f"call_{i}"
            # Ollama arguments are already dicts (no json.loads needed).
            tool_calls.append(ToolCall(id=tc_id, name=name, arguments=arguments if isinstance(arguments, dict) else {}))

        return Completion(content=content, tool_calls=tool_calls)
