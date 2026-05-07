from __future__ import annotations

from typing import Any

from .base import Message

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
        **kwargs: Any,
    ) -> str:
        # cache_breakpoints are not applicable for Ollama; ignored intentionally.
        model_name = model.removeprefix("ollama/") if model.startswith("ollama/") else model

        response = _ollama_sdk.chat(
            model=model_name,
            messages=list(messages),  # type: ignore[arg-type]
            **kwargs,
        )

        # Ollama returns token counts in the response dict under prompt_eval_count / eval_count.
        self.last_usage = {
            "input_tokens": response.get("prompt_eval_count", 0) if isinstance(response, dict) else getattr(response, "prompt_eval_count", 0) or 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "output_tokens": response.get("eval_count", 0) if isinstance(response, dict) else getattr(response, "eval_count", 0) or 0,
        }

        if isinstance(response, dict):
            return response.get("message", {}).get("content", "")
        return response.message.content or ""
