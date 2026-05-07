from __future__ import annotations

import json
import logging

_log = logging.getLogger(__name__)

_HEADER = "## Context from upstream steps\n"


class HandoffTransformer:
    """Compress conversation history into a bounded context block for sub-step injection."""

    def __init__(self, cap: int = 500, encoding: str = "cl100k_base") -> None:
        self._cap = cap
        try:
            import tiktoken  # type: ignore[import-untyped]
            self._enc = tiktoken.get_encoding(encoding)
        except Exception:
            self._enc = None
            _log.warning("tiktoken unavailable — falling back to word-count approximation")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def compress(self, messages: list[dict], prior_output: str | None) -> str:
        """Return the header + compressed context string.

        Strategy:
        - Always keep the last assistant turn verbatim.
        - Fill remaining budget from newest → oldest (excluding last assistant).
        - Prepend prior_output if provided and budget allows.
        """
        budget = self._cap - self._count(_HEADER)

        # Separate last assistant turn
        last_assistant: dict | None = None
        rest: list[dict] = []
        for msg in reversed(messages):
            if last_assistant is None and msg.get("role") == "assistant":
                last_assistant = msg
            else:
                rest.append(msg)
        rest = list(reversed(rest))

        # Build last_assistant text
        last_text = ""
        if last_assistant:
            last_text = self._msg_text(last_assistant)
            budget -= self._count(last_text)

        # Optionally include prior_output (from upstream HandoffTransformer)
        prior_text = ""
        if prior_output:
            candidate = f"**Prior output:** {prior_output}\n"
            cost = self._count(candidate)
            if cost <= budget:
                prior_text = candidate
                budget -= cost

        # Fill from newest → oldest in rest
        selected: list[str] = []
        for msg in reversed(rest):
            line = self._msg_text(msg)
            cost = self._count(line)
            if cost > budget:
                break
            selected.append(line)
            budget -= cost
        selected.reverse()

        parts: list[str] = []
        if prior_text:
            parts.append(prior_text)
        parts.extend(selected)
        if last_text:
            parts.append(last_text)

        body = "\n".join(p for p in parts if p)
        return _HEADER + body

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _msg_text(self, msg: dict) -> str:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Anthropic block format — extract text blocks
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    else:
                        text_parts.append(json.dumps(block))
                else:
                    text_parts.append(str(block))
            content = " ".join(text_parts)
        return f"[{role}]: {content}"

    def _count(self, text: str) -> int:
        if self._enc is not None:
            return len(self._enc.encode(text))
        # Rough approximation: 1 token ≈ 4 chars
        return max(1, len(text) // 4)
