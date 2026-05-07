from __future__ import annotations

import copy
from typing import Any

from .base import Message

try:
    import anthropic as _anthropic_sdk
except ImportError as exc:  # pragma: no cover
    _anthropic_sdk = None  # type: ignore[assignment]
    _import_error = exc
else:
    _import_error = None


class AnthropicAdapter:
    name = "anthropic"

    def __init__(self) -> None:
        if _anthropic_sdk is None:
            raise ImportError("anthropic package required: pip install anthropic") from _import_error
        self._client = _anthropic_sdk.Anthropic()
        self.last_usage: dict[str, int] = {}

    def complete(
        self,
        messages: list[Message],
        cache_breakpoints: list[int] | None = None,
        model: str = "",
        **kwargs: Any,
    ) -> str:
        if cache_breakpoints is not None and len(cache_breakpoints) > 4:
            raise ValueError(
                f"Anthropic supports at most 4 cache breakpoints; got {len(cache_breakpoints)}"
            )

        prepared = _apply_cache_breakpoints(messages, cache_breakpoints or [])

        system_blocks: list[dict] = []
        conversation: list[dict] = []
        for msg in prepared:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if isinstance(content, str):
                    system_blocks.append({"type": "text", "text": content})
                else:
                    system_blocks.extend(content)
            else:
                conversation.append(msg)

        create_kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": kwargs.pop("max_tokens", 8192),
            "messages": conversation,
            **kwargs,
        }
        if system_blocks:
            create_kwargs["system"] = system_blocks

        response = self._client.messages.create(**create_kwargs)

        usage = response.usage
        self.last_usage = {
            "input_tokens": usage.input_tokens,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "output_tokens": usage.output_tokens,
        }

        return "".join(b.text for b in response.content if b.type == "text")


def _apply_cache_breakpoints(
    messages: list[Message],
    breakpoints: list[int],
) -> list[dict]:
    """Return a deep copy of messages with cache_control injected at breakpoint indices."""
    if not all(0 <= i < len(messages) for i in breakpoints):
        raise ValueError(
            f"cache_breakpoint index out of range for {len(messages)}-message list"
        )
    result = []
    bp_set = set(breakpoints)

    for idx, msg in enumerate(messages):
        msg_copy = copy.deepcopy(dict(msg))
        if idx in bp_set:
            content = msg_copy.get("content", "")
            if isinstance(content, str):
                msg_copy["content"] = [
                    {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                ]
            elif isinstance(content, list) and content:
                content = copy.deepcopy(content)
                content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
                msg_copy["content"] = content
        result.append(msg_copy)

    return result
